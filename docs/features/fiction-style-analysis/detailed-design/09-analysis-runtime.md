# 09 Analysis Runtime 詳細設計

## 1. 目的

Document解析Analyzerを依存DAGとして実行し、入力Revision・Analyzer/Policy・Model/Prompt・依存Run・人手補正StateをFingerprint化する。前処理、Structure作成、Corpus集約、Profile生成、LintをAnalysisRunへ押し込まない。

Style JobはProject-local `story.db` にpersistし、API Process全体では単一同期Worker Threadで処理する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  runtime_models.py
  analyzer.py
  analyzer_registry.py
  analysis_policy.py
  analysis_state.py
  analysis_repository.py
  analysis_service.py
  fingerprint.py
  model_client.py
  prompts/

API/src/novel_api/style_analysis/
  runtime.py
  job_worker.py
  model_client.py
```

## 3. AnalysisRun対象

```text
scene-boundary-detector
entity-mention-extractor
entity-resolver
speaker-attribution
entity-relation-extractor
term-candidate-extractor
term-resolver
term-explanation-detector
scene-semantic-classifier
block-semantic-classifier
pov-classifier
style-metrics-basic
style-metrics-semantic
```

対象外:

- Normalization -> TextRevision
- Automatic/Semantic/Manual Structure Materialization -> StructureService
- Aggregate
- Profile
- Lint

## 4. Analyzer契約

```python
@dataclass(frozen=True)
class AnalyzerContext:
    document_id: int
    text_revision_id: int
    structure_revision_id: int
    dependency_run_ids: tuple[int, ...]
    policy_version: int
    state_fingerprint: str | None
    registry_input_fingerprint: str | None
    config: Mapping[str, object]

@dataclass(frozen=True)
class AnalyzerResult:
    status: Literal["succeeded", "partial"]
    output_counts: Mapping[str, int]
    warnings: tuple[str, ...]
    failed_subject_ids: tuple[int, ...] = ()

class Analyzer(Protocol):
    id: str
    version: int
    deterministic: bool
    cacheable: bool
    dependencies: tuple[str, ...]
    state_inputs: tuple[str, ...]
    registry_input: str | None
    input_scope: str
    def run(self, context: AnalyzerContext) -> AnalyzerResult: ...
```

## 5. 初期Analyzer Registry

| Analyzer | Cache | Dependency | State Input | Registry Input |
|---|---|---|---|---|
| scene-boundary-detector | yes | - | - | - |
| entity-mention-extractor | yes | - | - | - |
| entity-resolver | **no** | entity-mention-extractor | entity_registry | entity_registry |
| speaker-attribution | yes | entity-resolver | entity_registry, mention_resolution | - |
| entity-relation-extractor | yes | speaker-attribution | entity_registry, mention_resolution | - |
| term-candidate-extractor | yes | - | - | - |
| term-resolver | **no** | term-candidate-extractor | term_registry | term_registry |
| term-explanation-detector | yes | term-resolver | term_registry | - |
| scene-semantic-classifier | yes | - | - | - |
| block-semantic-classifier | yes | - | - | - |
| pov-classifier | yes | entity-resolver | entity_registry, mention_resolution | - |
| style-metrics-basic | yes | - | - | - |
| style-metrics-semantic | yes | speaker-attribution, term-resolver, term-explanation-detector, scene-semantic-classifier, block-semantic-classifier | effective_semantics | - |

Resolver 2種だけはWork/DocumentのIncremental Registryを更新するためCache不可。

## 6. AnalysisPolicy

唯一のThreshold/Sample Policy正本。

```python
@dataclass(frozen=True)
class AnalysisPolicy:
    version: int = 1
    entity_resolution_auto_merge: float = 0.90
    speaker_effective: float = 0.85
    speaker_candidate: float = 0.60
    participant_effective: float = 0.80
    term_resolution_auto_merge: float = 0.90
    term_entity_auto_link: float = 0.90
    term_explanation_effective: float = 0.85
    scene_label_effective: float = 0.80
    block_semantic_effective: float = 0.75
    scene_boundary_auto_apply: float = 0.85
    scene_boundary_candidate_min: float = 0.60
    profile_min_episode_measurements: int = 5
    profile_min_scene_measurements: int = 10
    profile_min_character_utterances: int = 10
    profile_min_term_samples: int = 5
