# 01 Source Ingestion 詳細設計

## 1. 目的

外部小説・手持ちテキストを、後段の解析が再現可能な `SourceSnapshot` として取り込む。取得処理は解析処理から分離し、サイト仕様変更・通信失敗が分析済みデータを直接破壊しない構造にする。

上位仕様は `../basic-design.md`。本書の決定事項をCodex実装時の承認済み仕様とする。

## 2. 実装境界

ネットワークアクセスはCOREに入れない。COREは不変snapshotの保存・参照だけを担当し、HTTP取得とサイト固有HTML解析はAPI層に置く。

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

既存 `database.py`、Project Registry、authoring tableの責務は変更しない。

## 3. 対応ソース

| source_type | 入力 | 通信 |
|---|---|---|
| `narou` | 作品URLまたはNコード | あり |
| `kakuyomu` | 作品URL | あり |
| `text` | UTF-8 text file | なし |
| `html_file` | 保存済みHTML | なし |
| `epub` | DRMなしEPUB | なし |

汎用 `remote_html` はv1では実装しない。

## 4. 取得ポリシー

ユーザーが明示指定した作品・fileだけを取り込む。法的権利判定はアプリケーション責務にしない。

禁止:

- サイト全体crawl/検索結果一括収集
- login/CAPTCHA/access control/有料表示の回避
- 許可host外への汎用fetch

UIに短い注意文は表示可。ただし `rights_basis`、確認checkbox、毎回の同意recordは必須にしない。明示Purgeを提供する。

## 5. SourceAdapter契約

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
    async def import_work(self, request: SourceRequest) -> ImportBundle: ...
```

AdapterはDBへ書かない。

## 6. Snapshot / Catalog

`FetchedResource.payload` は元resource bytes。hashもbytesに対して計算する。

`SourceSnapshot` はimmutable。`ReferenceWork` / `ReferenceEpisode` はcurrent catalog projectionなのでrefresh時にtitle/order/latest snapshot pointerを更新可能。過去本文はTextRevisionで保持する。

`ImportedEpisode.resource_external_key` から元Snapshotを特定する。EPUBでは複数episodeが同じ元EPUB resource keyを参照してよい。

## 7. HTTP共通仕様

`httpx.AsyncClient`。

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

Adapterのhost allowlistをredirect後も検証する。固定host Adapterに重複したprivate-IP判定は追加しない。

## 8. なろうAdapter

許可host: `ncode.syosetu.com`, `api.syosetu.com`。

- Nコード正規化
- metadata/掲載話数は取得可能な範囲で公式API利用
- 公開episode pageだけ逐次取得
- episode URL/order保持
- 前書き/本文/後書き分離、`raw_text` は本文のみ
- 本文要素一意特定不能は `SOURCE_PARSE_ERROR`

fixture根拠のある少数selector候補だけ実装する。

## 9. カクヨムAdapter

許可host: `kakuyomu.jp`。

- work ID抽出
- 公開episode一覧/本文を順番に取得
- login/有料/本文取得不能を迂回しない
- title/author/episode title/order/URL保持
- 本文一意特定不能は `SOURCE_PARSE_ERROR`

## 10. Local Adapter

### text

UTF-8/UTF-8 BOM。その他encodingは `SOURCE_ENCODING_ERROR`。1 file=1 episode。

### html_file

追加network取得なし。script/style/nav/form除外。主要本文特定不能はparse error。

### epub

DRMなし。`ebooklib` 使用。spine順。navigation/cover除外。title fallback `Episode {n}`。Snapshotには元EPUB bytesを保存。

## 11. Import job / transaction

`style_imports` と `style_jobs` のqueue recordはfetch開始前に短いtransactionで作成する。これがjob statusの正本になる。

network fetch中はDB transactionを開き続けない。

成功時:

1. queued import/job作成・commit
2. workerがimport/jobをrunningへ更新・commit
3. Adapterがfetch/parseして `ImportBundle` 生成
4. catalog persistence transaction開始
5. Source/Snapshot insert/reuse
6. ReferenceWork/ReferenceEpisode upsert
7. episode TextRevision作成/reuse
8. import/job succeededへ更新してcommit

fetch/parse失敗時はcatalog persistenceを開始せず、import/jobだけfailedへ更新する。部分Reference catalogや部分Snapshotを残さない。

### Refresh時episode order更新

`style_reference_episodes` は `(reference_work_id,order_index)` unique。既存episodeをreorderする場合は1 transaction内で:

1. 対象workの既存 `order_index` に十分大きいtemporary offsetを加える
2. external_episode_idで各episodeをfinal orderへupdate/insert
3. 今回sourceから消えたepisodeをReferenceEpisode catalogからDELETE

削除ReferenceEpisodeに属するStyle Document/TextRevisionはcascadeする。一方、既に保存済み `SourceSnapshot` はSourceの取得履歴として残し、Reference Work全体をPurgeした時にSourceとともに削除する。refreshのたびに過去Snapshotを個別GCしない。

このrefresh処理にepisodeごとの確認dialogは設けない。

## 12. API

```text
POST /projects/{project_id}/style-analysis/imports
POST /projects/{project_id}/style-analysis/imports/file
GET  /projects/{project_id}/style-analysis/imports/{import_id}
GET  /projects/{project_id}/style-analysis/reference-works
GET  /projects/{project_id}/style-analysis/reference-works/{work_id}
POST /projects/{project_id}/style-analysis/reference-works/{work_id}/refresh
DELETE /projects/{project_id}/style-analysis/reference-works/{work_id}
```

network importは202 + job ID。

## 13. Error code

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

本文をerror messageへ含めない。

## 14. Test

- Narou index/episode/前後書き
- Narou DOM欠損
- Kakuyomu複数episode/本文欠損
- redirect host逸脱
- 429 retry
- size超過
- UTF-8 BOM/非UTF-8
- EPUB spine/binary hash
- failed fetchでcatalog未更新
- refresh reorder unique collisionなし
- sourceから消えたepisodeのDocument cascade + Snapshot保持

## 15. Codex禁止事項

- 001〜005変更
- 汎用crawler/headless browser
- access restriction回避
- 空本文success
- MCP tool追加
- fixture根拠なしfallback大量追加
- network fetch中の長時間DB transaction