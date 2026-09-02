# 09 Analysis Runtime 詳細設計

## 1. 目的

Document解析Analyzerを依存DAGとして実行し、Revision・Analyzer Definition・Prompt/Taxonomy・必要なPolicy入力・依存Run・Human StateをFingerprint化する。JobはProject-local DBへPersistし、API Process全体の単一同期Workerで処理する。

上位仕様は `../basic-design.md`。

## 2. 共通Canonical Serialization / Fingerprint

Style Analysis内のJSON由来Fingerprintはすべて1つのUtilityを使用する。

実装先:

```text
CORE/src/novel_core/style_analysis/fingerprints.py
```

契約:

```python
def canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def fingerprint_json(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
```

入力整形規則:

- Enumは文字列Valueへ変換してから渡す。
- Tuple/Setは呼出側で意味上の順序を定義し、Setは必ずSort済みListへ変換する。
- DB Row集合は各設計書で指定されたKey順にSortしてList化する。
- Optional値は欠落Keyにせず、Fingerprint仕様に含める項目ならJSON `null`として明示する。
- `NaN` / `Infinity` は許可しない。
- SHA-256 hexはlowercase 64文字。

02 Normalization、03 Structure、08 Aggregate、09 Run/State/Policy/Registry、11 Lintで「Canonical JSON」「Canonical SHA-256」と記載したものはこのUtilityを使う。

Analyzerに該当Inputが存在しないFingerprint列は`NULL`とする。空Object Hashを保存しない。

## 3. Analyzer契約

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

## 4. 初期Analyzer Registry

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

## 5. AnalysisPolicy / Policy Input

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

`policy_inputs`に列挙したKeyとValueだけをKey昇順ObjectとしてSection 2 Utilityへ渡す。Policy Version全体をCurrent条件にしない。

Raw Scene/Speaker/Block/POV推論はEffective Threshold変更で再実行しない。

## 6. Boundary Policy

Boundary AnalyzerはRaw Candidate保存のみでPolicy非依存。

- `scene_boundary_auto_apply`:03 Semantic Materialization。
- `scene_boundary_candidate_min`:API/UI Proposal Filterだけ。

Semantic Structure FingerprintへAuto Apply値を含める。Policy変更だけでCurrent Structureを自動Clear/Rebuildしない。

## 7. Human State Fingerprint

### entity_registry_state

Resolverを明示的に再評価すべきHuman変更だけを含める。

- Manual Entity Identity。
- Entity `enabled/name/type` Override。
- Manual Alias。
- Inferred Alias最新Confirm/Reject。

後続Episode解析で増えただけの未Review Inferred Entity/Alias集合は含めない。その時点の実RegistryはSection 8 Provenanceへ記録する。

### mention_resolution

Target Structure内:

- Latest `mention.entity_id` ManualOverride。
- Current Resolution Inference Review Confirm/Reject。

### term_registry_state

- Manual Term Identity。
- Term `enabled/label/type` Override。
- Manual Alias。
- Inferred Alias最新Confirm/Reject。

後続Episodeで増えただけの未Review Inferred Term/Aliasは含めない。

### metric_effective_state

- Speaker Correction/Review。
- Term Novelty Correction/Review。
- First Appearance TermMention Explanation Correction/Review。
- Block Primary Correction/Review。

Entity/Term EnabledはRegistry State→Resolver Dependency経路だけで伝播する。

### term_first_appearance

05を正本とする。

各Stateは設計書で列挙したTuple/Listを安定Sortし、Section 2 UtilityでHashする。

## 8. Registry Input Fingerprint

Entity/Term Resolver実行時の実RegistryをProvenanceとしてHashする。

```text
Current Enabled Stable Identity
Effective Name/Type/Label
Confirmed/Manual Alias
```

Identity ID昇順、Alias文字列昇順でCanonical List化してSection 2 Utilityを使う。

`registry_input_fingerprint`は「そのRunが何を見たか」の履歴であり、Current Run選択時に現在Registryとの一致を要求しない。

したがって後続EpisodeでRegistryが自然成長しただけでは過去Episode Resolverを自動Staleにしない。

Manual CorrectionはSection 7 State FingerprintでStaleにする。

Entity/Term ResolverはCache不可。

## 9. Dependency / Current Run

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

Dependency集合比較は`analyzer_id -> run_id`をAnalyzer ID昇順でCanonical化する。

`complete`はSucceededのみ、`subject_partial_allowed`はSucceeded優先/Partial fallback。