```

## 7. Human State Fingerprint

ManualOverride/InferenceReviewがAnalyzer入力を変える場合だけCurrent RunをStaleにする。Raw Inferenceを単にOverrideしただけで無関係AnalyzerまでStaleにしない。

`analysis_state.py` がState KeyごとのCanonical SHA-256を計算する。

### entity_registry

対象Scopeの:

- Manual Entity Identity
- Active Effective `entity.enabled/name/type` Override
- Manual Entity Alias
- Inferred Entity Aliasの最新Confirmed/Rejected Review

### mention_resolution

指定StructureRevision内のActive Effective `mention.entity_id` Override。

### term_registry

対象Scopeの:

- Manual Term Identity
- Active Effective `term.enabled/label/type` Override
- Manual Term Alias
- Inferred Term Aliasの最新Confirmed/Rejected Review

### effective_semantics

指定Document/Text/StructureでMetricへ影響するEffective Human Decision:

- `block.speaker_entity_id`
- Entity Enabled
- Term Enabled
- `term.novelty`
- `term.exact_match_safe`
- `term.sufficient_explanation_annotation_id`
- Scene Function/Tone/Pace/InformationLoad/Interaction/POV Override
- Relevant Confirm/Reject Review

Canonical StateはEffective値でHashし、Override履歴Row IDそのものは含めない。同じEffective Stateなら同Hash。

Analyzerの `state_inputs` が空なら `state_fingerprint=NULL`。

複数Keyは:

```text
hash({key: key_hash, ...} sorted)
```

## 8. Registry Input Fingerprint

`entity-resolver` / `term-resolver` はCurrent Inferred Registryも入力にするため、Run開始時のRegistry全体をCanonical Hash化して `registry_input_fingerprint` に保存する。

含むもの:

- Enabled Inferred/Manual Identity ID + Effective Name/Type/Label
- Confirmed/Manual Alias

これはHistorical Provenance用。

**Current Run判定では現在のRegistry Hashとの一致を要求しない。** 後続EpisodeでRegistryが成長するたび全過去Episodeを自動Stale化しないためである。

ResolverはCache不可なので、ユーザーが再Analysisしたときは必ずCurrent Registryで新Runを作る。

## 9. AnalysisRun Dependency永続化

Dependency IDは12 `style_analysis_run_dependencies` に保存する。

Run開始前:

1. Registry Dependency Analyzer IDを取得
2. Section 10 Current ResolverでCurrent Dependency Runを解決
3. 必須Dependencyがない場合、Orchestratorが先にそのAnalyzerを実行
4. Dependency Run IDsをsort
5. Run FingerprintへDependency Run Fingerprintsを含める

Final Output TransactionでRun ResultとDependency Linkを一緒にpersistする。

Historical Dependency LinkはUpdateしない。

## 10. Current AnalysisRun Resolver

入力:

```text
document_id
text_revision_id
structure_revision_id
analyzer_id
consumer_mode = complete | subject_partial_allowed
```

Candidate条件:

### Current Definition

- Analyzer Version = Registry Current
- Policy Version = Current AnalysisPolicy
- Config JSON = Current Default Config
- State Fingerprint = Section 7で現在計算した値
- Model-basedならCurrent Provider/Model/Prompt ID+Version一致
- Taxonomy/Metric Version等のFingerprint定義一致

v1 Analyze APIは任意Analyzer Configを受け付けない。ConfigはRegistry Defaultだけ。将来Custom Configを追加する場合はAPI/Current Resolverを同時拡張する。

### Dependency

Registry依存を再帰Resolveし、CandidateのDependency Link集合がCurrent Dependency Run ID集合と完全一致すること。

Dependencyが変わればDependent RunはStale。

### Status

`complete`: Succeededのみ。

`subject_partial_allowed`: Succeeded優先、なければPartial可。

### Selection

Current条件一致が複数なら:

```text
created_at DESC, id DESC
```

該当なしはNone。旧Version/旧Policy/旧DependencyをFallbackしない。

Resolve Call内はMemoizeする。

### Resolver Analyzer特例

`entity-resolver` / `term-resolver` はCache不可だが、**表示・Dependent Run Current判定用には最新Current RunをResolve可能**。

そのCurrent判定では:

- Analyzer/Policy/Model/Prompt/State/Dependency一致を要求
- Registry Input FingerprintのCurrent一致は要求しない

## 11. Dependency DAG

Final Structure確定後:

```text
entity-mention-extractor
  -> entity-resolver
      -> speaker-attribution
          -> entity-relation-extractor
      -> pov-classifier

term-candidate-extractor
  -> term-resolver
      -> term-explanation-detector

scene-semantic-classifier
block-semantic-classifier

final structure
  -> style-metrics-basic

speaker-attribution
term-resolver
term-explanation-detector
scene-semantic-classifier
block-semantic-classifier
  -> style-metrics-semantic
