# 02 Normalization 詳細設計

## 1. 目的

Source AdapterまたはProject Draftから得た可読本文をCanonical Textへ変換し、Raw Textとの位置対応を保持する。正規化は解析ノイズだけを除去し文学的表現を変更しない。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  text_models.py
  normalization.py
  text_mapping.py
  text_service.py
```

HTML DOM Parsing/Networkは01 API Adapter側。

## 3. StyleDocument / TextRevision

Document Kind:

```text
reference_episode
project_episode_draft
```

### reference_episode

`style_documents.reference_episode_id` を持つ。Project Work/Episode IDはNULL。

### project_episode_draft

`style_documents.project_work_id/project_episode_id` を持つ。具体的なCapture元Draft IDはDocument RowではなくTextRevision `project_draft_id` に保存する。

### Current Text

`style_documents.current_text_revision_id` がCurrent解析本文の正本。

新しいReference本文/Project Draft CaptureをCurrentへ採用する時:

1. TextRevisionを作成または既存同一RevisionをReuse。
2. Current TextRevision IDを設定。
3. Current Textが実際に変わった場合だけ `current_structure_revision_id=NULL`。

Latest Revision NoをCurrentと仮定しない。

## 4. TextRevision

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
metadata_json
created_at
```

Document単位Revision No 1..N。Immutable。

同Documentで:

```text
raw_sha256 + normalizer_id + normalizer_version
```

が一致すれば既存Revisionを返してよい。Reuse時にCurrent TextがそのRevisionと既に同一ならStructure PointerをClearしない。

## 5. Unicode / Offset

Python `str` Unicode Code Point Index、半開 `[start_cp,end_cp)`。

- Byte Offset保存禁止。
- APIは `start_cp/end_cp`。
- WebUIはCode Point→UTF-16変換Utilityを1箇所に実装。
- Unicode NormalizationはNFCのみ。NFKC禁止。

## 6. Normalization順序

1. UTF-8 BOM除去
2. CRLF/CR→LF
3. NFC
4. NULL/非許可Control除去
5. TAB→ASCII Space 1文字
6. 行末ASCII Space除去
7. 空行中ASCII Space除去
8. 3行以上連続空行を2行へ縮約
9. 文書先頭/末尾空行除去
10. 最終LFなし

全角空白U+3000は保持する。

## 7. Control Character

保持: LF。TABはStep5で変換。

除去:

```text
U+0000
U+0001..0008
U+000B..000C
U+000E..001F
U+007F
```

その他Format Characterを一律削除しない。

## 8. Ruby / Decoration

HTML RubyはAdapterがSurface本文だけをraw_textへ出す。読み仮名は必要ならSnapshot Metadata。

TXT/EPUB中の `｜語《よみ》` 等、文字として存在する独自記法は勝手に除去しない。

## 9. TextMapping

Run-length Segment:

```python
@dataclass(frozen=True)
class TextMapSegment:
    raw_start: int
    raw_end: int
    canonical_start: int
    canonical_end: int
    operation: Literal["identity", "replace", "delete", "collapse"]
```

- Raw/Canonical双方で順序・非重複。
- Identity区間は結合。
- NFC変化はReplace。
- 空行縮約はCollapse。
- Canonical Span→Rawは重なる最小Raw範囲 + `exact` Flag。

## 10. Project Draft Capture

Structured DraftのPlain Text Projectionは既存Document Engineを再利用し、Style Analysis側にTipTap Parserを複製しない。

Capture APIは `draft_id` 明示。Latest Draftへ暗黙解決しない。

Flow:

1. Draftが指定Episode所属か検証。
2. Existing Canonical ProjectionでPlain Text取得。
3. Normalization。
4. TextRevision Insert/Reuse (`project_draft_id=draft_id`)。
5. Document Current TextをそのRevisionへ設定。
6. Current Textが変わった時だけCurrent Structure Clear。

Authoring Draftは更新しない。

## 11. Paragraph

Canonical Textの空行区切りをParagraphとする。Adapterに明示HTML Paragraph Hintがある場合は優先Hintとして03へ渡す。TextRevision自身にParagraph Tableは持たない。

## 12. Version / Error

```text
normalizer_id = canonical-japanese-fiction
normalizer_version = 1
```

Rule変更時はVersion Up。

Error:

```text
TEXT_EMPTY
TEXT_TOO_LARGE
TEXT_MAPPING_INVALID
PROJECT_DRAFT_NOT_FOUND
PROJECT_DRAFT_TEXT_PROJECTION_FAILED
```

1 Episode初期上限2,000,000 Code Points。

## 13. Test

- CRLF/BOM/NFC/NFKC非適用
- 全角空白保持/TAB/Trailing Space
- 空行縮約/Control Character
- Mapping
- Emoji Code Point
- Same Revision Reuse
- Current Text Pointer新規/Reuse
- Current Text変更時Structure Clear
- Project Draft IDはTextRevisionに保存
- Explicit Draft Capture

## 14. Codex禁止事項

- `str.strip()` 無差別適用
- NFKC/Lowercase
- Raw Text破棄
- Byte Offset保存
- Draft IDをStyleDocumentへ重複保存
- Current TextをLatest Revision Noで推測
- Authoring Draft Update
- Existing Document JSON Schema変更
