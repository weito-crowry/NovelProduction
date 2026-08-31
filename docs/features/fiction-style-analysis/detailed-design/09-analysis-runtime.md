# 09 Analysis Runtime 詳細設計

## 1. 目的

Document解析Analyzerを依存関係付きDAGとして実行し、入力revision・設定・model・promptをfingerprint化する。前処理、Structure作成、Corpus集約、Profile生成、LintをAnalysisRunへ押し込まず責務を分離する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  runtime_models.py
  analyzer.py
  analyzer_registry.py
  analysis_policy.py
  analysis_repository.py
  analysis_service.py
  fingerprint.py
  model_client.py
  prompts/

API/src/novel_api/style_analysis/
  runtime.py
  model_client.py
```

## 3. Runtime責務

### AnalysisRun対象

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

### AnalysisRun対象外

- normalization: 02 TextRevision作成
- deterministic segmentation: 03 automatic StructureRevision
- semantic Structure materialization: 03 StructureService
- Aggregate: 08 AggregateService/job
- Profile: 08 ProfileService/job
- Lint: 11 LintRun/job

## 4. Analyzer契約

```python
@dataclass(frozen=True)
class AnalyzerContext:
    document_id: int
    text_revision_id: int
    structure_revision_id: int
    dependency_run_ids: tuple[int, ...]
    policy_version: int
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
    dependencies: tuple[str, ...]
    input_scope: str
    def run(self, context: AnalyzerContext) -> AnalyzerResult: ...
```

AnalysisServiceがrun state/fingerprint/transactionを管理する。

## 5. AnalysisPolicy

唯一のthreshold/sample policy正本。

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

調整時はversionを上げfingerprintへ含める。

## 6. Effective AnalysisRun選択

同一target/analyzerに複数runが存在し得るため、repositoryに1つの選択規則を実装する。

候補条件:

```text
same document_id
same text_revision_id
same structure_revision_id
same analyzer_id
status in succeeded | partial
```

### succeededを要求するconsumer

Basic document Metric等、complete outputが必要なconsumerは最新の `succeeded` runだけを選ぶ。

### partial subjectを利用可能なconsumer

Scene単位のSemantics表示や07のcomplete Scene Metricは、最新 `succeeded` がなければ最新 `partial` runの成功subject outputを利用可能。

「最新」は `created_at DESC, id DESC`。fingerprint一致の古いrunを新しい異fingerprint runより優先しない。

ManualOverrideはrun選択後にEffective Viewとしてoverlayする。

## 7. Orchestration

### deterministic preset

```text
TextRevision
-> automatic Structure build/reuse
-> style-metrics-basic
```

### full preset: structure未指定

```text
TextRevision
-> automatic base Structure build/reuse
-> scene-boundary-detector(base)
-> semantic Structure materialize/reuse
-> final Structure決定
-> Entity/Term/Speaker/Semantics analyzers
-> style-metrics-basic(final)
-> style-metrics-semantic(final)
```

Boundary Detector runのcandidate Annotationから03がsemantic Structureを作る。生成時 `style_structure_analysis_sources` にRun provenanceを記録する。

### full preset: structure明示

requestのStructureRevisionをfinalとして使用する。`manual` だけでなく `automatic/semantic` も指定可。**明示Structureがある場合はScene Boundary Detectorを再実行しない。** ユーザーがrevisionを固定した意図を優先する。

## 8. Dependency DAG

final Structure確定後:

```text
entity-mention-extractor
  -> entity-resolver
      -> speaker-attribution
      -> entity-relation-extractor

term-candidate-extractor
  -> term-resolver
      -> term-explanation-detector

scene-semantic-classifier
block-semantic-classifier
pov-classifier

final structure -> style-metrics-basic
speaker-attribution
term-explanation-detector
scene-semantic-classifier
block-semantic-classifier
  -> style-metrics-semantic
