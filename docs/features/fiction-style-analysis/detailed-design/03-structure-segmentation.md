# 03 Structure Segmentation 詳細設計

## 1. 目的

Canonical Textを、後段の意味解析・文体計測が参照できる安定構造へ分解する。本文文字列は変更せず、Scene境界の改善は新しい `StructureRevision` として表現する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  structure_models.py
  segmentation.py
  sentence_splitter.py
  structure_repository.py
  structure_service.py
```

## 3. StructureRevision

```text
id
text_revision_id
revision_no
segmenter_id
segmenter_version
source_kind = automatic | semantic | manual
parent_structure_revision_id nullable
fingerprint
created_at
```

- `automatic`: 決定論的parserによるbase構造。
- `semantic`: 06/09のScene Boundary Analyzer結果をmaterializeした構造。
- `manual`: ユーザーsplit/mergeを反映した構造。

既存revisionはupdateしない。manual/semantic revisionはparentを必ず持つ。

## 4. 階層

```text
TextRevision
  └─ StructureRevision
      ├─ Scene
      │   └─ Block
      │       └─ Sentence
      └─ Scene外Separator Block
```

すべてCanonical Textの `[start_cp,end_cp)` spanを持つ。

### order_index規則

曖昧さを避けるため次で固定する。

- `Scene.order_index`: StructureRevision内で1..N。
- `Block.order_index`: **StructureRevision全体で**本文順に1..N。Sceneごとに振り直さない。
- `Block.paragraph_index`: StructureRevision全体で元paragraph順に1..N。同paragraphから複数Blockへ分割しても同値。
- `Sentence.order_index`: Block内で1..N。

これにより `scene_id=NULL` のseparatorもBlockの全体順序上に一意に配置できる。

## 5. Block type

```text
dialogue
narration
monologue
heading
separator
unknown
```

`action / description / exposition / psychology / transition` は06のsemantic annotationとする。

Blockは原則paragraph単位。ただし1paragraph中に明確な会話括弧と地の文が混在する場合は分割する。

例:

```text
彼は振り返った。「行こう」そして歩き出した。
```

```text
narration: 彼は振り返った。
dialogue: 「行こう」
narration: そして歩き出した。
```

## 6. Quote scanner

stack based scannerを使う。

主会話括弧: `「 」`。
補助括弧: `『 』`, `（ ）`, `( )`。

- `「...」` はdialogue候補。
- `『...』` 単独は会話と断定しない。
- `（...）` を自動monologueにしない。
- unmatched `「` はparagraph末までdialogue候補としwarningを付ける。
- nested quoteは外側を1dialogue blockとして保持する。
- multiline dialogueは閉じ括弧まで1blockを許可する。

## 7. Monologue

v1では記号だけで内心独白を断定しない。source metadataで明示された場合だけ `monologue`。その他はnarrationとして構造化し、06の`psychology`分類へ渡す。

## 8. Heading

headingは次のいずれか。

- adapterの明示heading hint
- 独立行40 code points以下で、`第...章/話/節` 等の見出しpatternに一致
- 数字/漢数字 + 短いtitleの明確な見出し形式

単に短い文という理由だけでheadingにしない。

## 9. Separator

初期pattern:

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

独立paragraph、記号中心、32 code points以下。adapter hintがあればpattern外も可。

## 10. Sentence split

SentenceはBlock内部だけで分割する。

終端: `。！？!?`。
終端後の `」』）)]】` は同Sentenceに含める。
`……` / `――` は単独終端にしない。

残り文字列は終端記号なしでも最後のSentenceとする。

## 11. Automatic Scene

base `automatic` revisionでは明示的な境界だけを使う。

1. separator block
2. adapter scene-break hint
3. 本文途中のheading

明示境界がなければepisode全体を1 Sceneとしてよい。このbase revisionはSemantic Boundary Analyzerの安定入力を作るための構造であり、最終Scene粒度とは限らない。

separator blockは `scene_id=NULL` で保持する。

## 12. Semantic Scene materialization

full analysisでは09の `scene-boundary-detector` がbase Scene内部のBlock境界を評価する。

Policy default `scene_boundary_auto_apply = 0.85` 以上の候補を自動適用し、新しい `source_kind=semantic` StructureRevisionを作る。0.60以上0.85未満の候補は提案として保持するが自動適用しない。値の正本は09のAnalysisPolicy。

materialize処理自体は決定論的CORE serviceとし、LLM出力が本文spanを直接書き換えない。

- candidateは `after_block_id` だけを指定する。
- candidate Blockがparent revisionに存在しない場合は無視してwarning。
- 同一境界の重複候補は最高confidenceだけを採用。
- separator/heading既存境界と重なる候補は追加境界を作らない。
- 結果がbaseと同一ならsemantic revisionを新規作成せずbaseを再利用する。

full analysisの後続Entity/Term/Scene Semantics/Metricは、このsemantic revisionを使用する。

## 13. Scene最小条件

- analyzable blockが1件以上。
- 空Sceneを作らない。
- 連続separatorは1境界扱い。
- headingだけのSceneは作らず次Scene先頭に含める。

## 14. Manual split/merge

手動操作は現在のeffective StructureRevisionをparentにした新 `manual` revisionを作る。

### split

- Block境界だけ許可。
- `after_block_id` を指定。
- Block途中/Sentence途中ではsplit不可。

### merge

- 隣接Sceneだけ。
- 間のseparatorはBlockとして残す。
- merged Scene spanはseparatorを跨いでよい。

新StructureRevision後は、そのrevisionに依存するsemantic/metric runを再実行する。旧結果は削除しない。

## 15. Warning

```text
unclosed_dialogue_quote
unmatched_closing_quote
ambiguous_heading
empty_paragraph_hint
mapping_boundary_mismatch
semantic_boundary_invalid
```

warningは解析継続可能な診断情報。すべてをReviewItemへ自動投入しない。

## 16. Validation

永続化前にassertする。

- Scene orderが1..N。
- Block orderがStructureRevision全体で1..N。
- Sentence orderが各Block内1..N。
- span `start < end`。
- spanがCanonical Text長内。
- sibling Block spanが重複しない。
- Block text == canonical slice。
- Sentence text == canonical slice。
- Scene所属Block spanはScene span内。

不一致は `STRUCTURE_INVARIANT_ERROR` でrollback。

## 17. Version

```text
segmenter_id = japanese-fiction-structure
segmenter_version = 1
```

quote、heading、separator、sentence rule変更はversion更新対象。

Semantic Boundary Analyzerのthreshold変更だけではsegmenter versionを上げず、AnalysisPolicy version/fingerprintを変える。

## 18. テスト

- 地の文のみ
- 会話のみ
- narration→dialogue→narration同paragraph
- nested quote
- unmatched quote
- multiline dialogue
- separator
- heading
- sentence終端
- emoji offset
- Block global order + scene_id NULL separator
- semantic candidate materialization
- threshold未満candidate非適用
- manual split/merge
- revision不変性

## 19. Codex実装時の禁止事項

- LLMから任意character offsetでSceneを切らない。
- Block typeへsemantic分類を混ぜない。
- manual/semantic処理でparent StructureRevisionをupdateしない。
- `start/end` を本文検索で後付け推定しない。
- ambiguous candidateを全部ReviewQueueへ自動投入しない。