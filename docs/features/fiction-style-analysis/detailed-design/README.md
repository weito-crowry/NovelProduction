# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、v1詳細設計を領域別に管理する。Codex Lunaは本ディレクトリの設計を承認済み仕様として扱い、大規模な再設計判断を行わない。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | Local TXT/HTML/EPUB Import、Parser/Purge | v1.0 |
| 02 | [02-normalization.md](02-normalization.md) | Current Text、Normalization、Mapping | v1.0 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | Automatic/Semantic/Manual Structure | v1.0 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Mention、Entity Registry、Speaker | v1.0 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | Term Registry、初出、Explanation | v1.0 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene/Block Semantic、POV、Boundary | v1.0 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | Metric Registry、Basic/Semantic Metric | v1.0 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Corpus、Aggregate、Profile Version | v1.0 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | Fingerprint、Current Run、Job、Worker | v1.0 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | Effective View、Review、Override | v1.0 |
| 11 | [11-style-lint.md](11-style-lint.md) | Rule評価、Finding、Coverage | v1.0 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite 006〜008 Schema | v1.0 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | API、WebUI、Request Contract | v1.0 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | Unit/Integration/CI/Dogfood | v1.0 |
| 15 | [15-semantic-model-contracts.md](15-semantic-model-contracts.md) | Model Client、Prompt、JSON Contract | v1.0 |

## Codex向け実装順

| Phase | Scope | 主に読む設計 |
|---|---|---|
| SA-A | DB Foundation、Current Pointer、Job Worker、Runtime State | 02, 03, 09, 12, 14 |
| SA-B | Local Source Import/Purge、Reference Catalog | 01, 02, 12, 13, 14 |
| SA-C | Normalization、Automatic Structure、Basic Metric | 02, 03, 07, 09, 12, 14 |
| SA-D | Boundary、Entity/Term、Speaker/POV/Semantics、Model Contract、Work Analysis | 03, 04, 05, 06, 07, 09, 10, 12, 13, 14, 15 |
| SA-E | Corpus Membership、Aggregate、Profile | 07, 08, 09, 12, 13, 14 |
| SA-F | Manual Identity/Alias、Override、Review、Recompute | 04, 05, 06, 07, 09, 10, 12, 13, 14 |
| SA-G | Project Draft Capture、Style Lint | 02, 04, 07, 08, 10, 11, 12, 13, 14 |
| SA-H | WebUI、E2E、Dogfood | 01, 03, 08, 10, 11, 13, 14, 15 |

SA-A〜Hは既存NovelProduction Phase系列とは別系列。

## 実装上の確定事項

### Storage / Revision

- Project-local `story.db`へ`style_` Table群追加。
- Migrationは006/007/008。001〜005変更禁止。
- Current Text/Structureは`style_documents`明示Pointer。
- Latest RevisionをCurrentと推測しない。
- Text/Structure/Run/Aggregate/Profile Versionは履歴保持。

### Collection

- v1はLocal TXT/HTML/EPUB同期Importのみ。
- Site-specific Network Downloader/Refreshなし。
- HTML/XHTML:`beautifulsoup4` + stdlib `html.parser`。
- EPUB:`zipfile` + `xml.etree.ElementTree`。
- `lxml/html5lib/ebooklib`なし。
- Local Import Job/Staging Tableなし。

### Runtime / Model

- Persisted Jobは`analyze_document|analyze_reference_work|recompute_aggregate|run_lint`のみ。
- API Process全体でWorker Thread 1本。
- Work Jobは子Document Jobを作らずinline実行。
- Fingerprint JSONは09共通Utility。
- Semantic Model Contractは15を正本とする。
- API Model通信は`httpx` Runtime Dependency、OpenAI-compatible Chat Completions。
- OpenAI SDKなし。
- Prompt ID/Version、Input/Output JSON、Resolver候補選択、Repair規則を15から変更しない。

### Entity / Term / Semantic

- Reference Entity/TermはWork単位Stable Registry。
- Mention/Term Candidate ExtractorはRegistry非依存。
- Entity/Term ResolverはCache不可。
- Registry自然成長だけで過去Episodeを自動Stale化しない。
- Manual Registry CorrectionはStateでStale化。
- Term Explanationは1 Run×1 TermMention最大1 Persistence Row。
- Scene `unknown`とTaxonomy`unclear`を分離。
- Scene AxisはMetricではなくAggregate/Lint Selector用途。

### Metric / Aggregate / Profile

- 07の29 Metric Definition Registryを正本とする。
- MissingはMeasurement Row不存在。
- Aggregate値は常にREAL。Count Metricも平均/Percentileを丸めない。
- Measurement Row等重み。Work等重みではない。
- Profile IdentityとImmutable Versionを分離。
- Corpus ProfileはExact median/p25/p75 Aggregate IDを使用。
- Rule値はfinite REAL。Count Metric Ruleも小数Range可。
- Enabled Ruleはmin/max両方必須。

### Review / Lint

- ManualOverrideはAppend-only `set|clear|revert`。
- ReviewItemとInferenceReviewは別責務。
- ReviewItem Subject Registry / InferenceReview Registryは10を正本とする。
- Low-confidenceだけでReviewItemを量産しない。
- Missing Metric/SelectorはLint Coverageで扱い、割合だけでFailしない。
- 総合品質Score/自動本文修正なし。

## Codex実装時の標準運用

Codex向け指示には以下を明記する。

- 提示された設計を承認済み仕様として扱い、brainstorming / planning由来の再承認待ちで停止しない。
- サブエージェント、multi-agent、delegation、parallel agent work禁止。
- model escalation禁止。
- Codex自身が単一エージェントとして順番に作業する。
- 別エージェント調査/レビュー禁止。
- 不要な案比較、広範Refactor、Scope外改善禁止。
- 開始時Branch/Working Tree確認。
- 既存未Commit差分をReset/Stash/Checkout/Deleteしない。
- Shared main上なら通常作業Branchを作成し、既に適切なBranchなら重ねて作らない。
- 新規Worktreeは原則作らない。dirtyだけを理由に作らない。
- 必要なTest/Static Checkを実行し、未実施をPASS扱いしない。
- 実装後Commit/PushしChatGPTレビュー可能にする。
- Merge/Force Push/Rebase/Tag/Release/Deployは明示依頼なしで実施しない。

## 設計変更ルール

- 基本設計と矛盾する場合は実装を止め、ChatGPT側で設計修正する。
- Normalizer/Segmenter/Analyzer/Prompt/Taxonomy/Metric/Policyの結果互換性変更は該当Versionを上げる。
- Codexが独断で新規Analyzer、Metric、Table、Endpoint、Safety Gate、Review Gateを追加しない。
- Unrelated Refactor禁止。
- 既存Authoring Data、ManualOverride、ユーザー未Commit変更を破壊しない。

## レビュー前提

```text
ChatGPTでPhase Scope確定
-> Codex実装/Test/Commit/Push
-> ChatGPT GitHub Review
-> 必要なら限定修正
-> CI/Review完了
```
