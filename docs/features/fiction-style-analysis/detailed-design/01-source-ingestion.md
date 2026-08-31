# 01 Source Ingestion 詳細設計

## 1. 目的

外部小説・手持ちTextを再現可能なSourceSnapshotとして取り込み、Reference Work/EpisodeとStyleDocumentのCurrent TextRevisionを更新する。取得処理は解析処理から分離する。

上位仕様は `../basic-design.md`。

## 2. 実装境界

```text
CORE/src/novel_core/style_analysis/
  source_models.py
  source_repository.py

API/src/novel_api/style_analysis/
  ingestion_service.py
  source_fetcher.py
  adapters/
    base.py
    narou.py
    kakuyomu.py
    text.py
    html_file.py
    epub.py
```

NetworkはAPI層。COREはDB/Domainのみ。

## 3. Source Type

```text
narou
kakuyomu
text
html_file
epub
```

汎用Remote HTML/Crawlerはv1対象外。

## 4. 取得方針

ユーザーが明示指定した作品/Fileだけ取り込む。

実装しない:

- Site全体Crawl
- Login/CAPTCHA/Access Control/有料表示の回避
- 許可Host外への汎用Fetch

rights_basis、毎回の同意Checkbox/Recordは必須にしない。

## 5. SourceAdapter

09の単一同期Workerに合わせ同期API。

```python
@dataclass(frozen=True)
class SourceRequest:
    source_type: str
    locator: str

@dataclass(frozen=True)
class FetchedResource:
    resource_kind: str
    external_key: str
    canonical_url: str | None
    media_type: str
    payload: bytes
    status_code: int | None
    etag: str | None
    last_modified: str | None

@dataclass(frozen=True)
class ImportedEpisode:
    external_episode_id: str
    title: str
    order_index: int
    source_url: str | None
    resource_external_key: str
    raw_text: str
    metadata: dict[str, object]

@dataclass(frozen=True)
class ImportedWork:
    external_work_id: str
    title: str
    author_name: str | None
    source_url: str | None
    metadata: dict[str, object]
    episodes: tuple[ImportedEpisode, ...]

@dataclass(frozen=True)
class ImportBundle:
    resources: tuple[FetchedResource, ...]
    work: ImportedWork

class SourceAdapter(Protocol):
    def validate_locator(self, locator: str) -> None: ...
    def import_work(self, request: SourceRequest) -> ImportBundle: ...
```

AdapterはDBへ書かない。

## 6. Snapshot / Catalog / Current Text

- `FetchedResource.payload` は元Bytes。HashもBytes基準。
- SourceSnapshotはImmutable。
- ReferenceWork/ReferenceEpisodeはCurrent Catalog ProjectionでMetadata/Order/Latest Snapshot Pointer更新可。
- Current解析本文の正本は **StyleDocument.current_text_revision_id**。
- ReferenceEpisode Rowへ別のCurrent Text Pointerを持たない。
- Work一括解析はEpisode→StyleDocument→Current TextRevisionを読む。

Import/Refreshで新しいTextRevisionがCurrentになった時:

1. `style_documents.current_text_revision_id` を新Revisionへ更新。
2. 同Documentの `current_structure_revision_id` をNULLへClear。
3. 過去Text/Structure/Runは削除しない。

同じCanonical/Raw入力が既存Current Revisionと同一で新Revision作成不要ならPointerもStructureも変更しない。

## 7. HTTP共通仕様

`httpx.Client`。

```text
connect timeout: 10 sec
read timeout: 30 sec
max redirects: 5
max response bytes/page: 5 MiB
retry: 429,502,503,504 最大2回
backoff: 1 sec, 3 sec
same-host interval: 1.0 sec
concurrency/import: 1
```

User-Agent: `NovelProduction-StyleAnalysis/1.0 (local analysis)`。

Redirect後もAdapter Host Allowlistを検証する。

## 8. Narou / Kakuyomu

Narou許可Host: `ncode.syosetu.com`, `api.syosetu.com`。

- Nコード正規化
- Metadataは利用可能な公式APIを優先
- Public Episodeを順次取得
- 前書き/本文/後書き分離、解析Raw Textは本文のみ

Kakuyomu許可Host: `kakuyomu.jp`。

- Work ID/Episode一覧/本文を取得
- Restricted/Login-required本文を迂回しない

本文一意特定不能は `SOURCE_PARSE_ERROR`。

## 9. Local Adapter

- text: UTF-8/UTF-8 BOM、1 File=1 Episode
- html_file: Networkなし、主要本文抽出
- epub: DRMなし、Spine順、元EPUB BytesをSnapshot保存

## 10. Initial Import Job

Initial Importは `source_import` Job。

`style_imports` は受付記録だけ:

```text
id
source_type
locator
job_id
created_at
```

状態・Error・Progressは `style_jobs` を正本とし二重管理しない。

Flow:

1. Job + Import受付Rowを短Transactionで作成/Commit
2. Worker Claim
3. Network Fetch/Parse（DB Transaction外）
4. Persistence Transaction
5. Source/Snapshot/Catalog/Document/TextRevision Insert/Reuse
6. Current Text Pointer更新、必要ならCurrent Structure Clear
7. Job Succeeded + Commit

Fetch/Parse失敗時はCatalogを部分更新しない。

## 11. Refresh Job

Refreshは `source_refresh` Job。Import Rowは作らない。

Episode ReorderはUnique衝突を避けるため同TransactionでTemporary Offset→Final Order。

Sourceから消えたEpisode:

- ReferenceEpisode DELETE
- Document/Text/AnalysisはCascade
- SourceSnapshotはWork全体Purgeまで保持

既存Episode本文が変わった場合だけ新TextRevisionを作成してCurrent Pointer更新/Structure Clear。

## 12. Purge

Reference Work DELETEは12 Service Transaction。

- Work/Episode/Document/Entity/Term/Membership削除
- 他Workが参照しない専用SourceならSource/Snapshot削除

通常の削除確認1回でよい。

## 13. Error Code

```text
SOURCE_LOCATOR_INVALID
SOURCE_HOST_NOT_ALLOWED
SOURCE_HTTP_ERROR
SOURCE_RATE_LIMITED
SOURCE_TOO_LARGE
SOURCE_PARSE_ERROR
SOURCE_ENCODING_ERROR
SOURCE_ACCESS_RESTRICTED
SOURCE_IMPORT_INCOMPLETE
```

## 14. Test

- Narou/Kakuyomu Success/Parse Failure
- Redirect Host/429/Size
- EPUB Binary Hash
- Sync Adapter
- Initial Import: style_importsはJob参照のみ
- Fetch FailureでCatalog未更新
- New Text RevisionでDocument Current Text更新 + Structure Clear
- Same Text ReuseでPointer/Structure不変
- Refresh Reorder
- Removed Episode Cascade + Snapshot保持
- Purge専用Source/Snapshot削除

## 15. Codex禁止事項

- Async Event Loop追加
- Network中の長Transaction
- Current TextをReferenceEpisodeとStyleDocumentで二重管理
- Import Status/ErrorをJobと二重管理
- 空本文Success
- Generic Crawler/Access Restriction回避
- MCP Tool追加
