# 09 Analysis Runtime 詳細設計

## 1. 目的

Document解析Analyzerを依存DAGとして実行し、Revision・Analyzer Definition・Prompt/Taxonomy・必要なPolicy入力・依存Run・Human StateをFingerprint化する。JobはProject-local DBへPersistし、API Process全体の単一同期Workerで処理する。

上位仕様は `../basic-design.md`。

## 2. Analyzer契約

```python
@dataclass(frozen=True)
class DependencySpec:
    analyzer_id: str
    mode: Literal["complete", "subject_partial_allowed"]

class Analyzer(Protocol):
    id: str
    version: int
    deterministic: bool
    cacheable: bool
    dependencies: tuple[DependencySpec, ...]
    state_inputs: tuple[str, ...]
    policy_inputs: tuple[str, ...]
    input_scope: str
    def run(self, context: AnalyzerContext) -> AnalyzerResult: ...
```

`subject_partial_allowed`はDependency RunがPartialでも、そのRunで成功したSubjectだけを利用できることを意味する。

## 3. 初期Analyzer Registry

| Analyzer | Cache | Dependency | State Input | Policy Input |
|---|---:|---|---|---|
| scene-boundary-detector | yes | - | - | - |
| entity-mention-extractor | yes | - | - | - |
| entity-resolver | no | entity-mention-extractor: partial allowed | entity_registry_state | entity_resolution_auto_merge |
| speaker-attribution | yes | entity-resolver: partial allowed | mention_resolution | - |
| term-candidate-extractor | yes | - | - | - |
| term-resolver | no | term-candidate-extractor: partial allowed | term_registry_state | term_resolution_auto_merge |
| term-explanation-detector | yes | term-resolver: partial allowed | - | - |
| scene-semantic-classifier | yes | - | - | - |
| block-semantic-classifier | yes | - | - | - |
| pov-classifier | yes | entity-resolver: partial allowed | mention_resolution | - |
| style-metrics-basic | yes | - | - | - |
| style-metrics-semantic | yes | speaker-attribution, term-resolver, term-explanation-detector, block-semantic-classifier: partial allowed | metric_effective_state, term_first_appearance | speaker_effective, term_explanation_effective, block_semantic_effective |

Scene SemanticはMetric入力ではなく08/11 Selector用途。v1ではEntity Relation Analyzerなし。

## 4. AnalysisPolicy / Policy Input

```python
@dataclass(frozen=True)
class AnalysisPolicy:
    version: int = 1
    entity_resolution_auto_merge: float = 0.90
    term_resolution_auto_merge: float = 0.90
    speaker_effective: float = 0.85
    term_explanation_effective: float = 0.85
    scene_label_effective: float = 0.80
    block_semantic_effective: float = 0.75
    pov_effective: float = 0.80
    scene_boundary_auto_apply: float = 0.85
    scene_boundary_candidate_min: float = 0.60
```

ProfileGenerationPolicyは08へ分離する。未使用Keyを追加しない。

AnalysisRunへ:

```text
analysis_policy_version nullable
policy_input_fingerprint nullable
```

を保存する。

`policy_inputs`に列挙したKey/ValueだけCanonical Hashし、Policy Version全体をCurrent条件にしない。

Raw Scene/Speaker/Block/POV推論はEffective Thresholdで再実行しない。

## 5. Boundary Policy

Boundary AnalyzerはRaw Candidate保存のみでPolicy非依存。

- `scene_boundary_auto_apply`:03 Semantic Materialization。
- `scene_boundary_candidate_min`:API/UI Proposal Filterだけ。

Semantic Structure FingerprintへAuto Apply値を含める。Policy変更だけでCurrent Structureを自動Clear/Rebuildしない。

## 6. Human State Fingerprint

### entity_registry_state

Resolverを明示的に再評価すべきHuman変更だけを含める。

- Manual Entity Identity。
- Entity `enabled/name/type` Override。
- Manual Alias。
- Inferred Alias最新Confirm/Reject。

