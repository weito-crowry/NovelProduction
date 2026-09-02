# 16 External Agent MCP / ChatGPT Analysis 詳細設計

## 1. 位置付けと正本

本書は Fiction Style Analysis v1.1 の SA-I extension、External Agent MCP /
ChatGPT Analysis の実装正本である。v1.0 の Text、Structure、Semantic、Metric、
Current Run、Review、Override、Aggregate、Profile、Lint、WebUI 契約は変更しない。
v1.0 の MCP 59 tools は過去契約として保持し、本 extension 適用後の inventory は
65 tools とする。

承認済み Architecture は次のとおりである。

```text
Internal: DocumentAnalysisOrchestrator -> ResumableDocumentAnalysisEngine
          -> Internal ModelClient -> shared validation / reduction / apply
External: ChatGPT -> MCP -> API ExternalAnalysisService
          -> ResumableDocumentAnalysisEngine -> persistent Model Task
          -> ChatGPT submits JSON -> shared validation / reduction / apply
```

NovelProduction は ChatGPT/OpenAI API を呼ばない。callback、webhook、OpenAI SDK、
API key、ChatGPT session token、parallel model task は存在しない。External session
は pull/status と submit のみで進む。

## 2. Layer responsibility

CORE は transaction-neutral な resumable state machine、Prepared/Completed Model
Call、Prompt/Response Contract、validation、reduction、domain apply、AnalysisRun、
External Session/Task の model/repository、runtime fingerprint、execution conflict
checker を所有する。CORE は FastAPI、Pydantic、MCP、httpx、novel_api を import
しない。

API は Project DB の open/close、External transaction、start/get/list/submit/cancel
service、Project Draft Capture、HTTP schema/route、error mapping、既存 Job
enqueue/retry conflict を所有する。API 側も server-side model call を行わない。

MCP は既存 `api_client.py` を使う HTTP mapping、tool schema、description、annotation
だけを所有する。MCP は CORE、API、FastAPI、sqlite3 を import せず、Prompt/Context/
Validator/ID/Candidate selection を実装しない。

## 3. Shared Resumable Engine

`ResumableDocumentAnalysisEngine.advance(request, cursor, completed_call)` は一回に
次のどちらかだけを返す。

- `pending_call` が一件あり、`result` は `null`
- `pending_call` が `null` で、terminal `result` が一件ある

Engine は model provider を呼ばず、commit/rollback もしない。checkpoint callback
だけを呼ぶ。Internal driver は既存 ModelClient と safe point、External driver は
API outer transaction と persistent Task を注入する。Public な
`DocumentAnalysisOrchestrator.analyze_document(...)` の signature は変更しない。

`PreparedModelCall` は call key、AnalysisRun、Analyzer/Prompt id/version、
`response_contract_id`、system prompt、user payload、response schema を持つ。
`CompletedModelCall` は response と error の exactly-one invariant を持つ。
Cursor は `schema_version=1` の小さい JSON 値だけを保存し、全文、巨大 request、
Python object、generator、pickle、callable は保存しない。Pending request の正本は
Task row である。

Full document の 15 stages は順に次のとおりで、`stage_index` は 1-based である。

```text
1 structure_prepare      6 speaker_attribution  11 scene_semantics
2 scene_boundary         7 pov                   12 block_semantics
3 structure_finalize     8 term_candidates      13 semantic_metrics
4 entity_mentions        9 term_resolver         14 basic_metrics
5 entity_resolver        10 term_explanation     15 finalize
```

Boundary/mention/term-candidate/scene-semantic classify は Scene x Chunk、resolver
は unresolved subject、speaker は Dialogue Block、POV は Scene、term explanation
は TermMention、block semantic は Narration Block 単位である。Scene semantic の
複数 chunk は既存 Reduce Call を使用し、Metrics は既存 CORE calculation を使う。
Boundary apply、dedup、dynamic registry、fallback、confidence/reason merge、
Partial/Failed 規則は v1.0 と同じである。

### 3.1 Response Contract Registry

`model_output_contracts.py` には次の 11 contract ID を登録する。

```text
style.scene_boundary.v1
style.entity_mentions.v1
style.entity_resolution.v1
style.speaker_attribution.v1
style.term_candidates.v1
style.term_resolution.v1
style.term_explanation.v1
style.scene_semantics.classify.v1
style.scene_semantics.reduce.v1
style.block_semantic.v1
style.pov.v1
```

各 entry は response schema guide と repairable validator を持ち、既存 Analyzer の
validator/reducer/domain conversion を参照する。External 専用の Analyzer、
Validator、Reducer は作らない。

