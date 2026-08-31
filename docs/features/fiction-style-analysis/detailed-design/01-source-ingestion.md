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

CORE既存の `database.py`、Project Registry、authoring tableの責務は変更しない。

## 3. 対応ソース

初期 `source_type` は次で固定する。

| source_type | 入力 | 通信 |
|---|---|---|
| `narou` | 作品URLまたはNコード | あり |
| `kakuyomu` | 作品URL | あり |
| `text` | UTF-8テキストファイル | なし |
| `html_file` | 保存済みHTMLファイル | なし |
| `epub` | DRMなしEPUB | なし |

汎用URLを取得する `remote_html` はv1では実装しない。サイトAdapterを明示的に追加する方式とする。

## 4. 取得ポリシー

本機能はユーザーが明示指定した作品・ファイルだけを取り込む。法的権利判定や利用条件の自動判定はアプリケーションの責務にしない。

v1で禁止する実装は次だけとする。

- サイト全体クロールや検索結果からの一括収集
- ログイン、CAPTCHA、アクセス制限、有料表示の回避
- 許可host外への汎用fetch

UIには「取得元の条件を確認して利用する」旨の短い注意文を表示してよいが、`rights_basis`、確認checkbox、毎回の同意記録は必須にしない。本文削除用の明示Purgeは提供する。

## 5. SourceAdapter契約

Adapterは「取得したresource」と「解析用に抽出した作品構造」の両方を返す。これによりraw snapshot保存と本文抽出結果が分離される。

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

AdapterはDBへ書き込まない。`IngestionService` がbundleを永続化する。

## 6. SnapshotとReference catalog

`FetchedResource.payload` は元resourceのbytesを保持する。HTML/TXTはUTF-8 bytes、EPUBは元zip bytesを保存してよい。hashはbytesに対して計算する。

`SourceSnapshot` はimmutable。一方、`ReferenceWork` / `ReferenceEpisode` は「現在の取得状態を示すcatalog projection」であり、refresh時にtitle、order、latest snapshot pointerを更新してよい。過去本文は既存TextRevisionで保持する。

episodeごとの `resource_external_key` から、どのsnapshotを元に `raw_text` を抽出したか追跡できること。

## 7. HTTP取得共通仕様

`source_fetcher.py` は `httpx.AsyncClient` を使う。`httpx` をAPI runtime dependencyへ追加する。

初期値:

```text
connect timeout: 10 sec
read timeout: 30 sec
max redirects: 5
max response bytes per page: 5 MiB
retry: 429, 502, 503, 504 を最大2回
retry backoff: 1 sec, 3 sec
concurrency per import: 1
minimum interval between same-host requests: 1.0 sec
```

User-Agentは `NovelProduction-StyleAnalysis/1.0 (local analysis)`。

各Adapterが許可hostを持ち、redirect後もhostを再検証する。host allowlistを通る場合に追加のprivate-IP判定等は重ねない。

## 8. なろうAdapter

許可hostは `ncode.syosetu.com` と `api.syosetu.com`。

- locatorからNコードを正規化する。
- 作品メタデータ・掲載話数は取得可能な範囲で公式APIを利用する。
- 本文はユーザー指定作品の公開episode pageだけを逐次取得する。
- 目次からepisode URLを抽出し、表示順を `order_index` に保存する。
- 前書き・本文・後書きを分離し、`raw_text` には本文だけを入れる。
- HTML本文要素が一意に特定できなければ `SOURCE_PARSE_ERROR`。

CSS class名1個だけへ依存せず、fixtureで確認した少数のselector候補を優先順位付きで実装する。

## 9. カクヨムAdapter

許可hostは `kakuyomu.jp`。

- 作品URLからwork IDを抽出する。
- 公開episode一覧を取得し、本文pageを順番に取得する。
- ログイン要求・有料表示・本文取得不能pageは迂回しない。
- title、author、episode title、order、URLを保持する。
- 本文要素を一意に特定できなければ `SOURCE_PARSE_ERROR`。

## 10. ローカルファイルAdapter

### text

- UTF-8/UTF-8 BOMを受理する。
- その他encodingは自動推測せず `SOURCE_ENCODING_ERROR`。
- 1 fileを1episode、filename stemをtitleとする。

### html_file

- network resourceを追加取得しない。
- script/style/nav/formを除外し、主要本文候補を抽出する。
- 主要本文候補が特定できなければ `SOURCE_PARSE_ERROR`。

### epub

- DRMなしEPUBのみ。
- `ebooklib` をAPI runtime dependencyへ追加する。
- spine順をepisode順とする。
- navigation、cover等を本文episodeから除外する。
- chapter titleがなければ `Episode {n}`。
- snapshot payloadには元EPUB bytesを保存する。

## 11. Import transaction

network fetch中はDB transactionを開き続けない。

処理順:

1. Adapterがfetch/parseして `ImportBundle` を生成
2. DB transaction開始
3. Source/Snapshotをinsertまたは再利用
4. ReferenceWork/ReferenceEpisode catalogをupsert
5. episodeごとにTextRevisionを作成または既存hashを再利用
6. import statusをsucceededに更新してcommit

fetch途中で失敗した場合はReference catalogを部分更新しない。診断用の部分resource保存はv1では行わず、再実行で取り直す。これにより中間状態を減らす。

## 12. API操作

```text
POST /projects/{project_id}/style-analysis/imports
POST /projects/{project_id}/style-analysis/imports/file
GET  /projects/{project_id}/style-analysis/imports/{import_id}
GET  /projects/{project_id}/style-analysis/reference-works
GET  /projects/{project_id}/style-analysis/reference-works/{work_id}
POST /projects/{project_id}/style-analysis/reference-works/{work_id}/refresh
DELETE /projects/{project_id}/style-analysis/reference-works/{work_id}
```

network importはpersisted jobを使い `202 Accepted` を返す。

## 13. エラーコード

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

外部HTML本文をerror messageへ含めない。

## 14. テスト

必須fixture:

- なろう目次/複数episode/前書き後書き
- なろうDOM欠損
- カクヨム複数episode
- カクヨム本文要素欠損
- redirect host逸脱
- 429 retry
- response size超過
- UTF-8 BOM text
- 非UTF-8 text拒否
- EPUB spine順とbinary snapshot hash

adapter fixtureではtitle、episode数、order、本文hash、resource hashを検証する。

## 15. Codex実装時の禁止事項

- 001〜005 migrationを変更しない。
- 汎用Web crawlerを作らない。
- headless browser依存を追加しない。
- CAPTCHA、ログイン、有料壁を回避しない。
- 取得失敗を空本文で成功扱いしない。
- MCP toolを追加しない。
- fixture根拠のない大量fallback selectorを追加しない。