**後続Episode解析で増えただけの未Review Inferred Entity/Alias集合はState Fingerprintへ含めない。** その時点の実RegistryはSection 7 Provenanceへ記録する。

### mention_resolution

Target Structure内:

- Latest `mention.entity_id` ManualOverride。
- Current Resolution Inference Review Confirm/Reject。

### term_registry_state

- Manual Term Identity。
- Term `enabled/label/type` Override。
- Manual Alias。
- Inferred Alias最新Confirm/Reject。

後続Episodeで増えただけの未Review Inferred Term/AliasはState Fingerprintへ含めない。

### metric_effective_state

- Speaker Correction/Review。
- Term Novelty Correction/Review。
- First Appearance TermMention Explanation Correction/Review。
- Block Primary Correction/Review。

Entity/Term EnabledはRegistry State→Resolver Dependency経路だけで伝播する。

### term_first_appearance

05を正本とする。

## 7. Registry Input Fingerprint

Entity/Term Resolver実行時の実RegistryをProvenanceとしてHashする。

```text
Current Enabled Stable Identity
Effective Name/Type/Label
Confirmed/Manual Alias
```

をSortしてCanonical SHA-256。

`registry_input_fingerprint`は「そのRunが何を見たか」の履歴であり、Current Run選択時に現在Registryとの一致を要求しない。

したがって後続EpisodeでRegistryが自然成長しただけでは過去Episode Resolverを自動Staleにしない。

Manual CorrectionはSection 6 State FingerprintでStaleにする。

Entity/Term ResolverはCache不可。

## 8. Dependency / Current Run

`style_analysis_run_dependencies`へRun→Dependency Runを保存する。

- `complete`: Current Succeeded必須。
- `subject_partial_allowed`: Succeeded優先、なければCurrent Partial可。
- 利用不可BranchだけSkipしIndependent Branch継続。

Current Run条件:

- Current Analyzer Version。
- Current Default Config。
- Current Prompt/Taxonomy/MetricDefinition Version。
- 同TextRevision/StructureRevision。
- Current State Fingerprint。
- Relevant Policy Input Fingerprint。
- Required Dependency集合がCurrentで、Historical Dependency Linkと一致。

`complete`はSucceededのみ、`subject_partial_allowed`はSucceeded優先/Partial fallback。

同条件複数は`created_at DESC,id DESC`で1件を選ぶ。

Provider/ModelはProvenance/Execution Cacheへ含めるが、保存済みRunのCurrent Consumption条件として「現在Environmentで選択されているProvider/Modelとの一致」は要求しない。

## 9. Execution Fingerprint / Cache Hit

Cacheable AnalyzerのExecution Fingerprint:

```text
analyzer id/version
text_revision_id
structure_revision_id
config
prompt/taxonomy/metric version
state_fingerprint
policy_input_fingerprint
dependency run ids
今回使用 provider/model
```

Cache Hit:

- `cacheable=true`。
- 同Execution Fingerprintの`status=succeeded` Run。

Partial/FailedはCache Hit不可。

Resolverは`cacheable=false`。

## 10. Document Analyze Request / Structure

内部契約:

```text
text_revision_id required
structure_revision_id nullable
preset = deterministic | full | metrics
rebuild_structure boolean default false
metric_groups nullable
```

Publicは`deterministic|full`だけ。`metrics`は10内部専用。

03を正本として:

- Explicit Structure -> Exact Final、Boundaryなし、Pointer不変。
- Current Manual/Semantic + default ->再利用、Boundaryなし。
- Current Automatic + deterministic ->再利用。
- Current Automatic + full ->AutomaticをBaseにBoundary、Semantic昇格可能。
- Current Structureなし -> Automatic Build/Reuse、fullならBoundary。
- rebuild=true -> Current種類を無視しAutomaticから再生成。Explicit Structureと併用不可。

