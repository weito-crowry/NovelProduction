# 01 Source Ingestion 詳細設計

## 1. 目的

ユーザーが手元に用意した小説本文ファイルを再現可能なSourceSnapshotとして取り込み、Reference Work/EpisodeとStyleDocument Current TextRevisionを更新する。取得元サイト固有の自動ダウンロードはv1対象外とし、Import/Parse、Normalization、解析を分離する。

上位仕様は `../basic-design.md`。

## 2. v1対象

```text
text
html_file
epub
```

すべてLocal File Importのみ。Narou/Kakuyomu等の直接Network Adapter、Generic Crawler、Remote HTML Fetch、Refreshはv1で実装しない。

将来Site Adapterを追加する場合は、その時点の公式利用条件と取得手段を別Phaseで再設計する。

## 3. 実装境界

```text
CORE/src/novel_core/style_analysis/
  source_models.py
  source_repository.py
  text_service.py

API/src/novel_api/style_analysis/
  ingestion_service.py
  adapters/
    base.py
    text.py
    html_file.py
    epub.py
```

- TXT/HTML/EPUB Parse: API Adapter。
- Raw→Canonical Normalization/TextRevision: CORE 02。
- AdapterはDBへ書かない。
- ImportはHTTP Request内で同期実行し、Jobを作らない。

## 4. Source Identity

v1は **1 Source = 1 Reference Work**。

```text
external_work_id = upload bytes SHA-256
```

UNIQUE `(source_type, external_work_id)`。

同じBytesを再Uploadした場合はExisting Source/Reference Workを返し、Parse/Persistを再実行しない。

## 5. SourceAdapter契約

```python
@dataclass(frozen=True)
class SourceRequest:
    source_type: Literal["text", "html_file", "epub"]
    filename: str
    payload: bytes

@dataclass(frozen=True)
class SourceIdentity:
    external_work_id: str

class SourceAdapter(Protocol):
    def identify(self, request: SourceRequest) -> SourceIdentity: ...
    def import_work(self, request: SourceRequest) -> ImportedWork: ...
```

`identify()` はUpload BytesだけからIdentityを決める。

`ImportedEpisode`:

```text
external_episode_id
title
order_index
raw_text
metadata
```

`ImportedEpisode.metadata`で02が使用するv1項目:

```text
scene_break_offsets_raw: list[int]
```

AdapterはCanonical化しない。

`ImportedWork`:

```text
title
author_name nullable
metadata
episodes
```

## 6. Import Flow

```text
POST /imports/file
```

1. Upload Size Validation。
2. Source Type Validation。
3. SHA-256でIdentity計算。
4. Existing Source判定。
5. NewならAdapter ParseをDB Transaction外で実行。
6. 各EpisodeをCORE TextServiceへ渡し02 Normalization Input Fingerprint/Canonical Textを生成。
7. 1 TransactionでSource/Snapshot/ReferenceWork/Episode/Document/TextRevisionを保存。
8. Current Text Pointerを設定。
9. Commit後Reference Work Summaryを返す。

HTTP:

- New: `201 Created`。
- Duplicate: `200 OK` + `reused_existing=true`。
- Upload超過: `413`。
- Parse/Encoding/Normalization失敗:同期Error。

All-or-Nothing。1 EpisodeでもParse/Normalize/Persistに失敗した場合、新Reference Workを部分保存しない。

## 7. Resource上限

```text
File upload: 100 MiB
1 Episode canonical text: 2,000,000 code points
```

超過は `SOURCE_TOO_LARGE`。

Upload Staging Table、Temporary Spool、Streaming Importはv1で導入しない。

## 8. SourceSnapshot / Current Text

- Upload元Bytesを`style_source_snapshots.raw_payload`へBLOB保存。
- HashはBytes基準。
- SourceSnapshot immutable。
- ReferenceWork/ReferenceEpisodeはCurrent Catalog Projection。
- Current解析本文の正本は`StyleDocument.current_text_revision_id`。
- ReferenceEpisodeへCurrent Text Pointerを重複保持しない。

02 `normalization_input_fingerprint` と既存Revisionが一致すればRevisionをReuseする。

