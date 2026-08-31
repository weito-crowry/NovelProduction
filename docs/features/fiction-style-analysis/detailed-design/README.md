# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、詳細設計を領域別に管理する。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | Source Adapter、Import/Refresh/Purge | v0.4 |
| 02 | [02-normalization.md](02-normalization.md) | StyleDocument Current Text、Normalization、Mapping | v0.4 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | Current Structure、Automatic/Semantic/Manual | v0.4 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Mention Candidate、Entity Registry、Speaker | v0.4 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | Term Candidate/Registry、Attribute Reduction、説明 | v0.4 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene/Block Semantic、POV、Boundary | v0.3 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | Basic/Semantic Metric | v0.3 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Membership、Aggregate Count、Profile Version | v0.4 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | Current Run、Work Job、Single Worker | v0.4 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | Effective View、Set/Clear/Revert | v0.3 |
| 11 | [11-style-lint.md](11-style-lint.md) | Finding、Evidence、Coverage | v0.1 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite 006〜008、Current Pointer、Provenance | v0.4 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | API、Current Structure、Manual Identity、UI | v0.4 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | Unit/Integration/CI/Dogfood | v0.4 |

## Codex向け実装順

| Phase | Scope | 主に読む設計 |
|---|---|---|
| SA-A | DB Foundation、Current Pointer、Job Worker、Runtime State | 02, 03, 09, 12, 14 |
| SA-B | Source Import/Refresh/Purge、Reference Catalog | 01, 02, 09, 12, 13, 14 |
| SA-C | Normalization、Automatic Structure、Basic Metric | 02, 03, 07, 09, 14 |
| SA-D | Boundary、Entity/Term Registry、Speaker/POV/Semantics、Work Analysis | 03, 04, 05, 06, 07, 09, 10, 12, 13, 14 |
| SA-E | Corpus Membership、Aggregate、Profile | 07, 08, 12, 13, 14 |
| SA-F | Manual Identity/Alias、Override、Review、Recompute | 04, 05, 06, 09, 10, 12, 13, 14 |
| SA-G | Project Draft Capture、Style Lint | 02, 07, 08, 11, 12, 13, 14 |
| SA-H | WebUI、E2E、Dogfood | 01, 03, 08, 10, 11, 13, 14 |

SA-A〜Hは既存NovelProduction Phase系列とは別系列。

## 実装上の確定事項

### Storage / Revision

- Project-local `story.db` に `style_` Table群を追加。
- Migrationは006/007/008。001〜005変更禁止。
- Current Text/Current Structureは `style_documents` の明示Pointer。
- ReferenceEpisodeへCurrent Text Pointerを重複保持しない。
- Latest RevisionをCurrentと推測しない。
- Raw/Canonical/Structure Revisionは履歴保持。

### Collection / Job

- Source Adapter/Model Clientは同期API。
- Initial ImportとRefreshは別Job。
- Import状態はJobを正本としImport Rowへ重複保存しない。
- JobはProgress/Result/Warning/PartialをProject DBへ保存。
- API Process全体でWorker Thread 1本。
- Request SQLite ConnectionをWorkerへ渡さない。

### Entity / Term

- Reference Entity/TermはWork単位Stable Registry。
- Mention Extractor/Candidate ExtractorはRegistry非依存。
- MentionはCandidate Type/Canonical Nameを保持しEntity IDを持たない。
- Entity Resolver/Term ResolverはCache不可。
- Resolver RunはRegistry Input Fingerprintを保存。
- Manual Entity/Term/AliasをStyle Analysis内へ直接作成可能。
- Entity/Term誤抽出はEnabled Overrideで除外。
- Term Novelty/Exact Matchは同Run/Termにつき各最大1件。
- Occurrence Indexなし。

### Runtime / Review

- AnalysisRun Dependency Linkを永続化。
- Human DecisionはState Fingerprintへ反映。
- Current Runを単純Latest Succeededで選ばない。
- Resolver Cache不可だがRegistry成長だけで過去Episodeを自動全再解析しない。
- Low-confidence/UnknownをReviewQueueへ全件投入しない。
- Direct OverrideはReviewItem不要。
- Override Operationは `set|clear|revert`。
- Generic二重CAS/必須Reasonを追加しない。

### Corpus / Profile / Lint

- MembershipはWork Default + Episode Override。
- Measurement Row等重み。Work等重みではない。
- `source_measurement_count`, `sample_count`, `work_count`, `skipped_target_count` を別定義。
- Current Document Text/Structure/RunだけをAggregateへ使用。
- Profile IdentityとImmutable Versionを分離。
- New VersionだけではActive Version切替なし。
- Missing MetricはLint Coverage、割合だけでFailさせない。

## Codex実装時の標準運用

Codex向け指示には以下を明記する。

- 提示された設計を承認済み仕様として扱い、brainstorming / planning由来の再承認待ちで停止しない。
- サブエージェント、multi-agent、delegation、parallel agent work禁止。
- model escalation禁止。
- 単一エージェントで順番に作業。
- 別エージェント調査/レビュー禁止。
- 不要な案比較、広範Refactor禁止。
- 開始時Branch/Working Tree確認。
- 既存未Commit差分をReset/Stash/Checkout/Deleteしない。
- Shared Branchなら通常作業Branch、既に適切なら新Branchを重ねない。
- 新規Worktreeは原則作らない。
- Scope外機能追加禁止。
- 必要なTest/Static Checkを実行し、未実施をPASS扱いしない。
- 実装後Commit/PushしChatGPTレビュー可能にする。
- Merge/Force Push/Rebase/Tag/Release/Deployは明示依頼なしで実施しない。

## 設計変更ルール

- 基本設計と矛盾する場合は基本設計も更新する。
- Result互換性が変わるNormalizer/Segmenter/Analyzer/Taxonomy/Prompt/Metric/PolicyはVersionを上げる。
- Codexが独断で大規模再設計しない。
- Unrelated Refactor禁止。
- 既存Authoring Data、ManualOverride、ユーザー未Commit変更を破壊しない。
- 追加Confirmation、追加CAS、追加ReviewQueue、追加Fail条件はCodexが独断で増やさない。

## レビュー前提

```text
ChatGPTでPhase Scope確定
-> Codex実装/Test/Commit/Push
-> ChatGPT GitHub Review
-> 必要なら限定修正
-> CI/Review完了
```
