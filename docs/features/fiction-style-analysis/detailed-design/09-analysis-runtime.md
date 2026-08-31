# 09 Analysis Runtime 詳細設計

## 1. 目的

Document解析Analyzerを依存DAGとして実行し、Revision・Analyzer/Policy・Model/Prompt・依存Run・Human StateをFingerprint化する。JobはProject-local DBへPersistし、API Process全体の単一同期Workerで処理する。

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

Normalization、Structure Materialization、Aggregate、Profile、Lintは対象外。

## 4. Analyzer契約

Analyzerは `id/version/deterministic/cacheable/dependencies/state_inputs/registry_input/input_scope` を宣言し、`AnalyzerContext` はDocument/Text/Structure、Dependency Run IDs、Policy Version、State Fingerprint、Registry Input Fingerprint、Configを持つ。

## 5. 初期Registry

| Analyzer | Cache | Dependency | State | Registry |
|---|---|---|---|---|
| scene-boundary-detector | yes | - | - | - |
| entity-mention-extractor | yes | - | - | - |
| entity-resolver | no | entity-mention-extractor | entity_registry | entity_registry |
| speaker-attribution | yes | entity-resolver | entity_registry, mention_resolution | - |
| entity-relation-extractor | yes | speaker-attribution | entity_registry, mention_resolution | - |
| term-candidate-extractor | yes | - | - | - |
| term-resolver | no | term-candidate-extractor | term_registry | term_registry |
| term-explanation-detector | yes | term-resolver | term_registry | - |
| scene-semantic-classifier | yes | - | - | - |
| block-semantic-classifier | yes | - | - | - |
| pov-classifier | yes | entity-resolver | entity_registry, mention_resolution | - |
| style-metrics-basic | yes | - | - | - |
| style-metrics-semantic | yes | speaker-attribution, term-resolver, term-explanation-detector, scene-semantic-classifier, block-semantic-classifier | effective_semantics | - |

Resolver 2種はIncremental Registryを更新するためCache不可。

## 6. AnalysisPolicy

Threshold/Sample値の正本はVersioned `AnalysisPolicy`。

```text
entity_resolution_auto_merge 0.90
speaker_effective 0.85
speaker_candidate 0.60
participant_effective 0.80
term_resolution_auto_merge 0.90
term_entity_auto_link 0.90
term_explanation_effective 0.85
scene_label_effective 0.80
block_semantic_effective 0.75
scene_boundary_auto_apply 0.85
scene_boundary_candidate_min 0.60
profile_min_episode_measurements 5
profile_min_scene_measurements 10
profile_min_character_utterances 10
profile_min_term_samples 5
```

## 7. Human State Fingerprint

Canonical Effective StateをHashする。

### entity_registry

- Manual Entity Identity
- Active Entity enabled/name/type Override
- Manual Alias
- Inferred Alias最新Review

### mention_resolution

Current Structure内Active `mention.entity_id` Override。

### term_registry

- Manual Term Identity
- Active Term enabled/label/type Override
- Manual Alias
- Inferred Alias最新Review

### effective_semantics

Speaker、Entity/Term Enabled、Term Novelty/Exact Match/Explanation、Scene Semantic/POV Override、Relevant Review。

Override Row IDではなくEffective値をHashする。

## 8. Registry Input Fingerprint

Entity/Term ResolverはRun開始時のEnabled RegistryをHashして保存する。含むもの:

- Enabled Identity ID + Effective Name/Type/Label
- Confirmed/Manual Alias

Historical Provenance用。後続EpisodeでRegistryが増えただけでは過去Resolverを自動Staleにしない。Explicit ReanalysisではResolverを必ず再実行する。

## 9. Dependency / Current Run

Dependencyは `style_analysis_run_dependencies` に保存する。

Current Runは:

- Current Analyzer/Policy/Default Config
- Current Human State
- Current Model/Prompt/Taxonomy/Metric Definition
- Current Dependency Run集合

と一致するRunだけを採用する。

`complete` はSucceededのみ。`subject_partial_allowed` はSucceeded優先、なければPartial可。同条件複数は `created_at DESC,id DESC`。

Stale RunへFallbackしない。

ResolverはCache不可だがDependent Run判定/表示用に最新Current RunをResolve可能。Current Registry Hash一致は要求しない。

## 10. Document Orchestration / Current Revision

StyleDocumentは:

```text
current_text_revision_id nullable
current_structure_revision_id nullable
```

を持つ。

Request `text_revision_id` はDocument所属必須。

### deterministic / Structure omitted

```text
指定TextRevision
-> Automatic Structure build/reuse
-> Basic Metric
```

Job `succeeded|partial` 終了時:

- `document.current_text_revision_id` がRequest TextRevisionと同一であることを確認。
- Final Automatic Structureを `current_structure_revision_id` に設定。

Job途中でCurrent Textが別Revisionへ変わっていた場合はPointerを更新せず `DOCUMENT_REVISION_CHANGED` WarningをJobへ残す。解析Run自体は指定Revisionの履歴として保持する。