同条件複数は`created_at DESC,id DESC`で1件を選ぶ。

Provider/ModelはProvenance/Execution Cacheへ含めるが、保存済みRunのCurrent Consumption条件として現在Environment Provider/Modelとの一致は要求しない。

## 10. Execution Fingerprint / Cache Hit

Cacheable AnalyzerのExecution Fingerprint入力:

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

Section 2 UtilityでHashする。

Cache Hit:

- `cacheable=true`。
- 同Execution Fingerprintの`status=succeeded` Run。

Partial/FailedはCache Hit不可。Resolverは`cacheable=false`。

## 11. Document Analyze Request / Structure

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

## 12. Document Orchestration

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

Independent Branchは同Worker内で順番に実行する。v1でAnalyzer並列実行を追加しない。

新FinalをCurrentへ設定可能なのは03の3条件だけ。Job終了時Request TextがまだCurrent Textの場合だけPointer更新する。

## 13. `metrics` preset

Human Correction後の軽量再計算用。

- Text/Structure明示必須。
- Boundary/Entity/Term/Scene/Block Analyzer再実行なし。
- 必要Metric Groupだけ新AnalysisRun。
- Current Dependency不足なら作れるMetricだけ生成しJob partial。
- Pointer変更なし。

Public API/UIへ露出しない。

## 14. Document Job Status

Full Document:

- `succeeded`: Final Structure + Basic Metric成功、Scheduled Semantic Analyzer/Metric全SucceededまたはNot Applicable。
- `partial`: Basic成功、BoundaryまたはSemantic Branchの一部Partial/Failed/Dependency不足。
- `failed`: Final Structure確立失敗、Basic Metric失敗、Persistence全体Failure。
- `cancelled`: Safe PointでCancellation受理。

Scene Semantic失敗はMetric直接非依存でもFull Jobはpartial。

Deterministic DocumentはSemantic BranchをScheduleしない。Structure + Basic成功なら`succeeded`、それ以前のFailureは`failed`。

## 15. v1.1 SA-I Resumable / External Execution

v1.0 の Orchestrator は内部で `ResumableDocumentAnalysisEngine` を loop する。
Engine は `PreparedModelCall` を一件だけ返し、provider を呼ばず、transaction の
commit/rollback を所有しない。Internal driver は既存 ModelClient と safe point、
External driver は API outer transaction と persistent Task を注入する。同一の
Analyzer primitive、validator、reducer、apply を両方の実行経路で使用する。

Full stage order は `structure_prepare` から `finalize` まで15段階、cursor は
schema_version 1 の JSON である。Pending request は Task row、accepted response
は immutable history として扱い、restart 後は sequence/call_key 順に読み戻して
既存 reduction を継続する。`run_observer(created|reused)` は AnalysisRun と
External Session link を同じ outer transaction で作る。

SA-I runtime contract/policy/state drift、External Session/Task lifecycle、worker
recovery exclusion、conflict checker の詳細は [16](16-external-agent-mcp.md) を
参照する。

## 15. Reference Work Job

`analyze_reference_work` はJob開始時にReferenceEpisode order、StyleDocument ID、Current TextRevision IDをSnapshotする。

Episode Order順にDocument Orchestratorを同じWork Job内でinline実行する。

子`analyze_document` Jobをenqueueして待たない。単一Workerでdeadlockするため。

各Episode完了後にProgress更新。

途中でCurrent TextがSnapshot値と変わったEpisodeは`DOCUMENT_REVISION_CHANGED`として失敗扱いにし、新Revisionを同Jobへ混ぜない。

Work Status:

- 全Episode Succeeded -> `succeeded`。
- 1件以上usable + 一部Partial/Failed -> `partial`。
- usable Episode 0 -> `failed`。
- Cancel受理 -> `cancelled`。

成功済みEpisodeのAnalysisRunは保持する。

## 16. Job Type別Terminal Status

DB Enumは共通だがServiceが次を守る。

| Job Type | succeeded | partial | failed | cancelled |
|---|:---:|:---:|:---:|:---:|
| analyze_document | yes | yes | yes | yes |
| analyze_reference_work | yes | yes | yes | yes |
| recompute_aggregate | yes | no | yes | yes |
| run_lint | yes | no | yes | yes |

### recompute_aggregate