Boundary Analyzerが失敗した場合はAutomatic BaseをFinalとしてSemantic Branchを続行できるが、Full Document Jobは`partial`とする。

## 11. Document Orchestration

### deterministic

```text
Final Structure
-> style-metrics-basic
```

### full

```text
Final Structure determination
├ Entity Mention -> Entity Resolver -> Speaker / POV
├ Term Candidate -> Term Resolver -> Term Explanation
├ Scene Semantic
├ Block Primary Semantic
├ Basic Metric
└ Semantic Metric
```

Independent Branchは並列Agent化せず同Worker内で順番に実行してよい。v1は実装単純性を優先し、Analyzer並列実行を必須にしない。

新FinalをCurrentへ設定可能なのは03の3条件だけ。Job終了時Request TextがまだCurrent Textの場合だけPointer更新する。

## 12. `metrics` preset

Human Correction後の軽量再計算用。

- Text/Structure明示必須。
- Boundary/Entity/Term/Scene/Block Analyzer再実行なし。
- 必要Metric Groupだけ新AnalysisRun。
- Current Dependency不足なら作れるMetricだけ生成しJob partial。
- Pointer変更なし。

Public API/UIへ露出しない。

## 13. Document Job Status

Full Document:

- `succeeded`: Final Structure + Basic Metric成功、Scheduled Semantic Analyzer/Metric全SucceededまたはNot Applicable。
- `partial`: Basic成功、BoundaryまたはSemantic Branchの一部Partial/Failed/Dependency不足。
- `failed`: Final Structure確立失敗、Basic Metric失敗、Persistence全体Failure。
- `cancelled`: Safe PointでCancellation受理。

Scene Semantic失敗はMetric直接非依存でもFull Jobはpartial。

## 14. Reference Work Job

`analyze_reference_work` はJob開始時に:

```text
ReferenceEpisode order
StyleDocument id
Current TextRevision id
```

をSnapshotする。

Episode Order順に**Document Orchestratorを同じWork Job内でinline実行する**。

子`analyze_document` Jobをenqueueして待たない。単一Workerでdeadlockするため。

各Episode完了後にProgressを更新する。

途中でCurrent TextがSnapshot値と変わったEpisodeは`DOCUMENT_REVISION_CHANGED`としてそのEpisodeを失敗扱いにし、新Revisionを同Jobへ混ぜない。

Work Status:

- 全Episode Succeeded -> `succeeded`。
- 1件以上usable + 一部Partial/Failed -> `partial`。
- usable Episode 0 -> `failed`。
- Cancel受理 -> `cancelled`。

成功済みEpisodeのAnalysisRunは保持する。