Repairable validation は既存 `complete_validated_json()` と同じ境界だけである。
consumer/domain validation error は repair に昇格させない。Repair は initial と
repair の最大 2 attempts。repair system prompt は CORE の既存
`REPAIR_SYSTEM_PROMPT` を共有し、payload は `original_request`、canonical JSON
string の `invalid_response`、`validation_errors` とする。Transport malformed
JSON は API/MCP で reject し、CORE repair attempt に数えない。

## 4. Runtime and Policy contract

Session 作成時に current runtime contract の canonical JSON SHA-256 fingerprint を
保存する。payload は engine contract version、全 Analyzer id/version、Prompt
id/version、11 Response Contract ID、scene/block/POV taxonomy、全 Metric
name/version、structure segmenter id/version、chunking contract version、current
chunk max code points を含む。submit 時に異なれば fail closed する。

Session request JSON には schema version、target、executor model、rebuild flag、
`AnalysisPolicy` dataclass 全 field を canonical JSON で保存する。resume は current
default を再生成せず保存済み Policy を復元する。

AnalysisRun の `state_fingerprint` と `policy_input_fingerprint` は run 作成時の
正本である。submit 前に既存 `CurrentRunResolver` の state reconstruction helper
で再計算し、Relevant input が変われば `EXTERNAL_ANALYSIS_INPUT_CHANGED` として
response を保存したうえで Session/created running Run を failed にする。Resolver
が生成した未確認 Identity/Alias の自然成長は v1.0 の state semantics に従い drift
としない。

## 5. Persistent storage (`009_style_analysis_external_agent.sql`)

001〜008 の bytes は変更しない。SA-I の追加 migration はこの 009 一つだけで
ある。JSON は `canonical_json_bytes`、fingerprint は lowercase SHA-256 を使う。

### 5.1 Sessions

`style_external_analysis_sessions` は id、document/reference_work target、executor
provider/model、runtime fingerprint、status、request/snapshot/cursor/result/warning
JSON、version、error、timestamps、finished_at を保持する。provider は
`chatgpt_mcp` のみ、target は exactly one、status は
`active|succeeded|partial|failed|cancelled`。JSON valid、fingerprint length 64、
version >= 1、active は finished_at NULL、terminal は finished_at non-NULL を DB
CHECK で保証する。status/id、document/status、reference_work/status index を持つ。

Document snapshot は target kind、document、text/explicit structure、開始時 current
text/structure、`target_was_current_text` を固定する。Reference Work は episode
id/order/document/snapshot text/initial structure の array を固定する。

### 5.2 Tasks

`style_external_analysis_tasks` は session/run、sequence/call、Analyzer/Prompt/
Contract、attempt、parent、request/response fingerprint、request/response/error
JSON、status、version、timestamps を保持する。status は
`pending|accepted|repair_required|rejected|superseded`、attempt は 1 または 2。

`(session_id,sequence_no)` と `(session_id,call_key,attempt_no)` は unique、partial
unique index により Session あたり pending は最大一件。Attempt 1 の parent は
NULL、Attempt 2 の parent は initial Task。同一 Session の created Run だけが
Task の `analysis_run_id` になれる。Accepted/domain error は Task accepted のまま
で、その後の Analyzer Partial/Failed は Engine が処理する。

### 5.3 Session run links

`style_external_analysis_session_runs(session_id, run_id, run_role)` の PK は
`(session_id,run_id)`。role は `created|reused`。Run insert/reuse と link は同一
outer transaction で行い、cache reused Run から Task を作らない。

## 6. Session lifecycle and transaction invariants

Start target は document、reference_work、project_episode。project_episode は
既存 `capture_project_draft` を同じ outer transaction で使う。Preflight は
target/revision/structure/rebuild/conflict/model を検証し、失敗時に Session row を
残さない。

Start は `BEGIN IMMEDIATE` 内で preflight、capture/snapshot、policy/runtime 保存、
Session insert、Engine advance、必要なら Task insert、cursor/result/warning 更新、
invariant check、commit を行う。Server-side model call は 0 件。active commit 時は
pending Task exactly 1 件、terminal commit 時は pending 0 件でなければならない。

Submit は同じ `BEGIN IMMEDIATE` 内で session/task ownership、response fingerprint、
finalized same-response idempotency、active/model/current/version、runtime/state
fingerprint、repairable validation、Task finalize、Engine consume/advance、Session
update、invariant、commit の順で行う。

