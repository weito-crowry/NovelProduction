# 09 Analysis Runtime 詳細設計

## 1. 目的

Document解析Analyzerを依存関係付きDAGとして実行し、入力revision・設定・model・promptをfingerprint化する。前処理・Corpus集約・Profile生成・LintをAnalysisRunへ無理に押し込まず、責務を分離する。

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

## 3. Runtime責務の分離

### AnalysisRunで管理するもの

既存 `TextRevision` / `StructureRevision` を入力としてDocument内に派生データを作るAnalyzer。

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

### AnalysisRunに入れないもの

- normalization: TextRevision作成処理。02のversion/hashで再利用。
- deterministic segmentation: StructureRevision作成処理。03のversion/fingerprintで再利用。
- semantic Structure materialization: 03 StructureService。
- Aggregate: 08 AggregateService/job。
- Profile生成: 08 ProfileService/job。
- Lint: 11 LintRun/job。

これにより `AnalysisRun` が「自分のinputを自分で生成する」循環を作らない。

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

AnalysisServiceがtransaction/fingerprintを管理する。

## 5. AnalysisPolicy

confidence thresholdやsample最小値を各Analyzerへ散在させない。

`analysis_policy.py` にversioned dataclassを置く。

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

初期値は実装判断ではなく本設計で確定。将来調整時はpolicy versionを上げ、fingerprintへ含める。

## 6. Orchestration

### deterministic preset

```text
指定TextRevision
-> automatic StructureRevisionを作成/reuse
-> style-metrics-basic
```

### full preset

```text
指定TextRevision
-> automatic StructureRevisionを作成/reuse
-> scene-boundary-detector(base structure)
-> semantic StructureRevisionをmaterialize/reuse
-> entity mention/resolution
-> term candidate/resolution
-> speaker/relation
-> term explanation
-> scene/block/POV semantics
-> style-metrics-basic(final structure)
-> style-metrics-semantic
```

Boundary Detectorがcandidateを1件も自動適用しなければbase structureをfinalとしてreuseする。

manual StructureRevisionをrequestで明示した場合、Scene Boundary Detectorを再適用せず、そのmanual revisionをfinal structureとして後続解析する。

## 7. Dependency DAG

final StructureRevision確定後:

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

cycleはregistry初期化時に検出し起動error。

## 8. AnalysisRun

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

## 9. Fingerprint

canonical JSON SHA-256。

```text
analyzer_id/version
input text hash
structure fingerprint
sorted dependency fingerprints
config
policy version
model provider/id if model-based
prompt id/version if model-based
taxonomy version if applicable
metric definition versions if applicable
```

serialization: sorted keys、compact separators、UTF-8、ensure_ascii=false。

`succeeded` fingerprint一致をcache hit。`partial/failed` は自動reuseしない。

## 10. Partial policy

「失敗率10%」のような任意閾値は設けない。

Scene/Block単位Analyzer:

- 1件以上usable outputがあり、一部subjectだけ失敗: `partial`
- usable outputが0件、provider/contract/storage等の全体失敗: `failed`
- 全subject成功: `succeeded`

`partial` の成功subject出力は保持する。07がcoverageを見て、complete scopeだけMeasurementを生成する。

これにより1 Scene失敗だけで全episode解析を捨てない。

## 11. 変更伝播

| 変更 | stale/recompute |
|---|---|
| raw text/normalizer | Structure以降全部 |
| automatic segmenter | Boundary/Semantic/Metric |
| semantic/manual Structure | Semantic/Metric |
| entity extractor | resolver/speaker/relation、speaker metric |
| speaker override | speaker metric、Aggregate、Lint |
| term analyzer | term metric、Aggregate、Lint |
| taxonomy/classifier | scene Aggregate、semantic metric、Lint |
| MetricDefinition | Aggregate/Profile/Lint |
| AnalysisPolicy | 影響するAnalyzer/Structure/Profile以降 |
| Profile version | Lintのみ |

row deleteでinvalidateしない。

## 12. Persisted job

v1はRedis/Celery不要。API process内worker thread 1本。

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

FIFO、同時実行1。

## 13. 再起動

API起動時、`running` job/runを `failed / WORKER_INTERRUPTED` にする。queuedは処理再開。runningを自動再queueしない。

## 14. Transaction

AnalysisRun:

1. running状態commit
2. Analyzer計算
3. output + final run statusを1 transactionでpersist
4. persistence失敗時rollback、run failed

partial出力も同じ1 transactionで保存する。

network fetch中はtransactionを開かない（01）。

## 15. Cancellation

queuedは即cancel。runningは`cancel_requested=1`。

確認境界:

- Scene/Block処理の間
- source episode取得の間
- model call前後

requestを強制killしない。cancelled outputはeffectiveに使わない。

## 16. SemanticModelClient

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

## 17. API model adapter

v1:

```text
disabled
openai_compatible
```

設定:

```text
STYLE_ANALYSIS_LLM_PROVIDER
STYLE_ANALYSIS_LLM_BASE_URL
STYLE_ANALYSIS_LLM_API_KEY
STYLE_ANALYSIS_LLM_MODEL
STYLE_ANALYSIS_LLM_TIMEOUT_SECONDS default 60
```

API keyはDB/log/AnalysisRunへ保存しない。

`disabled` ならfull presetを開始できず `ANALYZER_PROVIDER_UNAVAILABLE`。deterministicは利用可能。

UIは現在のprovider/model名を表示する。ユーザーが明示的に「Full analysis」を実行する操作自体を送信同意とみなし、追加checkboxや毎回の確認dialogは設けない。

## 18. Model call

- temperature=0
- timeout/429/5xx retry最大1回
- schema invalidはrepair retry最大1回
- repair失敗は対象subject失敗としてpartial/failed判定
- raw response全文を通常logへ出さない

## 19. API

```text
POST /projects/{project_id}/style-analysis/documents/{document_id}/analyze
GET  /projects/{project_id}/style-analysis/jobs/{job_id}
POST /projects/{project_id}/style-analysis/jobs/{job_id}/cancel
POST /projects/{project_id}/style-analysis/jobs/{job_id}/retry
GET  /projects/{project_id}/style-analysis/analysis-runs
GET  /projects/{project_id}/style-analysis/analysis-runs/{run_id}
```

`analyze`:

- `text_revision_id` 必須。
- `structure_revision_id` optional。
- omittedなら指定TextRevisionからautomatic/semantic structureをbuild/reuse。
- providedならそのStructureRevisionがTextRevision所属であることを検証し、manual/semantic/automaticいずれも使用可。

## 20. テスト

- DAG order/cycle
- policy version fingerprint
- cache hit/miss
- manual StructureでBoundary Detector skip
- semantic Structure materialization
- partial subject保持
- failed no output
- basic metric provider不要
- restart recovery
- FIFO/cancel
- provider disabled
- model retry/repair

## 21. Codex実装時の禁止事項

- normalize/segment/Aggregate/Profile/Lintを無理にAnalysisRunへ入れない。
- Celery/Redis/parallel workerを追加しない。
- partial/failedをcache hitにしない。
- confidence thresholdをAnalyzerごとに重複hard-codeしない。
- provider SDKをCOREへ入れない。
- model/provider変更をfingerprintから隠さない。
- full analysis開始時に不要な確認dialogを追加しない。