### full / Structure omitted

```text
指定TextRevision
-> Automatic Base
-> Boundary Detector
-> Semantic Structure Materialize/Reuse
-> Entity/Term/Speaker/POV/Scene/Block
-> Basic/Semantic Metric
```

同じCurrent Text確認後、Final StructureをCurrent Structureへ設定する。

### Structure explicit

指定StructureをFinalとして解析。Boundary再実行なし。Current Structure Pointerは変更しない。

## 11. Reference Work Orchestration

`analyze_reference_work` Job。

Job開始時にCurrent CatalogをSnapshotする:

```text
ReferenceEpisode order_index ASC
+ reference episode id
+ episode StyleDocument id
+ document.current_text_revision_id
```

Current Text NULL EpisodeはFailure扱い。

各EpisodeをOrder順にStructure omitted Document Analysisとして実行する。途中RefreshでDocument Current Textが変わった場合、そのEpisodeは `DOCUMENT_REVISION_CHANGED` としてFailure扱いにし、新Current Textを同じWork Jobへ途中追加しない。Work再解析で新Catalogを取り直す。

Status:

- 全Episode Succeeded: succeeded
- Succeeded/Partial >=1 + 他Failure/Partial: partial
- Succeeded/Partial 0: failed
- Cancel: cancelled

Result:

```json
{
  "succeeded_episode_ids": [],
  "partial_episode_ids": [],
  "failed_episode_ids": []
}
```

## 12. AnalysisRun / Fingerprint

AnalysisRunはDocument/Analyzer/Text/Structure、Status、Fingerprint、Config、Policy、State/Registry Fingerprint、Model/Prompt、Warning/Error/Timestampsを保持する。

Fingerprint入力:

```text
analyzer id/version
input text hash
structure fingerprint
dependency fingerprints
config
policy
state fingerprint
registry input fingerprint if Resolver
model/prompt
taxonomy/metric versions
```

Cache Hitは `cacheable=true` + Current同Fingerprint Succeededのみ。

## 13. Partial Analyzer

- 全Subject成功: succeeded
- Usable Output >=1 + 一部失敗: partial
- Usable Output 0/全体Failure: failed

任意Failure率Thresholdなし。

## 14. Persisted Job

Job:

```text
job_type / payload_json / status / cancel_requested
progress_current / progress_total
result_json / warning_json
error_code / error_message
created_at / started_at / finished_at / version
```

Status `queued|running|succeeded|partial|failed|cancelled`。

Type:

```text
source_import
source_refresh
analyze_document
analyze_reference_work
recompute_aggregate
build_profile
run_lint
```

## 15. StyleJobWorker

API Process全体で同期Worker Thread 1本。

- `ready_project_ids` Deque + Set。
- Job Commit後 `worker.notify(project_id)`。
- Request-bound SQLite Connectionを渡さない。
- Worker自身がProject DBをOpen/Close。
- StartupでActive ProjectをScanしRunning Job/Runを `WORKER_INTERRUPTED` Failedへ変更、Queuedを回収。
- Project内FIFO。
- 1 Job後、同ProjectにQueuedがあればReady Queue末尾へ戻す。
- Project間Global FIFO不要。

## 16. Progress / Retry / Cancel

Work AnalysisはEpisode CountでProgress。Total不明JobはNULL可。

Retryは元Jobを再利用せず新Job Row。

Queued Cancel即時。RunningはCancel RequestedをSafe Point（Scene/Block/Source Episode/Work Episode/Model Call前後）で確認する。

## 17. Model Client

同期 `complete_json()`。Provider `disabled|openai_compatible`。

Provider/ModelはRunへ保存。API KeyはDB/通常Logへ保存しない。Full Analysisに追加確認Dialogなし。

Retry: Timeout/429/5xx最大1、Schema Repair最大1。

## 18. Test

- DAG/Dependency/Current Run
- State/Registry Fingerprint
- Resolver Cache不可
- Basic Metric Semantic State非依存
- Omitted AnalyzeでCurrent Structure更新
- Explicit StructureでPointer不変
- Current Text変更中のAnalyzeでPointer不変 + Warning
- Work Job SnapshotはDocument Current Text
- Work途中Refreshを途中取り込みしない
- Work Result/Progress
- Single Worker/FIFO/Fair Requeue/Recovery
- Retry/Cancel
- Provider Disabled/Retry/Repair

## 19. Codex禁止事項

- Current TextをReferenceEpisode別Pointerで二重管理
- Current RunをLatest成功だけで選択
- Resolver Cache Hit
- Registry成長だけで全過去Episode再解析
- Explicit StructureでCurrent Pointer変更
- Current Textが変わったのに古い解析結果をCurrent Structureへ設定
- ProjectごとWorker追加
- Request DB ConnectionをWorkerへ渡す
- Redis/Celery/中央Queue DB追加
- Async Event Loop追加
