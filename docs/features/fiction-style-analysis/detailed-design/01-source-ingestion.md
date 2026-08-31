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

## 3. 実装境界 / Parser依存

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
    html_dom.py
```

- TXT/HTML/EPUB Parse: API Adapter。
- Raw→Canonical Normalization/TextRevision: CORE 02。
- AdapterはDBへ書かない。
- ImportはHTTP Request内で同期実行し、Jobを作らない。

API Runtime Dependencyへ次だけ追加する。

```text
beautifulsoup4>=4.13,<5.0
```

HTML/XHTML DOM Parseは:

```python
BeautifulSoup(payload_or_text, "html.parser")
```

を使用する。Parser Backendを`lxml`/`html5lib`へ切替えない。

EPUB ZIP/Container/OPF ParseはPython標準Library:

```text
zipfile
xml.etree.ElementTree
```

を使用する。`ebooklib`/`lxml`はv1で追加しない。

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

EPUBはZIP Central Directoryを読んだ時点で、Spine本文として読み込むEntryの`ZipInfo.file_size`合計が200 MiBを超える場合も`SOURCE_TOO_LARGE`とする。これは単一の展開量上限であり、Entry個別の追加制限はv1で設けない。

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
- Decodeは`utf-8-sig` strict。
- Decode不能は `SOURCE_ENCODING_ERROR`。

## 10. HTML本文抽出共通アルゴリズム

`html_file` とEPUB内XHTMLは同じ`html_dom.py`決定論的DOM→Raw Text Utilityを使う。

### 10.1 Content Root

Parse後、次の順でRootを1つ選ぶ。

1. `<article>` が文書内にExactly 1件 -> そのElement。
2. それ以外で `<main>` がExactly 1件 -> そのElement。
3. それ以外 -> `<body>`。
4. `<body>`不存在 -> `SOURCE_PARSE_ERROR`。

Readability等の外部本文推定Libraryはv1で使わない。

### 10.2 除外Element

Root配下から次をSubtreeごと除外する。

```text
script
style
noscript
template
svg
canvas
nav
header
footer
aside
form
```

BeautifulSoup Tree上で対象Tagを`decompose()`してから本文Walkする。

### 10.3 DOM→raw_text

DOMをDocument Orderで1回だけWalkしText Nodeを重複なく出力する。

- `NavigableString`: 文字列をそのまま出力。HTML EntityはParser Decode後の文字。
- `<br>`: 単一 `\n`。
- `<ruby>`: `rt/rp` Subtreeを除外しSurface Textだけ出力。
- `<hr>`: 文字を出力せず、現在のraw code point offsetを`scene_break_offsets_raw`へ記録する。
- Block Elementの開始/終了ではParagraph Boundary Candidateを出す。

Block Element集合:

```text
address article blockquote div dl fieldset figure
h1 h2 h3 h4 h5 h6
li main ol p pre section table ul
```

最終Serializationで:

- Paragraph Boundary Candidateの連続は1つに畳む。
- Paragraph間はExactly `\n\n`。
- `<br>`由来の単一LFはParagraph内に保持。
- 空Paragraphは出力しない。
- 先頭/末尾Paragraph Boundaryは除去。

このUtilityはCanonical Normalizationを行わない。ASCII trailing space、NFC、空行縮約等は02へ任せる。

## 11. html_file Adapter

追加Network Accessなし。

- Section 10でRoot/Raw Text/Scene Break Hintを生成。
- `external_episode_id = "1"`。
- Work/Episode Title = 非空`<title>` Text → filename stem fallback。
- Authorは自動推定せずNULL。
- Raw Textが空なら `SOURCE_EMPTY`。

`BeautifulSoup`へUpload Bytesを直接渡し、宣言Charset/BOMをLibraryのdecode処理へ任せる。最終`raw_text`はPython `str`。

## 12. epub Adapter

- DRMなしEPUBのみ。
- `zipfile.ZipFile`でArchive Open。
- `META-INF/container.xml`を`xml.etree.ElementTree`でParseしOPF Pathを解決。
- OPF Manifest/SpineをElementTreeでParse。
- Spine順に1 Spine Document = 1 Episode。
- Navigation/CoverだけのItemは除外。
- `external_episode_id = "spine:{1-based-order}"`。
- Episode Title = Navigation Label → 最初の非空`h1..h6` → `Episode {n}` fallback。
- Work Title/Author = EPUB Metadata → filename stem/NULL fallback。
- 各Spine XHTMLはSection 10 UtilityでRaw Text化。
- 同じUpload SourceSnapshotを複数Episodeが参照してよい。

ZIP PathはPOSIX相対PathとしてOPF所在Directory基準で`posixpath.normpath`解決する。`..`解決後にArchive Root外を指すPathは`SOURCE_PARSE_ERROR`。

EPUB3 Navigation DocumentはManifest `properties`に`nav`を含むItemを使用する。EPUB2 NCXがある場合はSpine `toc`参照先を使用する。Navigation Labelを取得できなくてもHeading/Fallbackへ進み、Import全体を失敗させない。

## 13. Duplicate / Re-import

同一 `(source_type, external_work_id)` はExisting Workを返す。

変更ファイルはBytes Hashが変わるため新Source/New Reference WorkとしてImportする。v1では既存Reference WorkへRefresh/Replaceしない。

Duplicate RaceはDB Unique Constraint競合後にExisting Source/Workを再取得して同じ200 Responseへ収束させる。

## 14. Purge

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

## 15. Error

```text
SOURCE_TYPE_UNSUPPORTED
SOURCE_TOO_LARGE
SOURCE_PARSE_ERROR
SOURCE_ENCODING_ERROR
SOURCE_EMPTY
```

Network Error系はv1に存在しない。

## 16. Test

- API Runtime Dependencyは`beautifulsoup4>=4.13,<5.0`。
- HTML/XHTML Parser backend=`html.parser`。
- `lxml/html5lib/ebooklib`非依存。
- TXT/HTML/EPUB Identity = Upload SHA-256。
- New -> 201同期、Jobなし。
- Duplicate -> 200、Parse/Persistなし。
- Duplicate Race -> Existing Reuse。
- Upload Limit/EPUB selected uncompressed total/Encoding/Parse Error。
- HTML Root Selection article→main→body。
- HTML除外Element。
- DOM WalkでText重複なし。
- Block Boundary / br / ruby / hr Serialization。
- EPUB container.xml/OPF/Spine/Nav/NCX/Metadata/Title fallback。
- Adapter ParseとNormalization責務分離。
- Same Normalization Input -> TextRevision Reuse。
- Same Raw TextでもHint変更 -> New TextRevision。
- New Current Text -> Current Structure Clear。
- All-or-Nothing Persistence。
- Purge Cascade。

## 17. Codex禁止事項

- Narou/Kakuyomu/Generic Network Downloader追加。
- Remote URL Import追加。
- Refresh機能追加。
- Readability等を独断導入して本文抽出規則を変更。
- `lxml/html5lib/ebooklib`を独断追加。
- HTML Parser Backend変更。
- Local File ImportをJob化。
- Upload Staging Table追加。
- Adapter内へCanonical Normalizationを実装。
- Duplicate用No-op Job追加。
- Source/Work Many-to-many化。
- Raw Text一致だけでTextRevision Reuse。
- Current Text二重管理。
- MCP Tool追加。