```

CycleはRegistry初期化時Error。

## 12. Orchestration: Document

### deterministic

```text
TextRevision
-> Automatic Structure build/reuse
-> style-metrics-basic
```

### full / Structure omitted

```text
TextRevision
-> Automatic Base Structure
-> scene-boundary-detector
-> Semantic Structure Materialize/Reuse
-> Final Structure
-> Entity Mention -> Entity Resolver -> Speaker/Relation/POV
-> Term Candidate -> Term Resolver -> Term Explanation
-> Scene/Block Semantic
-> Basic Metric
-> Semantic Metric
```

### full / Structure explicit

指定StructureをFinalとして使いBoundary Detectorを再実行しない。

## 13. Orchestration: Reference Work

作品全体解析用Job `analyze_reference_work` を用意する。

Job Payload:

```json
{
  "reference_work_id": 12,
  "preset": "full"
}
```

Worker実行開始時にCurrent CatalogをSnapshot:

```text
ReferenceEpisode order_index ASC
+ each current_text_revision_id
```

`current_text_revision_id=NULL` のEpisodeはそのEpisodeだけFailureとして記録する。

各EpisodeをOrder順にDocument Analysisする。これによりIncremental Entity/Term Registryが本文順に育つ。

ResolverはCache不可なので、Work全体解析を再実行すれば全Episode Resolverが再実行される。

### Work Job Status

- 全Episode成功 -> `succeeded`
- 1件以上成功 + 1件以上失敗/Cancel対象外Failure -> `partial`
- 成功0件 -> `failed`
- Cancel Requested -> 現在のSafe Point後 `cancelled`

成功済みEpisodeのRunはRollbackしない。

`result_json`:

```json
{
  "succeeded_episode_ids": [1,2],
  "failed_episode_ids": [3]
}
```

## 14. AnalysisRun

```text
id
document_id
analyzer_id
analyzer_version
text_revision_id
structure_revision_id
status
fingerprint
config_json
policy_version
state_fingerprint nullable
registry_input_fingerprint nullable
model_provider nullable
model_id nullable
prompt_id nullable
prompt_version nullable
started_at nullable
finished_at nullable
error_code nullable
error_message nullable
warning_json
created_at
```

Status:

```text
queued
running
succeeded
partial
failed
cancelled
```

## 15. Fingerprint

Canonical JSON SHA-256:

```text
analyzer id/version
input text hash
structure fingerprint
dependency run fingerprints
config
policy version
state fingerprint
registry input fingerprint if Resolver
model provider/id
prompt id/version
taxonomy/metric versions
```

Cache Hit:

- `analyzer.cacheable == true`
- 同Current FingerprintのSucceeded Run

Resolver 2種はFingerprintをProvenanceとして保存するがCache Hitには使わない。

Partial/FailedはCache Hit不可。

## 16. Scene Boundary Provenance

- Boundary Run Structure = Automatic Base
- Candidate Annotation = 03/06契約
- Semantic Structure = StructureService Projection
- `style_structure_analysis_sources` でBoundary Run Link

後続AnalyzerはSemantic Structure Fingerprint経由でProvenanceを得る。

## 17. Partial Analyzer Policy

- 全Subject成功 -> succeeded
- Usable Output >=1 + 一部Failure -> partial
- Usable Output 0 / Provider・Contract・Storage全体Failure -> failed

任意Failure率Thresholdは置かない。

## 18. Persisted Job Schema契約

各Project DBの `style_jobs`:

```text
id
job_type
payload_json
status
cancel_requested
progress_current nullable
progress_total nullable
result_json
warning_json
created_at
started_at
finished_at
error_code
error_message
version
```

Job Status:

```text
queued
running
succeeded
partial
failed
cancelled
```

Job Type:

```text
source_import
source_refresh
analyze_document
analyze_reference_work
recompute_aggregate
build_profile
run_lint
```

Progressは件数ベース。Totalが判明前はNULL可。

## 19. StyleJobWorker

API Process全体で同期Worker Thread 1本。

State:

```text
Condition
ready_project_ids deque
ready_project_id_set
stop flag
ProjectRegistry
```

Request-bound SQLite ConnectionはWorkerへ渡さない。Worker Thread自身がProject DB ConnectionをOpen/Closeする。

### Notify

Job Commit直後:

```python
worker.notify(project_id)
```

In-memory Project Queueへ追加してWakeするだけ。

### Startup Recovery

1. `ProjectRegistry.list(include_archived=False)`
2. 各Active ProjectをWorker Thread上で`open_database()`
3. Running Job/AnalysisRun -> `failed / WORKER_INTERRUPTED`
4. Queued JobがあればProject IDをReady Queue
5. Close

1 Project FailureでWorker全体を止めない。

Archived ProjectはStartup Scan Skip。

### Claim

Project内:

```text
status=queued
ORDER BY created_at ASC,id ASC
LIMIT 1
```

を短いTransactionでRunningへClaim。

同Project内FIFO。Project間厳密Global FIFOは不要。

### Execute

Network/Model Call中は長時間DB Transactionを開かない。

1 Job終了後、同ProjectにQueuedが残ればProject IDをReady Queue末尾へ戻す。

## 20. Progress更新

WorkerはJob種別ごとに短いTransactionでProgressを更新する。

### Source Import/Refresh

AdapterはDBを知らない。01のProgress Callbackで:

```text
progress_current
progress_total
```

をWorkerへ通知する。

### Reference Work Analysis

```text
progress_total = target episode count
progress_current = completed episode count
```

### Document Analysis等

Step数を無理にPercent化しない。Totalを自然に定義できなければNULLのままRunning表示でよい。

## 21. Restart / Cancel

RunningをSucceededへ推測しない。Startup RecoveryでFailed。

Running Job自動Requeueなし。Retry APIで新Job。

Queued Cancelは即Cancelled。

Runningは `cancel_requested=1`。

Safe Point:

- Scene/Block間
- Source Episode取得間
- Reference Work Episode間
- Model Call前後

External Request強制Killなし。

## 22. Transaction

AnalysisRun:

1. Running commit
2. Compute
3. Output + Dependency Link + Final Statusを1Transaction
4. Persistence Failure -> Rollback + Run Failed

Job Progress/Stateは別の短いTransaction。

## 23. Model Client

CORE Protocolは同期 `complete_json()`。

Provider Mode:

```text
disabled
openai_compatible
```

Config:

```text
STYLE_ANALYSIS_LLM_PROVIDER
STYLE_ANALYSIS_LLM_BASE_URL
STYLE_ANALYSIS_LLM_API_KEY
STYLE_ANALYSIS_LLM_MODEL
STYLE_ANALYSIS_LLM_TIMEOUT_SECONDS default 60
```

Worker Threadから同期呼出し。別Async Event Loopを作らない。

API KeyはDB/Logへ保存しない。

Full Analysis明示実行を送信開始操作とし追加確認Dialog不要。

## 24. Model Call

- Temperature=0
- Timeout/429/5xx Retry最大1
- Schema Invalid Repair Retry最大1
- Repair Failureは対象Subject Failure
- Raw Response全文を通常Logへ出さない

## 25. API契約

Document Analyze:

```text
POST /projects/{project_id}/style-analysis/documents/{document_id}/analyze
```

- `text_revision_id` required
- `structure_revision_id` optional
- `preset=deterministic|full`

Reference Work Analyze:

```text
POST /projects/{project_id}/style-analysis/reference-works/{work_id}/analyze
```

Request:

```json
{"preset":"full"}
```

Response `202 + job_id`。

Job作成/Retry後は `worker.notify(project_id)`。

## 26. Test

### Runtime

- DAG/Cycle
- Analyzer Cacheable Flag
- Resolver Cache不可
- State Fingerprint Key計算
- Entity/Term Human State変更で該当Run Stale
- Scene OverrideでScene Classifier RunはStaleにならずSemantic Metric Stale
- Registry Input Fingerprint保存
- Dependency Link Persist
- Analyzer/Policy/Model/Prompt mismatch -> Current None
- Dependency変更 -> Dependent Stale
- Complete vs Partial
- Current Resolver Memoization
- Basic Metric Semantic State非依存

### Work Analysis

- Current Text PointerをEpisode Order順にSnapshot
- Resolver毎Episode再実行
- Partial Work Job
- Progress Count
- Work ReanalysisでResolver再実行

### Worker

- Thread 1本
- Request Connection非再利用
- Notify
- Project内FIFO
- Project公平再Queue
- Startup Active Project Scan
- Running Recovery
- Queued Recovery
- 1 Project Failure継続
- Archived Skip
- Source Refresh Job
- Cancel

### Model

- Provider Disabled
- Retry/Repair

## 27. Codex禁止事項

- Normalize/Segment/Aggregate/Profile/LintをAnalysisRunへ入れる
- Dependency Link省略
- Current Runを単純Latest Succeededで選ぶ
- Stale RunをFallback
- Entity/Term ResolverをCache Hitで省略
- Inferred Registry成長だけで全過去Episodeを自動再解析
- Celery/Redis/Parallel Worker追加
- ProjectごとWorker Thread追加
- Request SQLite ConnectionをWorkerへ渡す
- Project間Global FIFO用中央DB追加
- Source/ModelのためだけにAsync Event Loop追加
- Arbitrary Failure率Threshold追加
- Threshold重複Hard-code
- Provider SDKをCOREへ入れる