本文文字列が同じでもScene Break Hint等の構造入力が変われば別TextRevisionとする。

Current Textが別Revisionへ変わった時だけ:

```text
current_text_revision_id = new revision
current_structure_revision_id = NULL
```

過去Revision/Runは保持する。

## 9. text Adapter

- UTF-8 / UTF-8 BOM。
- 1 File = 1 Episode。
- `external_episode_id = "1"`。
- Work/Episode Title = filename stem。
- Decode不能は `SOURCE_ENCODING_ERROR`。

## 10. html_file Adapter

追加Network Accessなし。

- HTMLをUpload BytesからParse。
- `script/style/noscript`等の非本文要素を除外。
- 主要本文Containerを決定できる場合はその本文、決定不能なら`body`の可読Textを使う。
- Block-level要素間を02契約のParagraph形式へSerialization。
- `<br>`は単一LF。
- `<ruby>`はSurface本文のみ。
- `<hr>`等の文字を持たない明示区切りは架空文字を挿入せず`scene_break_offsets_raw`へ記録。
- `external_episode_id = "1"`。
- Title = HTML title → filename stem fallback。

本文を一意に抽出できず空になる場合は `SOURCE_PARSE_ERROR`。

## 11. epub Adapter

- DRMなしEPUBのみ。
- ZIP/OPF/SpineをParse。
- Spine順に1 Spine Document = 1 Episode。
- Navigation/CoverだけのItemは除外。
- `external_episode_id = "spine:{1-based-order}"`。
- Episode Title = Navigation/Heading → `Episode {n}` fallback。
- Work Title/Author = EPUB Metadata → filename fallback。
- HTML本文Serializationはhtml_fileと同じ規則。
- 同じUpload SourceSnapshotを複数Episodeが参照してよい。

## 12. Duplicate / Re-import

同一 `(source_type, external_work_id)` はExisting Workを返す。

変更ファイルはBytes Hashが変わるため新Source/New Reference WorkとしてImportする。v1では既存Reference WorkへRefresh/Replaceしない。

Duplicate RaceはDB Unique Constraint競合後にExisting Source/Workを再取得して同じ200 Responseへ収束させる。

## 13. Purge

Reference Work削除は対応するSource RowをDELETEする。

1 Source = 1 WorkなのでCascadeで:

```text
SourceSnapshot
ReferenceWork/Episode
StyleDocument
Text/Structure
AnalysisRun/Measurement
Entity/Term
Corpus Membership
```

を削除する。

Aggregate/ProfileのHistorical Snapshot扱いは08/12を正本とする。

通常の削除確認は1回だけ。追加の権利確認Dialog/Checkboxは設けない。

## 14. Error

```text
SOURCE_TYPE_UNSUPPORTED
SOURCE_TOO_LARGE
SOURCE_PARSE_ERROR
SOURCE_ENCODING_ERROR
SOURCE_EMPTY
```

Network Error系はv1に存在しない。

## 15. Test

- TXT/HTML/EPUB Identity = Upload SHA-256。
- New -> 201同期、Jobなし。
- Duplicate -> 200、Parse/Persistなし。
- Duplicate Race -> Existing Reuse。
- Upload Limit/Encoding/Parse Error。
- EPUB Spine Order/Metadata。
- Adapter ParseとNormalization責務分離。
- HTML/EPUB `<hr>` Raw Scene Hint。
- Same Normalization Input -> TextRevision Reuse。
- Same Raw TextでもHint変更 -> New TextRevision。
- New Current Text -> Current Structure Clear。
- All-or-Nothing Persistence。
- Purge Cascade。

## 16. Codex禁止事項

- Narou/Kakuyomu/Generic Network Downloader追加。
- Remote URL Import追加。
- Refresh機能追加。
- Local File ImportをJob化。
- Upload Staging Table追加。
- Adapter内へCanonical Normalizationを実装。
- Duplicate用No-op Job追加。
- Source/Work Many-to-many化。
- Raw Text一致だけでTextRevision Reuse。
- Current Text二重管理。
- MCP Tool追加。
