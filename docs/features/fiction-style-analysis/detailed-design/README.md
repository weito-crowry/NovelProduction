# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、本機能の詳細設計を領域別に管理する。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | Source Adapter、Import/Refresh/Purge | v0.3 |
| 02 | [02-normalization.md](02-normalization.md) | Raw/Canonical Text、TextMapping、Offset | v0.1 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | Automatic/Semantic/Manual Structure | v0.2 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Mention、Work Entity Registry、Speaker | v0.3 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | Term Candidate/Registry、初出、説明 | v0.3 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene/Block Semantic、POV、Boundary | v0.3 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | Basic/Semantic Metric、Measurement | v0.3 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Corpus、Aggregate、Profile Version | v0.2 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | DAG、State、Work Job、Single Worker | v0.3 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | Effective View、Set/Clear/Revert | v0.3 |
| 11 | [11-style-lint.md](11-style-lint.md) | Finding、Evidence、Coverage | v0.1 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite、006〜008、Job/Run Provenance | v0.3 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | API、Revision、Work Analysis、React UI | v0.3 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | Unit/Integration/CI/Dogfood | v0.3 |

## Codex向け実装順

| Phase | 実装Scope | 主に読む設計 |
|---|---|---|
| SA-A | DB Foundation、Repositories、Job Worker、AnalysisPolicy/State | 02, 03, 09, 12, 14 |
| SA-B | Source Import/Refresh/Purge、Reference Work/Episode | 01, 02, 09, 12, 13, 14 |
| SA-C | Normalization、Automatic Structure、Basic Metric | 02, 03, 07, 09, 14 |
| SA-D | Boundary、Entity/Term Registry、Speaker/POV/Semantics、Work一括解析 | 03, 04, 05, 06, 07, 09, 10, 12, 14 |
| SA-E | Corpus、Aggregate、Profile Identity/Version | 07, 08, 12, 13, 14 |
| SA-F | Effective View、Direct Override、Review、Recompute | 04, 05, 06, 09, 10, 12, 13, 14 |
| SA-G | Project Draft Capture、Style Lint | 07, 08, 11, 12, 13, 14 |
| SA-H | WebUI、E2E、Dogfood | 01, 03, 08, 10, 11, 13, 14 |

SA-A〜Hは既存NovelProduction Phase系列とは別系列。

## 実装上の確定事項

### Architecture / Storage

- Style AnalysisはProject-local `story.db` の `style_` Table群として実装。
- 既存Migration 001〜005は変更しない。
- 新Migrationは006/007/008の3本。
- ORM、Redis、Celery、WebSocket/SSEを追加しない。
- v1でMCP Toolを追加せずTool Count 59を維持。

### Collection / Job

- Source AdapterとModel Clientは単一同期Workerに合わせ同期API。
- SourceSnapshotは元BytesをBLOB保持。
- Initial ImportとRefreshは別Job。
- ReferenceEpisodeはCurrent TextRevision Pointerを持つ。
- Reference Work一括解析はServer側1 JobでEpisode Order順に実行。
- JobはProgress/Result/Warningと `partial` StatusをDB保存。
- API Process全体でWorker Thread 1本。Projectごとに増やさない。
- WorkerはRequest-bound SQLite Connectionを使わず自身でOpen/Close。

### Structure

- Raw/Canonical分離、TextRevision Immutable。
- OffsetはUnicode Code Point半開区間。
- Structure Kindは `automatic | semantic | manual`。
- Block OrderはStructureRevision全体でGlobal。
- Boundary Modelは `after_block_id` だけを返す。
- Semantic Structureは生成元Boundary Runを追跡。

### Entity / Term

- Reference Entity/TermはWork単位Stable Registry。
- Mention ExtractorはEntity Registry非依存。Mention RowにEntity IDを持たない。
- Entity ResolverはResolution Annotationを作りCache不可。
- Term Candidate ExtractorはTerm/Entity Registry非依存。CandidateはAnnotation。
- Term ResolverはIdentity/TermMentionを作りCache不可。
- Resolver RunはRegistry Input Fingerprintを保存。
- Registry成長だけで過去Episodeを自動全再解析しない。Work再解析時にOrder順で再Resolver。
- Entity/Term誤抽出は `enabled=false` Overrideで除外可能。
- Term Novelty/ExactMatch/ExplanationはRun付きAnnotation。
- Occurrence Indexを保存しない。

### Runtime / Review

- Confidence/Sample Threshold正本はVersioned AnalysisPolicy。
- AnalysisRun DependencyはLink TableでPersist。
- Human Decisionが入力へ影響するAnalyzerはState FingerprintでCurrent/Staleを判定。
- Current Runは単純Latest Succeededで選ばない。
- Basic MetricはSemantic State非依存。
- Low-confidence/UnknownをReviewQueueへ全件投入しない。
- Direct OverrideはReviewItemなしで可能。
- ManualOverride Operationは `set | clear | revert`。
- ClearとRevertを混同しない。
- Generic二重CASや必須Reasonを追加しない。

### Profile / Lint

- StyleProfile IdentityとStyleProfileVersionを分離。
- Active Versionを明示し、新Version作成だけで自動切替しない。
- LintはProfile Versionを明示。
- Missing MetricはCoverageとして扱い、割合だけでFailさせない。
- 総合文章品質Score/自動書き換えはv1 Scope外。

## Codex実装時の標準運用

Codex向け指示には以下を標準で明記する。

- 提示された設計を承認済み仕様として扱い、brainstorming / planning由来の再承認待ちで停止しない。
- サブエージェント、multi-agent、delegation、parallel agent work禁止。
- model escalation禁止。
- 単一エージェントとして順番に作業。
- 別エージェントによる調査/レビュー禁止。
- 不要な案比較、広範なRefactor禁止。
- 開始時にBranch/Working Tree確認。
- 既存未Commit差分をReset/Stash/Checkout/Deleteしない。
- Shared Branchなら通常の作業Branchを作り、既に適切なBranchなら重ねて作らない。
- 新規Worktreeは原則作らない。
- Scope外機能追加禁止。
- 必要なTest/Static Checkを実行し、未実施をPASS扱いしない。
- 実装後Commit/PushしChatGPTレビュー可能にする。
- Merge/Force Push/公開履歴書換え/Tag/Release/Deployは明示依頼なしでは実施しない。

## 設計変更ルール

- 基本設計と矛盾する場合は基本設計も更新する。
- Result互換性が変わるNormalizer/Segmenter/Analyzer/Taxonomy/Prompt/Metric/PolicyはVersionを上げる。
- Codexが独断で大規模再設計しない。
- Unrelated Refactorをしない。
- 既存Authoring Data、ManualOverride、ユーザー未Commit変更を破壊しない。
- 「安全のため」だけを理由に追加Confirmation、追加CAS、追加ReviewQueue、追加Fail条件を増やさない。必要なら設計変更としてChatGPT側で判断する。

## レビュー前提

```text
ChatGPTでPhase Scope確定
-> Codexへ具体的実装指示
-> Codexが実装/Test/Commit/Push
-> ChatGPTがGitHub差分Review
-> 必要なら限定修正
-> CI/Review完了
```

Codex実装完了を最終完了とは扱わない。