```

cycleはregistry初期化時error。

## 9. AnalysisRun

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

status:

```text
queued
running
succeeded
partial
failed
cancelled
```

## 10. Fingerprint

canonical JSON SHA-256。

```text
analyzer_id/version
input text hash
structure fingerprint
sorted dependency run fingerprints
config
policy version
model provider/id if model-based
prompt id/version if model-based
taxonomy version if applicable
MetricDefinition versions if applicable
```

serialization: sorted keys, compact separators, UTF-8, ensure_ascii=false。

`succeeded` fingerprint一致のみcache hit。`partial/failed` はreuseしない。

## 11. Scene Boundary provenance

Boundary Detector自身はbase StructureRevisionを入力に通常のAnalysisRunを作る。

- `AnalysisRun.structure_revision_id` = automatic base。
- candidateは06/03契約のAnnotation。
- semantic StructureはRun outputではなく03 StructureServiceのmaterialized projection。
- semantic Structure作成後 `style_structure_analysis_sources` でRunをlink。
- semantic Structure fingerprintは03定義を正本。

後続Analyzerはsemantic Structureを入力とするため、dependency_run_idsへBoundary Detectorを直接含める必要はない。Structure fingerprintがそのprovenanceを表現する。

## 12. Partial policy

任意失敗率thresholdは置かない。

Scene/Block単位Analyzer:

- 全subject成功 -> succeeded
- usable output >=1かつ一部失敗 -> partial
- usable output 0、またはprovider/contract/storage全体失敗 -> failed

partial成功subject outputは保持。07がscope completenessを判断する。

## 13. 変更伝播

| 変更 | stale/recompute |
|---|---|
| raw/normalizer | Structure以降全部 |
| automatic segmenter | Boundary/Semantic/Metric |
| semantic/manual Structure | Semantic/Metric |
| Entity analyzer | resolver/speaker/relation、speaker Metric |
| speaker override | speaker Metric、Aggregate、Lint |
| Term analyzer/Term attribute | term Metric、Aggregate、Lint |
| taxonomy/classifier | scene Aggregate、semantic Metric、Lint |
| MetricDefinition | Aggregate/Profile/Lint |
| AnalysisPolicy | 影響Analyzer/Structure/Profile以降 |
| ProfileVersion | Lintのみ |

row deleteでinvalidateしない。

## 14. Persisted job

API process内worker thread 1本、FIFO、同時実行1。

```text
style_jobs
  id
  job_type
  payload_json
  status
  cancel_requested
  created_at
  started_at
  finished_at
  error_code
  error_message
  version
```

job:

```text
source_import
analyze_document
recompute_aggregate
build_profile
run_lint
```

## 15. Restart

起動時 `running` job/runを `failed / WORKER_INTERRUPTED`。queuedは続行。running自動requeueなし。

## 16. Transaction

AnalysisRun:

1. running commit
2. compute
3. output + final statusを1 transaction
4. persistence失敗rollback + run failed

partial outputも1 transaction。

Source fetch transactionは01。

## 17. Cancellation

queued即cancel。runningは`cancel_requested=1`。

check point:

- Scene/Block間
- source episode取得間
- model call前後

外部request強制killなし。cancelled outputはeffectiveに使わない。

## 18. SemanticModelClient

```python
@dataclass(frozen=True)
class ModelRequest:
    system_prompt: str
    user_prompt: str
    response_schema: Mapping[str, object]
    temperature: float

@dataclass(frozen=True)
class ModelResponse:
    parsed: Mapping[str, object]
    provider: str
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    request_id: str | None

class SemanticModelClient(Protocol):
    def complete_json(self, request: ModelRequest) -> ModelResponse: ...
```

## 19. API model adapter

v1:

```text
disabled
openai_compatible
```

```text
STYLE_ANALYSIS_LLM_PROVIDER
STYLE_ANALYSIS_LLM_BASE_URL
STYLE_ANALYSIS_LLM_API_KEY
STYLE_ANALYSIS_LLM_MODEL
STYLE_ANALYSIS_LLM_TIMEOUT_SECONDS default 60
```

API keyはDB/log/AnalysisRunへ保存しない。

Full analysis明示実行を送信開始操作とし、追加checkbox/dialogは必須にしない。UIはprovider/model名を表示する。

## 20. Model call

- temperature=0
- timeout/429/5xx retry最大1回
- schema invalid repair retry最大1回
- repair失敗は対象subject失敗
- raw response全文を通常logへ出さない

## 21. API

```text
POST /projects/{project_id}/style-analysis/documents/{document_id}/analyze
GET  /projects/{project_id}/style-analysis/jobs/{job_id}
POST /projects/{project_id}/style-analysis/jobs/{job_id}/cancel
POST /projects/{project_id}/style-analysis/jobs/{job_id}/retry
GET  /projects/{project_id}/style-analysis/analysis-runs
GET  /projects/{project_id}/style-analysis/analysis-runs/{run_id}
```

analyze:

- `text_revision_id` required。
- `structure_revision_id` optional。
- provided Structureは同document/TextRevision所属を検証。

## 22. Test

- DAG/cycle
- policy fingerprint
- effective run selection succeeded/partial/latest
- cache hit/miss
- omitted StructureでBoundary+semantic materialize
- explicit StructureでBoundary skip
- source link provenance
- partial subject保持
- basic Metric provider不要
- restart/FIFO/cancel
- provider disabled
- retry/repair

## 23. Codex禁止事項

- normalize/segment/Aggregate/Profile/LintをAnalysisRunへ入れない。
- Celery/Redis/parallel worker追加。
- partial/failed cache hit。
- threshold重複hard-code。
- provider SDKをCOREへ入れる。
- model/providerをfingerprintから隠す。
- explicit Structure指定時にScene Boundaryを勝手に再適用。