# 01 Source Ingestion 詳細設計

## 1. 目的

外部小説・手持ちテキストを、後段の解析が再現可能な `SourceSnapshot` として取り込む。取得処理は解析処理から分離し、サイト仕様変更・通信失敗が分析済みデータを直接破壊しない構造にする。

上位仕様は `../basic-design.md`。本書の決定事項をCodex実装時の承認済み仕様とする。

## 2. 実装境界

Network AccessはCOREに入れない。COREはSnapshot/Catalog persistenceを担当し、HTTP取得とSite固有HTML解析はAPI層に置く。

```text
CORE/src/novel_core/style_analysis/
  source_models.py
  source_repository.py

API/src/novel_api/style_analysis/
  ingestion_service.py
  source_fetcher.py
  adapters/
    __init__.py
    base.py
    narou.py
    kakuyomu.py
    text.py
    html_file.py
    epub.py
```

既存 `database.py`、Project Registry、Authoring tableの責務は変更しない。

## 3. 対応Source

| source_type | 入力 | 通信 |
|---|---|---|
| `narou` | 作品URLまたはNコード | あり |
| `kakuyomu` | 作品URL | あり |
| `text` | UTF-8 Text File | なし |
| `html_file` | 保存済みHTML | なし |
| `epub` | DRMなしEPUB | なし |

汎用 `remote_html` はv1では実装しない。

## 4. 取得ポリシー

ユーザーが明示指定した作品/Fileだけを取り込む。法的権利判定はアプリケーション責務にしない。

禁止:

- Site全体crawl/検索結果一括収集
- Login/CAPTCHA/Access Control/有料表示の回避
- 許可Host外への汎用Fetch

UIに短い注意文は表示可。ただし `rights_basis`、確認checkbox、毎回の同意recordは必須にしない。明示Purgeを提供する。

## 5. SourceAdapter契約

v1のJob Workerは09で単一同期worker threadとするため、Adapterも同期APIに固定する。

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

## 6. Snapshot / Catalog

`FetchedResource.payload` は元resource bytes。Hashもbytesに対して計算する。

`SourceSnapshot` はimmutable。

`ReferenceWork` / `ReferenceEpisode` はcurrent catalog projectionなのでRefresh時にtitle/order/latest snapshot pointerを更新可能。過去resource bytesはSnapshot、解析本文履歴はTextRevisionで扱う。

`ImportedEpisode.resource_external_key` から元Snapshotを特定する。EPUBでは複数Episodeが同じ元EPUB resource keyを参照してよい。

## 7. HTTP共通仕様

`source_fetcher.py` は `httpx.Client` を使う。`AsyncClient` は使わない。同時実行1のworker threadなので非同期化の利点がなく、event loop管理を増やさないためである。

```text
connect timeout: 10 sec
read timeout: 30 sec
max redirects: 5
max response bytes/page: 5 MiB
retry: 429,502,503,504 最大2回
backoff: 1 sec, 3 sec
concurrency/import: 1
same-host minimum interval: 1.0 sec
```

User-Agent: `NovelProduction-StyleAnalysis/1.0 (local analysis)`。

AdapterのHost AllowlistをRedirect後も検証する。固定Host Adapterに重複したPrivate-IP判定は追加しない。

## 8. なろうAdapter

許可Host: `ncode.syosetu.com`, `api.syosetu.com`。

- Nコード正規化
- Metadata/掲載話数は取得可能な範囲で公式API利用
- 公開Episode pageだけ逐次取得
- Episode URL/order保持
- 前書き/本文/後書き分離、`raw_text` は本文のみ
- 本文要素一意特定不能は `SOURCE_PARSE_ERROR`

Fixture根拠のある少数Selector候補だけ実装する。

## 9. カクヨムAdapter

許可Host: `kakuyomu.jp`。

- Work ID抽出
- 公開Episode一覧/本文を順番に取得
- Login/有料/本文取得不能を迂回しない
- Title/Author/Episode title/order/URL保持
- 本文一意特定不能は `SOURCE_PARSE_ERROR`

## 10. Local Adapter

### text