## 15. AnalysisRun Schema契約

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
analysis_policy_version nullable
policy_input_fingerprint nullable
state_fingerprint nullable
registry_input_fingerprint nullable
model_provider nullable
model_id nullable
prompt_id nullable
prompt_version nullable
started_at
finished_at
error_code
error_message
warning_json
created_at
```

Status:

```text
running
succeeded
partial
failed
cancelled
```

`queued`はJobだけに持つ。

## 16. Persisted Job / Worker

Job Type:

```text
analyze_document
analyze_reference_work
recompute_aggregate
run_lint
```

Local File Import/Profile生成は同期処理でJobを作らない。

Status:

```text
queued
running
succeeded
partial
failed
cancelled
```

API Process全体で同期Worker Thread 1本。

- Existing Project Registry/Project Discoveryを使ってProject DBを発見する。
- Ready Project Deque + SetをProcess Memoryに持つ。
- Job commit後`worker.notify(project_id)`。
- Request-bound SQLite ConnectionをWorkerへ渡さない。
- Worker自身がProject DB ConnectionをOpen/Closeする。
- Startup時にActive Projectのqueued/running Jobをscanする。
- Startupで残ったrunning Job/Runは`WORKER_INTERRUPTED` failedへ確定する。
- queued Jobは回収する。
- Project内FIFO。
- 1 Job処理後、同ProjectにqueuedがあればReady末尾へ戻す。
- 1 Project FailureでWorker全体を停止しない。

Redis/Celery/Central Queue DBは追加しない。

## 17. Job Progress / Result

`style_jobs`:

```text
progress_current nullable
progress_total nullable
result_json
warning_json
```

- analyze_document: analyzer step単位のProgressを持ってよい。
- analyze_reference_work: Episode数をProgress Totalとする。
- recompute_aggregate: Aggregate Spec×Metric処理数。
- run_lint: Rule/Target評価Progressを持ってよい。

Job Resultは各Job TypeのTyped SchemaをService層で定義する。DBはJSON保存。

## 18. run_lint Job

Payload:

```text
document_id
text_revision_id
structure_revision_id
profile_id
profile_version_id
scene_id nullable
```

Workerが11 LintServiceを実行し、`style_lint_runs/findings`を保存する。Job Resultへ`lint_run_id`を返す。

Metric/Selector不足はJob FailureではなくLint Coverage/Warning。LintServiceのInvariant/Storage FailureだけJob failed。

## 19. Cancel / Retry

Retryは新Job Rowを作り、元Job IDを`payload_json.retry_of_job_id`へ記録する。元Jobを再利用しない。

Queued Cancelは即時`cancelled`。

RunningはScene/Block/Episode/Model Call前後のSafe Pointで`cancel_requested`を確認する。External Request強制Killはしない。

## 20. Model Client

同期API:

```python
complete_json(request: ModelRequest) -> dict
```

Provider:

```text
disabled
openai_compatible
```

API KeyはDB/通常Logへ保存しない。

Model Call:

- Timeout/429/5xx Retry最大1。
- JSON Schema Parse失敗時Repair Retry最大1。
- それでも失敗は該当Analyzer Subject/RunをPartial/Failed規則に従い処理する。

Provider disabledは新Full Analyzeだけ拒否し、保存済みRun閲覧を妨げない。

## 21. Test

- DAG/Cycle/Dependency Edge Mode/Independent Branch。
- Scene Semantic非依存Semantic Metric。
- Resolver Cache不可。
- Registry自然成長だけで過去Resolver非Stale。
- Manual Registry State変更でResolver Stale。
- Mention Resolution Review変更でSpeaker/POV Stale。
- Speaker CorrectionだけでRaw Speaker非Stale。
- Relevant Policy KeyだけStale。
- Provider Disable後も過去Run表示。
- Current Manual/Semantic Full保持。
- Current Automatic Full Semantic昇格。
- Boundary FailureでAutomatic継続 + Job partial。
- rebuild/Explicit/Historical Pointer規則。
- metrics preset Analyzer非再実行。
- Work Jobが子Jobを作らずinline処理。
- Work Job Revision Change/Progress/Partial。
- Single Worker/FIFO/Recovery/Retry/Cancel。
- `build_profile`/Source Import Job不存在。
- run_lint Job payload/result。

## 22. Codex禁止事項

- AnalysisPolicy Version丸ごとCurrent条件。
- 未使用Policy Key追加。
- style-metrics-semanticへScene Semantic Dependency追加。
- Dependencyを全Succeeded必須化。
- Registry Input FingerprintをCurrent Registry一致条件にする。
- Registry自然成長だけで過去Episodeを全Stale化。
- Provider disabledだけで過去結果表示不能。
- Resolver Cache。
- Current Manual/Semanticをdefault Fullで置換。
- Current Automatic FullでBoundary常時Skip。
- Policy変更だけでCurrent Structure自動Rebuild。
- Work Jobから子Document Jobをenqueueして待つ。
- `build_profile`/Source Import/Refresh Job追加。
- Human Correctionの度にFull Analysis自動Queue。
- metrics presetでSemantic Analyzer再実行。
- ProjectごとWorker追加。
- Redis/Celery追加。
