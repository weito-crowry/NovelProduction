# 02 Normalization 詳細設計

## 1. 目的

Source AdapterまたはProject Draftから得た可読本文をCanonical Textへ変換し、Raw Textとの位置対応と構造Hintを保持する。正規化は解析ノイズだけを除去し、文学的表現を変更しない。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  text_models.py
  normalization.py
  text_mapping.py
  text_service.py
```

HTML/EPUB Parseは01 API Adapter側。Project Draft Projectionは既存Document Engineを再利用する。

## 3. StyleDocument / Current Text

Document Kind:

```text
reference_episode
project_episode_draft
```

Reference Documentは`reference_episode_id`、Project Documentは`project_work_id/project_episode_id`を持つ。

具体的Capture元Draft IDはTextRevision `project_draft_id`へ保存する。

`style_documents.current_text_revision_id` がCurrent解析本文の正本。最大Revision NoをCurrentと仮定しない。

Current Textが別Revisionへ変わった場合だけ `current_structure_revision_id=NULL`。

## 4. Raw Text Serialization契約

Adapter/Project Projectionは`raw_text`を次の形で渡す。

- Block-level paragraph間を空行1つ=`\n\n`で区切る。
- Paragraph内改行は単一`\n`。
- HTML RubyはSurface本文だけ。
- Heading textは本文に存在する場合、独立Paragraphとして残す。
- `<hr>`等の文字を持たない明示Scene Breakは本文へ架空文字を挿入せず、raw code point offsetを`scene_break_offsets_raw`へ記録する。

Paragraph専用Tableは持たない。

## 5. Normalization Input Fingerprint

TextRevision再利用は本文Hashだけで判定しない。

Normalization開始前にCanonical JSONを作る。

```json
{
  "raw_sha256":"...",
  "normalizer_id":"canonical-japanese-fiction",
  "normalizer_version":1,
  "structure_hints_raw":{
    "scene_break_offsets_raw":[120,845]
  }
}
```

`scene_break_offsets_raw`は整数化、範囲Validation、sort/dedupeしてHashする。

このJSONのSHA-256を`normalization_input_fingerprint`としてTextRevisionへ保存する。

同Documentで同Fingerprintなら既存TextRevisionをReuseする。本文が同一でもScene Break Hintが変われば新Revision。

NormalizerまたはHint解釈規則を変える場合はNormalizer Versionを上げる。

## 6. TextRevision

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
normalization_input_fingerprint
normalizer_id
normalizer_version
metadata_json
created_at
```

Document単位Revision No 1..N。Immutable。

Reference TextRevisionは`source_snapshot_id`を持つ。Project TextRevisionは`project_draft_id`を持つ。両方同時は不可。

## 7. Unicode / Offset

Python `str` Unicode Code Point Index、半開 `[start_cp,end_cp)`。

- Byte Offset保存禁止。
- APIは`start_cp/end_cp`。
- WebUIはCode Point→UTF-16変換Utilityを1箇所に置く。
- Unicode NormalizationはNFCのみ。NFKC禁止。

## 8. Normalization順序

1. UTF-8 BOM除去。
2. CRLF/CR→LF。
3. NFC。
4. NULL/非許可Control Character除去。
5. TAB→ASCII Space 1文字。
6. 各行末ASCII Space除去。
7. 空行中ASCII Space除去。
8. 3行以上連続空行を空行1つ=`\n\n`へ縮約。
9. 文書先頭/末尾空行除去。
10. 最終LFなし。

全角空白U+3000は保持する。

## 9. Control Character

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

## 10. TextMapping

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
- Identity区間は結合する。
- NFC変化はReplace。
- 空行縮約はCollapse。
- Canonical Span→Rawは重なる最小Raw範囲 + `exact` Flagを返す。

MappingはTextRevision単位で保存する。

## 11. Scene Break Hint Mapping

`scene_break_offsets_raw`をNormalization完了後にCanonical Offsetへ写像する。

1. TextMappingで対応Canonical Pointを解決。
2. Collapse/Delete境界でも一意にPointへ写せる場合だけ採用。
3. 一意でないHintはDrop + Warning `scene_break_hint_unmappable`。
4. Sort/Dedupe。
5. `0 < offset < len(canonical_text)`だけ採用。

TextRevision `metadata_json`:

```json
{
  "structure_hints": {
    "scene_break_offsets_cp": [120,845]
  }
}
```

## 12. Paragraph定義

Canonical Textの`\n\n`だけをParagraph境界の正本とする。単一LFは同Paragraph内改行。

TextRevisionにParagraph Tableは持たず、03 Block生成時に`paragraph_index`を付ける。

## 13. Project Draft Capture

既存Document EngineのPlain Text Projectionを再利用し、Style Analysis側にTipTap/Structured Draft Parserを複製しない。

Capture APIは`draft_id`明示。latest Draftへ暗黙解決しない。

Flow:

1. Draftが指定Project Work/Episode所属か検証。
2. Existing ProjectionでPlain Text取得。
3. Paragraph間を`\n\n`でSerialization。
4. Normalization Input Fingerprint計算。
5. Normalizeまたは同Fingerprint Revision Reuse。
6. Current Text設定。
7. Current Text変更時だけCurrent Structure Clear。

Authoring Draftは更新しない。

## 14. Version / Error

```text
normalizer_id = canonical-japanese-fiction
normalizer_version = 1
```

Error:

```text
TEXT_EMPTY
TEXT_TOO_LARGE
TEXT_MAPPING_INVALID
PROJECT_DRAFT_NOT_FOUND
PROJECT_DRAFT_TEXT_PROJECTION_FAILED
```

1 Episode上限2,000,000 Code Points。

## 15. Test

- CRLF/BOM/NFC/NFKC非適用。
- 全角空白/TAB/Trailing Space。
- Paragraph `\n\n`保持。
- 3以上空行縮約。
- Single LFはParagraph分割しない。
- Control Character/Mapping/Emoji。
- Scene Break Raw→Canonical Mapping成功/Drop。
- 同Raw + 同Hint -> Revision Reuse。
- 同Raw + 異なるHint -> New Revision。
- Normalizer Version変更 -> New Revision。
- Current Text変更時Structure Clear。
- Explicit Draft Capture。

## 16. Codex禁止事項

- `str.strip()`無差別適用。
- NFKC/Lowercase。
- Raw Text破棄。
- Byte Offset保存。
- Paragraph Hint専用Table追加。
- `<hr>`を架空本文へ変換。
- Scene Break Raw OffsetをMappingなしでCanonical扱い。
- TextRevision Reuseをraw_sha256だけで判定。
- Draft IDをStyleDocumentへ重複保存。
- Current Textを最大Revision Noで推測。
- Authoring Draft Update。