UTF-8/UTF-8 BOM。その他Encodingは `SOURCE_ENCODING_ERROR`。1 File = 1 Episode。

### html_file

追加Network取得なし。script/style/nav/form除外。主要本文特定不能はParse Error。

### epub

DRMなし。`ebooklib` 使用。Spine順。Navigation/Cover除外。Title fallback `Episode {n}`。Snapshotには元EPUB bytesを保存。

## 11. Import Job / Transaction

Initial Importは09 `source_import` Job。

`style_imports` と `style_jobs` のqueue recordはFetch開始前に短いtransactionで作成する。

Network Fetch中はDB transactionを開き続けない。

成功時:

1. queued Import/Job作成・commit
2. WorkerがImport/Jobをrunningへ更新・commit
3. DB connectionをtransaction外状態にしてAdapter Fetch/Parse
4. `ImportBundle` 生成
5. Catalog persistence transaction開始
6. Source/Snapshot insert/reuse
7. ReferenceWork/ReferenceEpisode upsert
8. Episode TextRevision作成/reuse
9. Import/Job succeededへ更新してcommit

Fetch/Parse失敗時はCatalog persistenceを開始せず、Import/Jobだけfailedへ更新する。部分Reference Catalogや部分Snapshotを残さない。

## 12. Refresh

Refreshは09 `source_refresh` JobとしてInitial Importと分離する。`style_imports` rowは新規作成しない。Job payloadに `reference_work_id` を入れる。

RefreshもNetwork Fetch中に長時間transactionを開かない。

### Episode order更新

`style_reference_episodes` は `(reference_work_id,order_index)` unique。

1 transaction内で:

1. 対象Workの既存 `order_index` に十分大きいtemporary offsetを加える
2. `external_episode_id` で各Episodeをfinal orderへupdate/insert
3. 今回Sourceから消えたEpisodeをReferenceEpisode CatalogからDELETE

削除ReferenceEpisodeに属するStyle Document/TextRevisionはcascadeする。

既存 `SourceSnapshot` はSourceの取得履歴として残し、Reference Work全体Purge時にSourceとともに削除する。Refreshのたびに過去Snapshotを個別GCしない。

RefreshにEpisodeごとの確認dialogは設けない。

## 13. Purge

Reference Work削除は12のPurge transactionを使用する。

- Work/Episode/Document/Entity/Term/Corpus Membershipを削除
- そのWork専用SourceならSource/Snapshotも削除
- 他Reference Workが同Sourceを参照していればSourceは残す

通常の削除確認1回でよい。

## 14. API

```text
POST /projects/{project_id}/style-analysis/imports
POST /projects/{project_id}/style-analysis/imports/file
GET  /projects/{project_id}/style-analysis/imports/{import_id}
GET  /projects/{project_id}/style-analysis/reference-works
GET  /projects/{project_id}/style-analysis/reference-works/{work_id}
POST /projects/{project_id}/style-analysis/reference-works/{work_id}/refresh
DELETE /projects/{project_id}/style-analysis/reference-works/{work_id}
```

- Initial Network/File Import: `202 + import_id + job_id`
- Refresh: `202 + job_id`
- Purge: synchronous DB transaction、成功204

## 15. Error Code

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

本文をError Messageへ含めない。

## 16. Test

- Narou index/episode/前後書き
- Narou DOM欠損
- Kakuyomu複数Episode/本文欠損
- Redirect Host逸脱
- 429 Retry
- Size超過
- UTF-8 BOM/非UTF-8
- EPUB Spine/Binary Hash
- Adapterが同期APIであること
- Failed FetchでCatalog未更新
- Refreshがsource_refresh Job
- Refresh reorder unique collisionなし
- Sourceから消えたEpisodeのDocument cascade + Snapshot保持
- Work Purgeで専用Source/Snapshot削除

## 17. Codex禁止事項

- 001〜005変更
- 汎用Crawler/Headless Browser
- Access Restriction回避
- 空本文Success
- MCP Tool追加
- Fixture根拠なしFallback大量追加
- Network Fetch中の長時間DB transaction
- 単一workerのためだけにAsyncClient/event loop管理を追加
