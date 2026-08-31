# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、詳細設計を領域別に管理する。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | Local TXT/HTML/EPUB Import、SourceSnapshot、Purge | v1.0 |
| 02 | [02-normalization.md](02-normalization.md) | Current Text、Normalization、Mapping、Project Capture | v1.0 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | Current Structure、Automatic/Semantic/Manual | v1.0 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Mention、Entity Registry、Speaker、Character Link | v1.0 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | Term Registry、初出、同Scene説明 | v1.0 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene Multi-axis、POV、Block Primary、Boundary | v1.0 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | Basic/Semantic Metric | v1.0 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Membership、Aggregate、Profile Version/Rule | v1.0 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | Current Run、DAG、Work Job、Single Worker | v1.0 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | Effective View、Override、Review、Analysis Status | v1.0 |
| 11 | [11-style-lint.md](11-style-lint.md) | Rule適用、Finding、Evidence、Coverage | v1.0 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite 006〜008、FK/Constraint/Index | v1.0 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | FastAPI、Job、WebUI | v1.0 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | Unit/Integration/API/E2E/Dogfood | v1.0 |

## v1 Scope固定

### 実装する

- Local TXT/HTML/EPUB同期Import。
- SourceSnapshot/Reference Work/Episode。
- TextRevision/Mapping。
- Automatic/Semantic/Manual Structure。
- Entity/Mention/Speaker。
- Term/初出/同Scene説明。
- Scene/POV/Block Semantic。
- Basic/Semantic Metric。
- Work一括解析。
- Corpus/Aggregate/Profile。
- Manual Correction/Review。
- Project Draft Capture/Lint。
- WebUI。

### 実装しない

- Narou/Kakuyomu等のNetwork Downloader。
- Remote URL Import/Refresh/Generic Crawler。
- Profile Import/Export。
- Entity Relation専用Analyzer。
- Term↔Entity Link。
- Scene×Character Metric。
- 総合品質Score/自動本文修正。
- MCP Tool追加。

取得方式は別Phaseで再検討する。

## Codex向け実装順

| Phase | Scope | 主に読む設計 |
|---|---|---|
| SA-A | DB Foundation、Current Pointer、Job Worker、Runtime State | 02, 03, 09, 10, 12, 14 |
| SA-B | Local Source Import、Reference Catalog、Purge | 01, 02, 12, 13, 14 |
| SA-C | Normalization、Automatic Structure、Basic Metric | 02, 03, 07, 09, 12, 14 |
| SA-D | Boundary、Entity/Term Registry、Speaker/POV/Semantics、Work Analysis | 03, 04, 05, 06, 07, 09, 10, 12, 13, 14 |
| SA-E | Corpus Membership、Aggregate、Profile | 07, 08, 09, 12, 13, 14 |
| SA-F | Manual Identity/Alias、Override、Review、Recompute | 04, 05, 06, 09, 10, 12, 13, 14 |
| SA-G | Project Draft Capture、Style Lint | 02, 07, 08, 10, 11, 12, 13, 14 |
| SA-H | WebUI、E2E、Dogfood | 01, 03, 08, 10, 11, 13, 14 |

SA-A〜Hは既存NovelProduction Phase系列とは別系列。

## 実装上の確定事項

### Storage / Revision

- Project-local `story.db` に `style_` Table群を追加。
- Migrationは006/007/008。001〜005変更禁止。
- 既存`works/episodes/drafts/characters`を必要箇所だけ参照し、Authoring Schemaを変更しない。
- Current Text/Current Structureは`style_documents`の明示Pointer。
- ReferenceEpisodeへCurrent Text Pointerを重複保持しない。
- Latest RevisionをCurrentと推測しない。
- TextRevision Reuseは`normalization_input_fingerprint`。
- StructureRevision Reuseはfingerprint。

### Source

- v1はLocal TXT/HTML/EPUBのみ。
- Local Importは同期処理、Jobなし。
- Source IdentityはUpload Bytes SHA-256。
- `style_imports` Tableは作らない。
- Network Source用Job/Column/UIを追加しない。

### Structure

