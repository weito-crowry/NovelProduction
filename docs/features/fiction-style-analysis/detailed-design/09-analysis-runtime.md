# 09 Analysis Runtime 詳細設計

## 1. 目的

Analyzerを依存関係付きDAGとして実行し、入力revision・設定・model・promptをfingerprint化して再利用可能にする。解析失敗やAPI再起動が既存結果を壊さず、必要範囲だけ再実行できるruntimeを定義する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  runtime_models.py
  analyzer.py
  analyzer_registry.py
  analysis_repository.py
  analysis_service.py
  fingerprint.py
  model_client.py
  prompts/

API/src/novel_api/style_analysis/
  runtime.py
  model_client.py
```

COREはprovider非依存。APIが外部LLM通信を担当する。

## 3. Analyzer契約

```python
@dataclass(frozen=True)
class AnalyzerContext:
    document_id: int
    text_revision_id: int
    structure_revision_id: int | None
    dependency_run_ids: tuple[int, ...]
    config: Mapping[str, object]

@dataclass(frozen=True)
class AnalyzerResult:
    status: Literal["succeeded", "partial"]
    output_counts: Mapping[str, int]
    warnings: tuple[str, ...]

class Analyzer(Protocol):
    id: str
    version: int
    deterministic: bool
    dependencies: tuple[str, ...]
    input_scope: str
    def config_schema(self) -> Mapping[str, object]: ...
    def run(self, context: AnalyzerContext) -> AnalyzerResult: ...
```

Analyzerはtransaction境界を自前で作らず、AnalysisServiceがrun単位transactionを管理する。

## 4. 初期Analyzer Registry

IDを固定する。

```text
normalize-text
segment-structure
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
scene-boundary-candidate
style-metrics
aggregate-builder
profile-generator
style-lint
```

`normalize-text` と `segment-structure` は厳密には前処理だが、runtime上はversion/fingerprintを統一管理する。

## 5. 依存DAG

初期依存を以下で固定する。

```text
normalize-text
  -> segment-structure
      -> entity-mention-extractor
          -> entity-resolver
              -> speaker-attribution
              -> entity-relation-extractor
      -> term-candidate-extractor
          -> term-resolver
              -> term-explanation-detector
      -> scene-semantic-classifier
      -> block-semantic-classifier
      -> pov-classifier
      -> scene-boundary-candidate

speaker-attribution
term-explanation-detector
scene-semantic-classifier
block-semantic-classifier
pov-classifier
  -> style-metrics

style-metrics
  -> aggregate-builder
      -> profile-generator

style-metrics + selected profile
  -> style-lint
```

DAG cycleはregistry初期化時に検出し、起動失敗とする。

## 6. AnalysisRun

```text
id
document_id
analyzer_id
analyzer_version
text_revision_id
structure_revision_id nullable
status
fingerprint
config_json
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

`running` を再起動後にsucceededへ推測しない。

## 7. Fingerprint

SHA-256 canonical JSONで作る。

```text
hash(
  analyzer_id,
  analyzer_version,
  input_text_sha256,
  structure_revision fingerprint if required,
  sorted dependency fingerprints,
  canonical analyzer config,
  model provider/id if model-based,
  prompt id/version if model-based,
  taxonomy version if applicable,
  metric version set if applicable
)
```

JSON serializationは `sort_keys=True`, separators `(',', ':')`, UTF-8, `ensure_ascii=False` 相当で固定する。

fingerprint一致かつstatus=`succeeded` のrunがあれば再利用する。`partial` は自動cache hitに使わない。

## 8. 変更伝播

再解析範囲を固定する。

| 変更 | invalidate |
|---|---|
| Source raw text | normalization以降全部 |
| normalizer version | structure以降全部 |
| segmenter version/manual structure | semantic/metric以降 |
| entity extractor | entity resolver/speaker/relation、依存metric |
| speaker override | character/speaker metric、aggregate、lint |
| term analyzer | term metric、aggregate、lint |
| scene taxonomy/classifier | scene filter aggregate、semantic metric、lint |
| metric version | aggregate/profile/lint |
| profile edit | lintのみ |

DB rowをdeleteしてinvalidateしない。新run/fingerprintを作る。

## 9. Job実行方式