- Input不足/0観測は08のWarning/Skipped/「Aggregate Rowなし」という正常結果であり`partial`にしない。
- Request内全Specを計算し、生成するAggregate/Linkを1 TransactionでPersistする。
- Invariant/Storage/Unexpected Calculation ErrorがあればTransactionをRollbackしJob`failed`。
- 0件生成でもRequest自体が正常処理できたなら`succeeded`。

### run_lint

- Metric/Selector不足は11 Coverage/WarningでありJob`succeeded`。
- LintRun/Storage/Invariant FailureだけJob`failed`。

## 17. AnalysisRun Schema契約

```text
id/document_id/analyzer_id/analyzer_version
text_revision_id/structure_revision_id/status/fingerprint/config_json
analysis_policy_version nullable
policy_input_fingerprint nullable
state_fingerprint nullable
registry_input_fingerprint nullable
model_provider/model_id nullable
prompt_id/prompt_version nullable
started_at/finished_at/error_code/error_message/warning_json/created_at
```

Status:`running|succeeded|partial|failed|cancelled`。`queued`はJobだけ。

## 18. Persisted Job / Worker

Job Type:

```text
analyze_document
analyze_reference_work
recompute_aggregate
run_lint
```

Local File Import/Profile生成は同期処理でJobを作らない。

API Process全体で同期Worker Thread 1本。

- Existing Project Registry/Project DiscoveryでProject DB発見。
- Ready Project Deque + SetをProcess Memoryに持つ。
- Job commit後`worker.notify(project_id)`。
- Request-bound SQLite ConnectionをWorkerへ渡さない。
- Worker自身がProject DB ConnectionをOpen/Close。
- Startup時Active Projectのqueued/running Jobをscan。
- 残ったrunning Job/Runは`WORKER_INTERRUPTED` failedへ確定。
- queued Job回収。
- Project内FIFO。
- 1 Job後、同Project queuedがあればReady末尾へ戻す。
- 1 Project FailureでWorker全体を停止しない。

Redis/Celery/Central Queue DBは追加しない。

## 19. Job Progress / Result

`style_jobs`:

```text
progress_current nullable
progress_total nullable
result_json
warning_json
```

- analyze_document: analyzer step単位。
- analyze_reference_work: Episode数。
- recompute_aggregate: Aggregate Spec×Metric処理数。
- run_lint: Rule/Target評価Progress。

Job Resultは各Job TypeのTyped SchemaをService層で定義しDBはJSON保存する。

## 20. run_lint Job

Payload:

```text
document_id
text_revision_id
structure_revision_id
profile_id
profile_version_id
scene_id nullable
```

Workerが11 LintServiceを実行し`style_lint_runs/findings`を保存する。Job Resultへ`lint_run_id`。

## 21. Cancel / Retry

Retryは新Job Rowを作り、元Job IDを`payload_json.retry_of_job_id`へ記録する。元Jobを再利用しない。

Queued Cancelは即時`cancelled`。

RunningはScene/Block/Episode/Model Call前後のSafe Pointで`cancel_requested`を確認する。External Request強制Killはしない。

## 22. Model Client

同期API:

```python
complete_json(request: ModelRequest) -> dict
```

Provider:`disabled|openai_compatible`。

API KeyはDB/通常Logへ保存しない。

- Timeout/429/5xx Retry最大1。
- JSON Schema Parse失敗時Repair Retry最大1。
- それでも失敗はAnalyzer Subject/RunのPartial/Failed規則に従う。

Provider disabledは新Full Analyzeだけ拒否し、保存済みRun閲覧を妨げない。

## 23. Test

- Canonical JSONでkey order/whitespaceが違っても同Hash。
- Unicodeをensure_asciiせずUTF-8 Hash。
- NaN/Infinity拒否。
- NULL input fingerprintはNULL保存。
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
- Aggregate 0 Input ->Job succeeded/partial不使用。
- Aggregate persistence failure ->Rollback/failed。
- Lint Missing ->Job succeeded/partial不使用。
- Single Worker/FIFO/Recovery/Retry/Cancel。
- `build_profile`/Source Import Job不存在。

## 24. Codex禁止事項

- Fingerprintごとに独自JSON Serializer実装。
- JSON default separators/ensure_ascii差異を許容。
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
- Aggregate/Lint Jobへpartial Statusを追加。
- `build_profile`/Source Import/Refresh Job追加。
- Human Correctionの度にFull Analysis自動Queue。
- metrics presetでSemantic Analyzer再実行。
- ProjectごとWorker追加。
- Redis/Celery追加。
