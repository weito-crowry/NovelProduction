# 14 Testing and Evaluation 詳細設計

## 1. 目的

Style Analysisの決定論的処理、DB整合性、API/WebUI、LLM推論、外部source adapterを再現可能に検証する。CIをlive network/model依存にせず、モデル精度はgold datasetとして別管理する。

上位仕様は `../basic-design.md`。

## 2. 基本原則

テストを4層に分ける。

```text
unit
integration
contract/UI
manual dogfood/evaluation
```

CIで外部小説サイト・LLM providerへ実通信しない。

## 3. 実装先

```text
CORE/tests/style_analysis/
  fixtures/
  gold/
  test_normalization.py
  test_segmentation.py
  test_entities.py
  test_terms.py
  test_semantics.py
  test_metrics.py
  test_runtime.py
  test_review.py
  test_profiles.py
  test_lint.py
  test_storage.py

API/tests/style_analysis/
  fixtures/
  test_source_adapters.py
  test_style_routes.py
  test_style_jobs.py
  test_model_client.py

WEBUI/frontend/src/features/styleAnalysis/
  *.test.tsx

WEBUI/frontend/e2e/
  style-analysis.spec.ts
```

既存test naming/conventionsが異なる場合は既存に合わせるが、機能scopeはstyle_analysis配下にまとめる。

## 4. Deterministic unit gate

以下はすべて完全一致でCI gateする。

### Normalization

- input/output text
- SHA-256
- mapping segments
- code point span

### Segmentation

- Scene count/order
- Block count/type/span/text
- Sentence count/span
- warning codes

### Metrics

- metric name/version
- scalar value
- percentile
- sample_count

float比較は式由来値に対し `pytest.approx(..., abs=1e-9)`。

## 5. Fixture snapshot方針

巨大golden JSONを無差別更新するsnapshot test frameworkは導入しない。

fixture inputは短い日本語本文、expectedはPython literal/JSONとして必要fieldだけ明示する。

source adapter HTML fixtureは実サイトから保存したものを必要最小限に縮約し、著作物本文を長くrepositoryへ含めない。本文はテスト用自作文へ置換してDOM構造だけ維持する。

## 6. Source Adapter test

live networkをmock transportへ置換する。`httpx.MockTransport` 等、既存dependencyで実装できるものを使う。

必須case:

```text
Narou work index success
Narou episode success
Narou parse fail
Kakuyomu success
Kakuyomu paid/restricted rejection
redirect allowed
redirect disallowed host
429 -> retry -> success
429 repeated -> failure
response size limit
partial multi-episode fetch -> import incomplete
```

HTML selectorを変更した場合、fixture testを先に更新せず、旧fixture compatibilityが必要かを確認する。実サイト変更に追従する場合はadapter_versionを上げる。

## 7. DB/Migration gate

CORE CIで以下を必須化。

- fresh 001→008
- 005既存DB→006→008
- `PRAGMA foreign_key_check` empty
- `PRAGMA integrity_check` = ok
- migration checksum current
- illegal enum/JSON/check rejected
- cascade purge
- snapshot/text revision UPDATE rejected

既存migration checksum testを拡張する。001〜005 fixture/checksumを変更しない。

## 8. Analyzer mocked test

SemanticModelClientはfake implementationを使用する。

Fakeはrequest内容に応じた固定JSONを返す。テスト中にprompt全文を脆いstring完全一致にせず、次を検証する。

- required contextが含まれる
- response schema ID/version
- analyzer config
- output validation

modelが不正JSON、schema欠落、不正offset、timeout、429を返すcaseを作る。

## 9. Gold dataset

`CORE/tests/style_analysis/gold/` に著作権上問題のない自作短文を置く。

初期dataset:

```text
20 Scene: speaker attribution
30 Scene: scene semantics
20 Scene: block semantics
20 Scene: term/explanation
```

同一Sceneを複数taskで共有可。

Gold recordは以下を持つ。

```json
{
  "id": "speaker-001",
  "text": "...",
  "expected": {...},
  "notes": "明示的な発話タグ"
}
```

外部作品本文をgold datasetへコピーしない。

## 10. Model evaluation

外部modelを使う評価scriptはCI外。

```text
API/scripts/evaluate_style_analysis.py
```

入力: gold dataset, configured SemanticModelClient。

出力:

```text
provider/model
prompt/analyzer version
timestamp
dataset hash
precision/recall/F1 where applicable
unknown rate
schema failure rate
latency summary
```

結果は `runs/` 等gitignored領域へ保存し、勝手にrepositoryへcommitしない。

## 11. 初期品質指標

硬いproduction gateではなく評価目標。

### speaker

明示speech tag subset:

```text
precision >= 0.95
```

全dialogue:

```text
unknown rateを併記
```

誤speakerを減らすためrecallよりprecision優先。

### Entity resolution

```text
false merge rate <= 2%
```

未統合は許容する。

### Term

work-specific term precision目標 >=0.85。

### Scene semantic

macro F1を記録するが、初期固定thresholdは置かない。taxonomy改善時の相対退行を確認する。

## 12. Runtime integration

in-memory/temp SQLite + fake modelでDAG全体を通す。

必須scenario:

```text
imported reference episode -> normalize -> structure -> semantics -> metrics
cache hit on second run
normalizer version change -> downstream re-run
speaker manual override -> metric recompute
corpus aggregate -> profile -> project lint
worker interrupted recovery
cancel queued/running
```

各scenario終了後にDB integrity check。

## 13. API contract test

既存FastAPI TestClient/httpx patternを使用する。

- project A/B isolation
- 404/409/413/422 mapping
- job 202 lifecycle
- API key非露出
- full raw source payloadが通常list/detailに出ない
- purge後本文取得不可
- explicit revision IDs required

project ID省略routeを追加しない。

## 14. WebUI unit/integration

Testing Library既存patternを使用。

重要:

- 非同期描画完了を `findBy...` / `waitFor` で待つ
- disabled elementへ `user.clear/type` しない
- route navigation後、古いDOM referenceを再利用しない
- fake timer使用時はpolling queryとuser-eventの相互作用を明示処理

必須flow:

```text
source import validation
job progress/retry
reference work browse/purge
capture project draft
analysis run
corpus membership
profile version editing + dirty guard
review speaker override + version conflict
scene boundary accept
lint stale detection
finding ignore
```

## 15. E2E

Playwright E2Eはexternal site/modelをmockまたはfake serverにする。

1本の代表flow:

```text
project open
-> local text fixture import
-> deterministic analysis
-> corpus create
-> profile build
-> project fixture capture
-> lint
-> finding表示
```

semantic model E2Eはfake provider serverをAPIに設定して別caseで実施。

## 16. Live dogfood

CIとは別に明示実行する。

### Source dogfood

- ユーザーが利用権限を確認した1作品だけ
- Narou/Kakuyomu各最大1作品
- 少数episodeで開始
- rate limitを遵守
- 取得後タイトル/episode順/本文冒頭を人間確認

### Model dogfood

- private corpusを外部providerへ送る前にprovider設定を確認
- AnalysisRunにprovider/model/prompt version記録
- speaker/term/sceneのReviewQueueを目視

Dogfood失敗をテストfixtureの推測修正で隠さない。

## 17. CI commands

既存CIを正本とし、少なくとも変更対象ごとに以下を通す。

CORE:

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_core --cov-report=term-missing
```

API:

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -W error
uv run pytest -W error --cov=src/novel_api --cov-report=term-missing
```

MCP:

Style Analysisで変更しないが既存CI regressionとして全てPASSを要求する。pre-commitもPASS。

WEBUI:

```text
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run test:e2e
```

## 18. Coverage

既存80% gateを維持。新機能のためにthresholdを下げない。

coverage目的の意味のないbranch testを大量追加せず、失敗・境界・versioning・idempotencyを優先する。

## 19. Completion criteria

各実装Phase完了時に以下を満たす。

1. 対応詳細設計の必須要件実装
2. unit/integration追加
3. static checks PASS
4. migration integrity PASS
5. existing MCP tool inventory PASS
6. unrelated既存挙動の回帰なし
7. 実行できない検証がある場合は未実施理由を明記
8. commit/push後にChatGPT側レビュー可能な状態

Codexの自己レビューだけで完了扱いにしない。

## 20. Codex実装時の禁止事項

- CIから実サイト/有料LLM APIへ接続しない。
- 外部作品本文をfixture/goldへコピーしない。
- flaky testをskipして完了扱いしない。
- coverage thresholdを下げない。
- 既存失敗と断定せず、変更との因果を確認する。
- 実行できなかったtestをPASSと報告しない。
- unrelated test refactorを広げない。