NovelProductionはローカル単一ユーザー・単一API processを前提とし、v1でRedis/Celery等を導入しない。

APIでpersisted job queueを実装する。

```text
style_jobs
  id
  job_type
  payload_json
  status
  created_at
  started_at
  finished_at
  error_code
  error_message
```

API起動時にworker threadを1本だけ起動する。`queued` をFIFOで処理する。同時解析数は1。

job type:

```text
source_import
analyze_document
recompute_aggregate
build_profile
run_lint
```

## 10. 再起動復旧

API起動時:

1. `style_jobs.status=running` を `failed` へ変更
2. error_code=`WORKER_INTERRUPTED`
3. 対応する `AnalysisRun.running` もfailedへ変更
4. queued jobはそのまま処理再開

running jobを自動再queueしない。ユーザーがRetryする。

## 11. Transaction

Analyzer出力はrun単位でatomic。

- run開始: status runningをcommit
- Analyzerは一時的なPython objectとして結果を組み立てる
- persistence transactionで結果一式をinsert
- 成功commit後にrunをsucceeded
- persistence失敗時rollbackしrun failed

大量outputでも途中commitしない。1episode上限は02で制御済み。

Source importはepisodeごとのsnapshot保存を許すが、Reference Workを「import complete」にするtransactionは全episode取得後に行う。

## 12. Cancellation

queued jobは即cancel可能。
running jobは`cancel_requested=1`を設定し、Analyzerの安全な境界で確認する。

安全境界:

- Scene処理の間
- HTTP episode取得の間
- model callの前後

外部HTTP request自体を強制killしない。

cancelled runの部分出力はeffective viewへ採用しない。

## 13. SemanticModelClient

CORE Protocol:

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

Analyzerはraw HTTP responseを扱わない。

## 14. API側model adapter

v1は以下2modeのみ。

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

`disabled` でsemantic analyzer要求が来たら `ANALYZER_PROVIDER_UNAVAILABLE`。deterministic analyzerは実行可能。

`openai_compatible` はAPI側 `httpx` でJSON応答を取得する。provider差異は `model_client.py` 内へ隔離し、Analyzerへ持ち込まない。

API keyをDB・log・AnalysisRunへ保存しない。

## 15. Model call policy

- temperature=0固定
- max retry=1
- retry対象はtimeout/429/5xx
- schema validation失敗時は同promptで1回だけrepair retry
- repair後も不正ならrun partialまたはfailed
- raw model response全文を通常logへ出さない

入力本文を第三者providerへ送信することになるため、UIでsemantic analysis開始前にprovider名を明示する。local/private corpusでも外部provider送信を自動で行わない。

## 16. Partial

Scene単位Analyzerで一部Scene失敗時:

- 失敗率 <=10%: run `partial`
- >10%: run `failed`

partial結果は表示可能だがAggregate/Profileへ使用しない。

失敗Scene IDsをwarning_jsonへ保存する。

## 17. Analysis orchestration API

```text
POST /projects/{project_id}/style-analysis/documents/{document_id}/analyze
GET  /projects/{project_id}/style-analysis/jobs/{job_id}
POST /projects/{project_id}/style-analysis/jobs/{job_id}/cancel
POST /projects/{project_id}/style-analysis/jobs/{job_id}/retry
GET  /projects/{project_id}/style-analysis/analysis-runs
GET  /projects/{project_id}/style-analysis/analysis-runs/{run_id}
```

`analyze` requestは `preset=deterministic|full`。

- deterministic: normalization/structure/basic metrics
- full: semantic + metricsまで

Profile/aggregate/lintは別job。

## 18. テスト

- DAG order
- cycle detection
- fingerprint canonicalization
- cache hit/cache miss
- version change invalidation
- failed runがcacheにならない
- running job restart recovery
- queued FIFO
- cancellation
- partial threshold 10%
- provider disabled
- model retry 1回
- schema repair retry
- API keyがlog/DBへ入らない

## 19. Codex実装時の禁止事項

- Celery/Redis/外部queueを導入しない。
- parallel analyzer実行を追加しない。
- fingerprint不一致結果を再利用しない。
- failed/partial runをeffective aggregateへ入れない。
- provider SDKをCOREへ入れない。
- API keyをAnalysisRunへ保存しない。
- model変更をanalyzer version変更なしで隠蔽しない。
