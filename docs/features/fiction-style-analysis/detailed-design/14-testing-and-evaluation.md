# 14 Testing and Evaluation 詳細設計

## 1. 目的

Style Analysisの決定論的処理、DB整合性、API/WebUI、LLM推論、Source Adapterを再現可能に検証する。CIはlive site/modelへ依存させず、精度評価は別のdogfood/evaluationとして扱う。

上位仕様は `../basic-design.md`。

## 2. テスト層

```text
unit
integration
API/WebUI contract
manual dogfood/evaluation
```

同じ不変条件を全層へ重複配置しない。DB integrityはmigration/integration suite、UIはユーザーflow、Analyzerはschema/output contractへ責務を分ける。

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

既存naming conventionが異なる場合は既存に合わせる。

## 4. Deterministic unit gate

### Normalization

- input/output
- hash
- mapping
- code point span

### Segmentation

- Scene count/order
- Block global order/type/span
- Sentence span/order
- separator `scene_id=NULL`
- semantic Structure materialization

### Metrics

- metric name/version
- scalar/percentile
- sample_count
- basic/semantic metric分離

floatは `pytest.approx(..., abs=1e-9)`。

## 5. Fixture方針

巨大snapshot frameworkは導入しない。短い自作日本語fixtureを使い、必要fieldだけ明示assertする。

Source Adapter HTML fixtureはDOM構造だけ残し、本文をテスト用自作文へ置換する。外部作品本文を長くrepositoryへ入れない。

## 6. Source Adapter

`httpx.MockTransport` 等でnetworkをmockする。

必須case:

```text
Narou index + episode success
Narou parse fail
Kakuyomu success
Kakuyomu restricted page
redirect allowed/disallowed host
429 retry success/failure
response size limit
multi-episode fetch途中失敗 -> catalog未更新
EPUB binary snapshot hash
```

selector変更はadapter_version変更対象。

## 7. DB / Migration gate

CORE CIで以下を確認する。

- fresh 001→008
- 005 DB→006→008
- migration checksum
- `PRAGMA foreign_key_check` empty
- `PRAGMA integrity_check` = ok
- JSON/enum/CHECK
- purge cascade
- immutable Snapshot/TextRevision/ProfileVersion UPDATE拒否
- Entity/Term exactly-one scope
- Profile version unique

各integration scenarioの終了ごとに同じintegrity checkを繰り返さない。

## 8. Analyzer mocked test

Fake `SemanticModelClient` で固定JSONを返す。

検証:

- required context
- schema/version
- output validation
- invalid JSON/schema
- invalid offset
- timeout/429
- partial subject handling
- AnalysisPolicy threshold/fingerprint

prompt全文の完全一致testは作らない。

## 9. Gold dataset

`CORE/tests/style_analysis/gold/` に自作短文を置く。

固定件数ノルマは設けない。初期実装では、最低限次のカテゴリを各taskで1件以上含む小さなcurated setを作り、バグ修正ごとにregression fixtureを追加する。

### speaker

```text
explicit speech tag
adjacent action
two-person turn taking
three-person ambiguous
unknown
```

### Scene/Block semantics

```text
daily
exposition
meeting
introspection
action
conflict
unclear
```

### Term

```text
work-specific
common word
alias
explanation before/after name
no explanation
```

Dataset量を増やすこと自体を完了条件にしない。

## 10. Model evaluation

CI外script:

```text
API/scripts/evaluate_style_analysis.py
```

記録:

```text
provider/model
prompt/analyzer/policy version
dataset hash
precision/recall/F1 where applicable
unknown rate
schema failure rate
latency summary
```

結果はgitignored領域。

## 11. 品質指標の扱い

初期v1では固定precision/F1値をrelease gateにしない。小規模gold setで `false merge rate <=2%` のような統計的に意味の薄い閾値も置かない。

重視する順序:

1. schema/offset/DB invariantが壊れない
2. 明示speaker等の簡単なcaseを正しく処理
3. unknownを許容し誤った自動merge/話者確定を増やさない
4. model/prompt変更前後の相対比較を記録

評価結果はChatGPTレビュー時の判断材料とする。

## 12. Runtime integration

temp SQLite + fake modelで代表flowを通す。

```text
reference import
-> TextRevision
-> automatic structure
-> semantic boundary materialization
-> semantic analyzers
-> basic/semantic metrics
-> Corpus Aggregate
-> Profile Version
-> project draft capture
-> Lint
```

追加case:

```text
second run cache hit
policy version change
manual Structure指定
speaker override -> metric recompute
worker interrupted recovery
cancel
partial Scene analyzer
```

## 13. API contract

- project A/B isolation
- 404/409/413/422
- job 202 lifecycle
- explicit text_revision_id
- optional structure_revision_id
- Profile identity/version契約
- ReviewItem CAS
- override note optional
- purge
- raw source payloadが通常list/detailへ出ない

API key値そのものをレスポンスへserializeしないことはmodel config test 1箇所で確認し、各route testへ重複しない。

## 14. WebUI

Testing Library既存pattern。

- async描画を `findBy...` / `waitFor`
- disabled elementへuser-eventしない
- route後に古いDOM referenceを使わない
- polling fake timerは必要なtestだけ

必須flow:

```text
source import
job progress/retry
reference browse/purge
project draft capture
analysis basic/full
semantic boundary表示/manual split
Corpus membership
Profile Version edit + dirty guard
speaker override + Review conflict
Lint coverage/stale
Finding ignore
```

## 15. E2E

external site/modelはmock/fake server。

代表flow 1本:

```text
project open
-> local text import
-> deterministic analysis
-> Corpus create
-> Profile build
-> project fixture capture
-> Lint
-> Finding display
```

semantic flowはfake providerで別1本。

全細部をE2Eへ重複させない。

## 16. Live dogfood

CI外・明示実行。

### Source

- Narou/Kakuyomuからユーザー指定作品を少数episodeで開始
- title/order/本文抽出を目視
- 問題なければ作品全体へ拡張

毎回のrights checkbox等は不要。ログイン/有料壁回避はしない。

### Model

- configured provider/modelを確認
- representative episodeでfull analysis
- Scene境界、speaker、Term、semantic分類を目視
- 明確な誤りをgold regressionへ追加

## 17. CI commands

既存CIを正本とする。

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

WEBUI:

```text
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run test:e2e
```

MCPは変更しないが既存CI regressionとしてPASSを要求する。pre-commitもPASS。

## 18. Coverage

既存80% gate維持。coverageのためだけの低価値testを大量追加しない。失敗・境界・versioning・idempotencyを優先する。

## 19. Completion criteria

各SA Phase:

1. 対応詳細設計の必須要件
2. 必要なunit/integration
3. static checks
4. migration変更Phaseはmigration gate
5. existing CI
6. 実行できない検証は未実施理由を報告
7. commit/push
8. ChatGPT側レビュー

全Phaseで無関係なdogfoodや全品質評価を毎回要求しない。該当Phaseに必要な検証だけ実行する。

## 20. Codex実装時の禁止事項

- CIから実サイト/有料LLMへ接続しない。
- 外部作品本文をfixture/goldへコピーしない。
- flaky testをskipして完了扱いしない。
- coverage thresholdを下げない。
- 小規模gold datasetへ根拠のない精度gateを置かない。
- 全integration caseへ同じintegrity/safety assertionを重複追加しない。
- unrelated test refactorを広げない。