- Block Typeは`dialogue|narration|heading|separator|unknown`。
- `monologue`は作らずNarration + psychology。
- LLM BoundaryはExisting Block境界だけ。
- Raw Candidateは全Valid保存、Candidate Minは表示だけ。
- Current Manual/Semanticは通常Fullで保持。
- Current AutomaticだけFullでSemantic昇格可能。
- 明示`rebuild_structure=true`でAutomaticから再生成。

### Entity / Term

- Reference Entity/TermはWork単位Stable Registry。
- Mention/Candidate ExtractorはRegistry非依存。
- MentionはCandidate Type/Canonical Nameを保持しEntity IDを持たない。
- Entity/Term ResolverはCache不可。
- Resolver Runは実行時Registry Input FingerprintをProvenance保存するが、Registry自然成長だけで過去Runを自動Stale化しない。
- Manual Registry変更はState FingerprintでStale化。
- Manual Entity/Term/AliasをStyle Analysis内へ直接作成可能。
- Occurrence Indexなし。
- Term ExplanationはTermMention単位、同Sceneだけ。
- Project CharacterはManual Linkだけ。

### Runtime / Job

- AnalysisRun Dependency Linkを永続化。
- Policy Version丸ごとではなくAnalyzerが読むPolicy KeyだけCurrent条件。
- Current Runを単純Latest Succeededで選ばない。
- Job Typeは`analyze_document|analyze_reference_work|recompute_aggregate|run_lint`の4種。
- API Process全体でWorker Thread 1本。
- Work Jobは子Document Jobを作らず同Job内でEpisode順にinline実行。
- Request SQLite ConnectionをWorkerへ渡さない。
- `metrics` presetは内部Correction専用。

### Review / Status

- Effective順位はManual > Confirmed > Current Eligible Inference > Unknown/Default。
- ManualOverrideはAppend-only `set|clear|revert`。
- Low-confidence/UnknownをReviewQueueへ全件投入しない。
- Direct OverrideはReviewItem不要。
- Generic二重CAS/必須Reasonを追加しない。
- Analysis StatusはBasic/Semantic別の派生値。永続`analysis_stale` boolなし。

### Corpus / Profile / Lint

- MembershipはWork Default + Episode Override。
- Measurement Row等重み。Work等重みではない。
- `source_measurement_count`, `sample_count`, `work_count`, `skipped_target_count`を別定義。
- Current Document Text/Structure/RunだけをAggregateへ使用。
- AggregateはImmutable、AggregatePolicy + Input FingerprintでStale判定。
- Profile IdentityとImmutable Versionを分離。
- Corpus RuleはExact median/p25/p75 Aggregate IDsをProvenance保存。
- Enabled Ruleはmin/max両方必須。
- New VersionだけではActive Version切替なし。
- Missing Metric/SelectorはLint Coverage、割合だけでFailさせない。

## Codex実装時の標準運用

Codex向け指示には原則として以下を明記する。

- **提示された設計を承認済み仕様として扱い、brainstorming / planning由来の再承認待ちで停止しない。**
- ChatGPTが設計・レビューを担当し、Codexは既存コード確認、指定実装、テスト、静的検査、限定修正を担当する。
- サブエージェント禁止。
- multi-agent / delegation / parallel agent work禁止。
- model escalation禁止。
- Codex自身が単一エージェントとして順番に作業する。
- 別エージェントによる調査・レビュー禁止。
- 重複調査、過剰探索、不要な案比較、広範Refactor禁止。
- 開始時にCurrent Branch/Working Treeを確認する。
- Dirtyであることだけを理由にWorktreeを作らない。
- 新規Worktreeは原則作らない。
- Shared main等なら通常作業Branchを作る。既に適切なBranchなら新Branchを重ねない。
- ユーザー既存未Commit差分をReset/Stash/Checkout/Deleteしない。
- Scope外機能追加禁止。
- 「ついでの改善」は実装せず最終報告の提案に留める。
- 必要なTest/Static Checkを実行し、未実施をPASS扱いしない。
- 実装後Commit/PushしChatGPTがGitHub上でReview可能にする。
- Merge/Force Push/公開履歴を書き換えるRebase/Tag/Release/Deployは明示依頼なしで実施しない。

## 設計変更ルール

- 基本設計と詳細設計が矛盾する場合、実装前にChatGPT側で解消する。
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
-> 追加Commit/Push
-> CI/Review完了
-> 必要時のみMerge
```
