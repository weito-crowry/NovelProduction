# 03 Structure Segmentation 詳細設計

## 1. 目的

Canonical Textを、後段の意味解析・文体計測が参照できる安定構造へ分解する。構造解析は可能な限り決定論的にし、LLMによる判断で本文の境界自体を勝手に変更しない。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  structure_models.py
  segmentation.py
  sentence_splitter.py
  structure_repository.py
```

## 3. StructureRevision

TextRevisionに対する構造解析結果を `StructureRevision` として不変保存する。

```text
id
text_revision_id
revision_no
segmenter_id
segmenter_version
source_kind = automatic | manual
parent_structure_revision_id nullable
created_at
```

同一 `text_revision + segmenter version + config` の自動解析はfingerprint一致時に再利用する。

手動scene split/mergeは既存rowを書き換えず、新しいmanual StructureRevisionを作る。

## 4. 階層

```text
TextRevision
  └─ StructureRevision
      └─ Scene
          └─ Block
              └─ Sentence
```

すべてCanonical Textの `[start_cp,end_cp)` spanを持つ。子spanは親span内に完全包含されること。

## 5. Block定義

初期 `block_type` は以下のみ。

```text
dialogue
narration
monologue
heading
separator
unknown
```

`action / description / exposition / psychology / transition` はBlock typeにしない。06のsemantic annotationで扱う。

Blockは原則paragraph単位。ただし1paragraph中に明確な会話と地の文が混在する場合のみ分割する。

例:

```text
彼は振り返った。「行こう」そして歩き出した。
```

以下3blockに分ける。

```text
narration: 彼は振り返った。
dialogue: 「行こう」
narration: そして歩き出した。
```

## 6. Quote scanner

日本語小説向けにstack based scannerを実装する。

主会話括弧:

```text
「 」
```

補助括弧:

```text
『 』
（ ）
( )
```

判定ルール:

- `「...」` を最優先でdialogue候補とする。
- `『...』` 単独は会話とは断定せず、周囲がdialogue内なら引用内引用、地の文内ならnarrationのままとする。
- `（...）` は自動的にmonologueにしない。
- unmatched `「` はparagraph末までdialogue候補とするが `structure_warning=unclosed_dialogue_quote` を付ける。
- nested quoteはstackで処理し、外側spanを1dialogue blockとする。

会話括弧内の改行は1dialogue blockに含めてよい。paragraph hintsが途中にあっても閉じ括弧まで優先する。

## 7. Monologue

v1では記号だけから内心独白を断定しない。

- 明示的な独白記号がsource metadataにある場合のみ `monologue`。
- それ以外の心内語はnarrationとして構造化し、06 semantic analyzerがpsychology判定する。

これにより構造parserの誤分類を抑える。

## 8. Heading

以下をheading候補とする。

- source adapterがepisode内heading hintを出したspan
- 独立行で40 code points以下、末尾が `。！？!?` ではなく、前後に空行がある行

ただし機械判定だけでheadingにするのは、次のいずれかも満たす場合に限定する。

- `第...章/話/節` 等の見出しpattern
- 数字・漢数字と短いtitleの組合せ
- adapter明示hint

曖昧な短文はnarrationにする。

## 9. Separator

明示scene separator pattern初期値:

```text
***
＊＊＊＊＊
＊ ＊ ＊
---
――――
◇
◆
◇◇◇
◆◆◆
†
```

判定は独立paragraphのみ。記号だけで構成され、32 code points以下であること。

adapterが明示separator hintを出した場合はpattern外でもseparatorにする。

## 10. Sentence split

SentenceはBlock内部だけで分割する。

終端文字:

```text
。！？!?
```

終端後に以下の閉じ記号が連続する場合、それらまでsentenceへ含める。

```text
」』）)]】
```

省略記号 `……`、ダッシュ `――` は単独でsentence終端にしない。

dialogue blockは内部の複数文をSentenceに分けるが、block自体は1発言単位を維持する。

末尾に終端記号がなくても残り文字列を最後のSentenceとする。

## 11. Scene自動境界

v1のautomatic StructureRevisionでは保守的にsceneを切る。

境界を確定するのは以下のみ。

1. separator block
2. source adapterが明示したscene break
3. heading blockが本文途中に出現し、前に本文blockが存在する場合
4. Canonical Textで空行が3行以上存在していたことをnormalization metadataが保持しており、adapterもscene break candidateとして示した場合

時間・場所・POV・登場人物変化だけではautomatic scene boundaryを確定しない。それらは06が `scene_boundary_candidate` annotationとして提案し、Review UIからmanual split可能にする。

separator自身は前後どちらのscene本文にも含めず、structure上のseparator blockとして保持する。scene spanはseparatorを除外する。

## 12. Scene最小条件

- analyzable blockが1件以上あること。
- 空sceneは作らない。
- 連続separatorはまとめて1境界扱い。
- headingだけのsceneは作らず、次scene先頭headingとして含める。

## 13. Manual split/merge

手動操作は新StructureRevisionを生成する。

### split

- split位置はBlock境界だけ許可。
- Sentence途中・Block途中ではsplit不可。
- 元sceneのBlockを前後2sceneへ再配分。

### merge

- 隣接sceneのみ。
- 間のseparator blockは構造revision内に残すが、merged sceneのspanはseparatorを跨いでよい。

Manual revision生成後、そのrevisionをinputとするsemantic/metric分析は新規runが必要。旧分析結果は削除しない。

## 14. Warning

構造解析は致命的でない異常をwarningとして保存する。

```text
unclosed_dialogue_quote
unmatched_closing_quote
ambiguous_heading
empty_paragraph_hint
mapping_boundary_mismatch
```

warningはReviewQueueに送ってよいが、解析全体は継続する。

## 15. Validation

永続化前に以下をassertする。

- scene/order_indexが連続1..N
- block/order_indexがscene内連続
- sentence/order_indexがblock内連続
- span start < end
- spanがCanonical Text長を超えない
- sibling spanが重複しない。ただしmerged sceneがseparatorを跨ぐ場合もblock同士は非重複。
- block text == canonical_text[start:end]
- sentence text == canonical_text[start:end]

不一致は `STRUCTURE_INVARIANT_ERROR` としてtransaction rollback。

## 16. Version

```text
segmenter_id = japanese-fiction-structure
segmenter_version = 1
```

pattern変更、quoteルール変更、sentence splitter変更はversion更新対象。

## 17. テストfixture

最低限:

- 地の文のみ
- 会話のみ
- 地の文→会話→地の文が同一paragraph
- nested `「『』」`
- unmatched quote
- multiline dialogue
- separator複数種
- heading候補/非候補
- `！？` 連続
- `。」` のsentence終端
- emojiを含むoffset
- scene split/merge
- StructureRevision不変性

## 18. Codex実装時の禁止事項

- LLMでautomatic構造を全面再構成しない。
- whitespaceだけを根拠に過剰なscene分割をしない。
- Block typeへsemantic分類を混ぜない。
- manual split/mergeで既存StructureRevisionをupdateしない。
- `start/end` を本文検索で後付け推定しない。parser処理中にoffsetを確定する。
