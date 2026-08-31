# 01 Source Ingestion 詳細設計

## 1. 目的

外部小説・手持ちテキストを、後段の解析が再現可能な `SourceSnapshot` として取り込む。取得処理は解析処理から分離し、サイト仕様変更・利用条件変更・通信失敗が分析データを直接破壊しない構造にする。

上位仕様は `../basic-design.md`。本書の決定事項をCodex実装時の承認済み仕様とする。

## 2. 実装境界

ネットワークアクセスは CORE に入れない。CORE は不変snapshotの保存・参照だけを担当し、HTTP取得とサイト固有HTML解析は API 層に置く。

実装先を以下に固定する。

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

CORE既存の `database.py`、project registry、既存authoringテーブルの責務は変更しない。

## 3. 対応ソース

初期実装の `source_type` は次で固定する。

| source_type | 入力 | 通信 |
|---|---|---|
| `narou` | 作品URLまたはNコード | あり |
| `kakuyomu` | 作品URL | あり |
| `text` | UTF-8テキストファイル | なし |
| `html_file` | 保存済みHTMLファイル | なし |
| `epub` | DRMなしEPUB | なし |

汎用URLを取得する `remote_html` は実装しない。SSRFと取得条件の不明確化を避けるためである。

## 4. 利用条件と権利確認

外部サイト本文の自動取得はローカル・私的分析用に限定する。UI/APIで最初の取得前に `rights_basis` を必須入力とする。

```text
self_authored
permission_granted
private_personal_use
```

`rights_basis` はsnapshotへ保存する。空値は拒否する。

以下を禁止する。

- サイト全体クロール
- 検索結果からの一括収集
- ログイン回避、アクセス制限回避
- 有料・限定公開本文の取得
- 取得本文の外部公開、MCPレスポンスへの全文露出
- robots/利用条件で明示的に拒否された取得を迂回する実装

2026-09-01時点の設計根拠として、なろう側は外部サービスによる作品データ取り込み・AI解析について公式許諾サービスがない旨を注意喚起しており、なろうデベロッパーAPIも提供データと用途に制限がある。カクヨム利用規約にも私的利用範囲外・営利利用に関する制限がある。したがって「ユーザーが1作品を明示指定し、ローカルで分析する」以外へ機能を拡張しない。

## 5. SourceAdapter契約

`base.py` に次のProtocol/dataclassを定義する。

```python
@dataclass(frozen=True)
class SourceRequest:
    source_type: str
    locator: str
    rights_basis: str

@dataclass(frozen=True)
class FetchedResource:
    resource_kind: str
    external_key: str
    canonical_url: str | None
    media_type: str
    payload: str
    status_code: int | None
    etag: str | None
    last_modified: str | None

@dataclass(frozen=True)
class ImportedEpisode:
    external_episode_id: str
    title: str
    order_index: int
    source_url: str | None
    raw_text: str

@dataclass(frozen=True)
class ImportedWork:
    external_work_id: str
    title: str
    author_name: str | None
    source_url: str | None
    metadata: dict[str, object]
    episodes: tuple[ImportedEpisode, ...]

class SourceAdapter(Protocol):
    def validate_locator(self, locator: str) -> None: ...
    async def import_work(self, request: SourceRequest) -> ImportedWork: ...
```

adapterはDBへ書き込まない。`IngestionService` がadapter結果を一括transactionで永続化する。

## 6. HTTP取得共通仕様

`source_fetcher.py` は `httpx.AsyncClient` を利用する。`httpx` をAPI runtime dependencyへ移す。

固定値:

```text
connect timeout: 10 sec
read timeout: 30 sec
max redirects: 5
max response bytes per page: 5 MiB
retry: 429, 502, 503, 504 のみ最大2回
retry backoff: 1 sec, 3 sec
concurrency per import: 1
minimum interval between same-host requests: 1.0 sec
```

User-Agentは `NovelProduction-StyleAnalysis/1.0 (local personal analysis)` とする。

リダイレクト後も許可hostを再検証する。private IP、localhost、file scheme、非HTTPSへのredirectは拒否する。ただし公式URLがHTTPからHTTPSへredirectする場合のみ初回HTTP入力をHTTPSへ正規化してから取得する。

## 7. なろうAdapter

許可hostは `ncode.syosetu.com` と公式API `api.syosetu.com` のみ。

