# 02 Normalization 詳細設計

## 1. 目的

外部sourceや自作品snapshotから得た本文を、解析に安定して利用できるCanonical Textへ変換し、Raw Textとの位置対応を保持する。正規化は文学的表現を変更する処理ではなく、解析ノイズだけを除去する処理とする。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  text_models.py
  normalization.py
  text_mapping.py
```

network/HTML DOM parsingは01のAPI adapterで完了させる。本書における `raw_text` はHTMLそのものではなく、adapterが抽出した「作品本文の可読テキスト」である。

## 3. TextRevisionモデル

1回の正規化出力を不変 `TextRevision` とする。

必須属性:

```text
id
document_id
revision_no
source_snapshot_id nullable
project_draft_id nullable
raw_text
canonical_text
raw_sha256
canonical_sha256
normalizer_id
normalizer_version
created_at
```

`revision_no` はdocument単位で1から増加する。既存revisionはupdateしない。

同一documentで `raw_sha256 + normalizer_id + normalizer_version` が完全一致する場合は既存revisionを返し、新revisionを作らない。

## 4. Unicode・offset仕様

offsetはPython `str` のUnicode code point indexで統一し、半開区間 `[start, end)` を使う。

- byte offsetを永続化しない。
- JavaScript側ではUTF-16 indexとの差があるため、APIでspanを返す際は `start_cp/end_cp` と命名する。
- UIでhighlightする場合、code point→UTF-16変換utilityを1箇所に実装する。

Unicode normalizationは **NFC** のみ使用する。NFKCは禁止する。全角・半角、記号、異体表現を互換変換すると文体特徴が壊れるためである。

## 5. 正規化パイプライン順序

順序を固定する。

1. UTF-8 BOMが先頭にあれば除去
2. CRLF/CRをLFへ変換
3. Unicode NFC
4. NULL文字、非許可制御文字を除去
5. horizontal tabをASCII space 1文字へ変換
6. 各行末のASCII space/tab由来spaceを除去
7. 空行だけに含まれるASCII spaceを除去
8. 連続空行3行以上を空行2行へ縮約
9. 文書先頭・末尾の空行を除去
10. 最終行末LFは持たない

全角空白 `U+3000` は削除・縮約しない。行頭字下げや演出に使われる可能性があるためである。

## 6. 削除対象制御文字

保持:

```text
LF U+000A
TAB U+0009 はstep 5でspaceへ変換
```

除去:

- U+0000
- U+0001〜U+0008
- U+000B〜U+000C
- U+000E〜U+001F
- U+007F

その他Unicode format characterは一律削除しない。Variation Selector、ZWJ等を壊さないためである。

## 7. ルビ・傍点

サイトadapterは、HTML rubyについて `raw_text` に本文surfaceだけを出力する。

例:

```html
<ruby>東京<rt>とうきょう</rt></ruby>
```

`raw_text`:

```text
東京
```

読み仮名はsource snapshot metadataへ保存してよいが、Canonical Textへ混ぜない。

傍点用DOMも本文surfaceだけ残す。装飾情報はv1の文体計測対象外。

TXT/EPUB内に文字として存在する `｜語《よみ》` 等の独自ルビ記法は勝手に除去しない。明示的な記法判定は将来Analyzerで扱う。

## 8. TextMapping

Raw→Canonicalの変換箇所をrun-length形式で保存する。1文字ごとのmappingは保存しない。

```python
@dataclass(frozen=True)
class TextMapSegment:
    raw_start: int
    raw_end: int
    canonical_start: int
    canonical_end: int
    operation: Literal["identity", "replace", "delete", "collapse"]
```

mapping要件:

- segmentはraw_start順、重複なし。
- raw/canonical両方で隙間のない範囲を表現する。
- identity区間は可能な限り結合する。
- NFCにより複数code point→1 code pointになる箇所は `replace`。
- 空行縮約は `collapse`。

span逆変換は「canonical spanに重なる最小raw範囲」を返す。完全な1対1復元ができない変換は `exact=false` を返す。

## 9. Document種別

`style_documents.kind` は以下に限定する。

```text
reference_episode
project_episode_draft
```

### reference_episode

`style_reference_episode_id` を必須とし、project work/episode IDはNULL。

### project_episode_draft

既存 `works.id`、`episodes.id`、`drafts.id` を保持する。解析開始時点のdraft本文をsnapshotし、その後authoring側が更新されてもTextRevisionは変更しない。

## 10. 自作品本文の取り出し

structured draftの正本は既存Document JSONである。Plain text化は既存document engineのcanonical reader/text projectionを再利用し、独自TipTap JSON parserをStyle Analysis側へ複製しない。

project episodeにdraftがない場合は `PROJECT_DRAFT_NOT_FOUND`。

## 11. Paragraph定義

Canonical Text内の行を構造解析へ渡す。paragraphは以下で定義する。

- 空行で区切られた非空テキスト群を1 paragraphとする。
- ただし、投稿サイト由来adapterが明示的なHTML paragraph境界をmetadataとして持つ場合、その境界を優先して `paragraph_hints` として渡す。
- 1行ごとに `<p>` が付くサイトで空行が存在しなくてもparagraph hintを利用する。

TextRevision自身にはparagraph tableを持たず、03のBlock生成時に構造化する。

## 12. Versioning

初期値:

```text
normalizer_id = canonical-japanese-fiction
normalizer_version = 1
```

正規化ルールを1つでも変更した場合はversionを上げる。旧revisionを再計算して上書きしない。

## 13. エラー

```text
TEXT_EMPTY
TEXT_TOO_LARGE
TEXT_MAPPING_INVALID
PROJECT_DRAFT_NOT_FOUND
PROJECT_DRAFT_TEXT_PROJECTION_FAILED
```

Canonical Textが空文字なら失敗。

初期上限は1episode 2,000,000 code points。超過は分割せず拒否する。

## 14. テスト

必須unit test:

- CRLF→LF
- BOM除去
- NFC合成
- NFKCされないこと
- 全角空白保持
- tab変換
- trailing ASCII space除去
- 3以上の空行縮約
- control char除去
- mapping round-trip相当範囲
- emoji/surrogate相当文字を含むcode point offset
- 同一hashのidempotent revision
- structured draft projectionの固定fixture

property testライブラリは追加しない。代表fixtureを明示的に列挙する。

## 15. Codex実装時の禁止事項

- `str.strip()` を本文全体・全行へ無差別適用しない。
- NFKC、lowercase等の意味変更normalizationを行わない。
- raw_textを捨てない。
- offsetをbyte数で保存しない。
- authoring draftをStyle Analysisから更新しない。
- 既存Document JSON schemaをStyle Analysis都合で変更しない。