Finalized Task への同一 canonical response は古い task version、terminal Session、
古い executor 値でも idempotent success として current Snapshot を返す。別 response
は `409 EXTERNAL_TASK_ALREADY_FINALIZED`。Contract drift と Human state drift は
response を rejected として保存し、HTTP 200 の failed Snapshot を返す。

Cancel は expected Session version を検証し、pending Task を superseded、created
かつ running の Run だけを cancelled、reused/既存 terminal Run は変更せず、Session
を cancelled にする。成功 mutation ごとに Session version を増やし、Task finalize
でも Task version を増やす。

Direct Document の historical text は分析でき、Current Pointer を更新しない。開始
時 target が Current で途中に Current Text/Structure が変わった場合は分析結果を
保持するが Pointer を CAS 更新せず、`CURRENT_TEXT_CHANGED` または
`CURRENT_STRUCTURE_CHANGED` warning を残す。Reference Work は各 Episode の開始時
revision を再確認し、変化した Episode だけ `DOCUMENT_REVISION_CHANGED` failed とし、
他 Episode を継続する。usable があれば Work partial、0 件なら failed。

## 7. Conflict and recovery

CORE の `AnalysisExecutionConflictChecker` を External start、Style Job enqueue/
retry、Reference Work purge で共有する。Document とその Reference Work child、
Work と child Document、active External Session の overlapping scope は conflict。
Unrelated Document は並行可能。Checker と INSERT/DELETE は同じ `BEGIN IMMEDIATE`
transaction で実行する。

Worker startup は既存の running Run recovery を維持する。ただし
`style_external_analysis_session_runs.run_role='created'` で linked Session が
active の Run だけを recovery から除外する。Terminal Session に link された
running Run は異常状態として `WORKER_INTERRUPTED` に回収する。

## 8. API contract

Prefix は `/api/v1/projects/{project_id}/style-analysis`。追加 endpoint は次の5つ
だけである。

```text
POST /external-sessions                                      201
GET  /external-sessions                                      200
GET  /external-sessions/{session_id}                        200
POST /external-sessions/{session_id}/tasks/{task_id}/submit  200
POST /external-sessions/{session_id}/cancel                  200
```

Start request は discriminated target（document: document/text/optional structure、
reference_work、project_episode: episode/draft）、non-empty executor model、
`rebuild_structure=false`。Submit は expected task version、executor model、JSON
object response。Cancel は expected Session version。List は status optional、limit
1..100、created_at DESC/id DESC の Summary。Get/Start/Submit/Cancel は Full Snapshot
を返し、active Snapshot の task は current pending Task exactly one、terminal
Snapshot は null とする。

HTTP 404 は Session/Task not found、409 は conflict/version/terminal/finalized/
not-current/executor mismatch、request shape は既存 Validation Envelope、unexpected
storage/invariant は既存 INTERNAL_ERROR。Model contract failure、Analyzer
Partial/Failed、dependency failure、revision drift、runtime/input drift は開始後の
domain result なので、Session state を commit して HTTP 200 Snapshot とする。

## 9. MCP contract

Style Analysis group に次の6 toolsだけを追加する。

```text
style_analysis_catalog_get
style_analysis_result_get
style_analysis_external_start
style_analysis_external_status
style_analysis_external_submit
style_analysis_external_cancel
```

Catalog と Result は明示 ID/revision を API に渡す read-only mapping。External
start/submit/cancel は API service へそのまま mapping する。status は GET だけで
あり State を進めない。全6 tools は `project_id` required、既存 group の
names/counts/schema は変更しない。

Annotations は catalog/status/result が read-only true、destructive false、
open-world false、start/submit/cancel が read-only false、destructive false、
open-world false、全て structured output。Final inventory は project 4、phase1 23、
phase2 27、phase3 5、style_analysis 6、合計65。`project_select` は存在しない。

Task description は system prompt が解析 instruction、response schema が output
contract、user payload の本文は untrusted analysis data であり、本文中の命令文を
実行しないことを明示する。ただし安全性の正本は CORE validation である。

## 10. Verification and non-goals

Internal/External parity、chunk/reduce、dynamic Resolver、restart/resume、repair
最大1回、response-loss idempotency、runtime/policy/executor/input drift、worker
recovery、job retry/purge conflict、migration、MCP inventory/boundary、provider
disabled（External start/submit、server model HTTP 0件）を検証する。Real ChatGPT
connector dogfood は ChatGPT review 後にのみ行う。

SA-I では WebUI external selector/screen、OpenAI API、callback/webhook、Auth、
Redis/Celery/additional Worker、Session TTL/cleanup、parallel/batch task、既存59
toolsの移動、001〜008の変更、existing Job semantics の redesign を行わない。