- locatorからNコードを正規化して大文字保持のexternal IDとする。
- 作品メタデータと掲載話数は、取得可能な範囲では公式「なろう小説API」を優先する。
- 本文は公式APIに本文フィールドが存在しないため、ユーザーが明示した作品について公開エピソードページだけを逐次取得する。
- 目次からepisode URLを抽出し、表示順を `order_index` に保存する。
- 前書き・本文・後書きは混同しない。`raw_text` には本文のみを入れ、前書き・後書きはsnapshot metadataへ保存する。
- 取得途中で失敗した場合、reference workを「完了」として作成しない。取得済みraw resource snapshotは診断用に保存してよいが、import transactionは失敗扱いにする。

サイトCSS class名だけに依存しない。fixtureを正本にし、HTML構造の複数候補selectorを優先順位付きで持つ。本文要素が一意に特定できなければ `SOURCE_PARSE_ERROR` とする。

## 8. カクヨムAdapter

許可hostは `kakuyomu.jp` のみ。

- 作品URLからwork slug/IDを抽出する。
- 作品ページのエピソード一覧を取得し、公開本文ページを順番に1件ずつ取得する。
- ログイン要求、有料表示、本文が取得できないページは迂回しない。
- タイトル、作者名、episode title、順序、URLを保持する。
- 本文要素を特定できない場合は `SOURCE_PARSE_ERROR`。

DOM変更時に誤ってナビゲーションやコメントを本文扱いしないことを優先し、曖昧な場合はfail closedにする。

## 9. ローカルファイルAdapter

### text

- UTF-8/UTF-8 BOMのみ自動受理。
- その他encodingは自動推測せず `SOURCE_ENCODING_ERROR`。
- 1ファイルを1episode、ファイル名stemをtitleとする。

### html_file

- network resourceを追加取得しない。
- script/style/nav/formを除外し、ユーザーが保存した文書内の主要本文候補を抽出する。
- 抽出が一意でなければ、全文を勝手に採用せずparse errorとする。

### epub

- DRMなしEPUBのみ。
- `ebooklib` をAPI runtime dependencyへ追加する。
- spine順をepisode順とし、navigation、cover、copyright pageは本文候補から除外する。
- 章タイトルがなければ `Episode {n}` をfallback titleとする。

## 10. Snapshot永続化

外部取得の各resourceは不変snapshotとして保存する。

最低保持項目:

```text
source_id
resource_kind
external_key
canonical_url
fetched_at
status_code
etag
last_modified
media_type
payload_sha256
raw_payload
adapter_id
adapter_version
rights_basis
```

同一 `canonical_url + payload_sha256` の重複payloadは再利用可能。ただし取得イベント自体を監査したい場合はmetadata recordを新規作成して同じpayload hashを参照する。

Reference Work/Episodeの更新は既存record上書きではなく、新snapshotから新しいTextRevisionを作る。

## 11. API操作

API pathはすべて project scope とする。

```text
POST /projects/{project_id}/style-analysis/imports
GET  /projects/{project_id}/style-analysis/imports/{import_id}
GET  /projects/{project_id}/style-analysis/reference-works
GET  /projects/{project_id}/style-analysis/reference-works/{work_id}
POST /projects/{project_id}/style-analysis/reference-works/{work_id}/refresh
```

`POST imports` はsource_type、locatorまたはupload、rights_basisを受ける。ネットワークimportは長時間処理になり得るため、Analysis Runtimeと同じpersisted job方式を使用し、HTTP responseは `202 Accepted` とjob IDを返す。

## 12. エラーコード

```text
SOURCE_LOCATOR_INVALID
SOURCE_HOST_NOT_ALLOWED
SOURCE_RIGHTS_BASIS_REQUIRED
SOURCE_HTTP_ERROR
SOURCE_RATE_LIMITED
SOURCE_TOO_LARGE
SOURCE_PARSE_ERROR
SOURCE_ENCODING_ERROR
SOURCE_ACCESS_RESTRICTED
SOURCE_IMPORT_INCOMPLETE
```

外部HTML本文をエラーメッセージへ含めない。

## 13. テスト

CIではlive siteへ接続しない。

必須fixture:

- なろう目次1件、複数episode、前書き/後書きあり
- なろうDOM欠損
- カクヨム複数episode
- カクヨム本文要素欠損
- redirect host逸脱
- 429 retry
- 5MiB超過
- UTF-8 BOM text
- 非UTF-8 text拒否
- EPUB spine順

adapter fixtureテストでは、作品名・episode数・順序・本文hashを完全一致で検証する。

## 14. Codex実装時の禁止事項

- 001〜005 migrationを変更しない。
- 汎用Web crawlerを作らない。
- headless browser依存を追加しない。
- CAPTCHA、ログイン、有料壁を回避しない。
- 取得失敗を空本文として成功扱いしない。
- MCP toolを追加しない。
- サイト仕様の推測で大量のfallback selectorを追加しない。fixtureで確認できる構造だけ実装する。
