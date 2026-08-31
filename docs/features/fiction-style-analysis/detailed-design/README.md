# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、本機能の詳細設計を領域別に管理する。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | なろう・カクヨム・TXT・EPUB・HTML、Source Adapter、Snapshot | v0.2 |
| 02 | [02-normalization.md](02-normalization.md) | Raw/Canonical Text、TextMapping、offset | v0.1 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | Automatic/Semantic/Manual Structure、Scene/Block/Sentence | v0.2 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Entity/Mention、人物統合、話者推定 | v0.2 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | Term identity、novelty、初出、説明、説明遅延 | v0.2 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene taxonomy、POV、Block semantic、Boundary | v0.2 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | Basic/Semantic Metric、Measurement、算出式 | v0.2 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Aggregate、Corpus、Profile identity/Version/Rule | v0.2 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | Analyzer DAG、AnalysisPolicy、Job、Effective Run | v0.2 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | Effective View、Direct Override、ReviewQueue | v0.2 |
| 11 | [11-style-lint.md](11-style-lint.md) | Project比較、Finding、Evidence、coverage | v0.1 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite schema、006〜008 migration、Purge | v0.2 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | FastAPI契約、Revision選択、React UI | v0.2 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | Fixture、Gold、CI、Dogfood | v0.2 |

ファイル番号は読解順であり、実装Phaseと一対一ではない。

## Codex向け実装順

実装時は以下の順序を標準とする。ChatGPT側で各Phaseのscopeを切り、Codexに全体再設計をさせない。

| Phase | 実装scope | 主に読む設計 |
|---|---|---|
| SA-A | DB foundation、Models/Repositories、Job基盤、AnalysisPolicy | 02, 03, 09, 12, 14 |
| SA-B | Source Import、Reference Work/Episode、Refresh/Purge | 01, 02, 12, 13, 14 |
| SA-C | Normalization、Automatic Structure、Basic Metric | 02, 03, 07, 09, 14 |
| SA-D | SemanticModelClient、Boundary、Entity/Speaker/Term/Scene Semantics | 03, 04, 05, 06, 09, 10, 14 |
| SA-E | Corpus、Aggregate、StyleProfile identity/Version | 07, 08, 12, 13, 14 |
| SA-F | Effective View、Direct Override、Review、再計算 | 04, 05, 09, 10, 12, 13, 14 |
| SA-G | Project Draft Capture、Style Lint | 07, 08, 11, 12, 13, 14 |
| SA-H | WebUI Integration、E2E、Dogfood | 01, 03, 08, 10, 11, 13, 14 |

SA-A〜Hは既存NovelProduction Phase A〜Eとは別系列。

## 実装上の確定事項

以下はCodexが再判断しない。

### Storage / Architecture

- Style Analysisは既存Projectの `story.db` 内に `style_` prefix tableとして実装する。
- 既存migration `001`〜`005` は変更しない。
- 新migrationは `006_style_analysis_foundation.sql`、`007_style_analysis_semantics.sql`、`008_style_analysis_analytics.sql`。
- ORM、Redis、Celery、WebSocket/SSEは追加しない。
- COREはNetwork/LLM Provider非依存。外部HTTPはAPI側。
- v1ではMCP toolを追加せずtool count 59を維持する。

### Text / Structure

- SourceSnapshotは元resource bytesをBLOB保持する。
- Raw/Canonical Textを分離しTextRevisionはimmutable。
- OffsetはUnicode code point `[start_cp,end_cp)`。
- StructureRevisionは `automatic | semantic | manual`。
- Block orderはStructureRevision全体でglobal 1..N。
- Scene Boundary LLMは任意offsetを返さず `after_block_id` だけ返す。
- threshold以上のBoundaryはSemantic Structureへ自動materialize可能。
- Semantic Structureは生成元Boundary AnalysisRunを追跡する。

### Semantic data

- Reference作品のEntity/TermはReference Work単位でepisode横断共有する。
- Entity/Term rowはstable identity。再解析で推論属性を上書きしない。
- Term `novelty` / `exact_match_safe` / explanationはRun付きAnnotation。
- TermMentionに `occurrence_index` を保存しない。
- Existing Character/World/Canonへ推論を自動writeしない。

### Runtime / Review

- Confidence/sample thresholdの正本はversioned `AnalysisPolicy`。
- AnalysisRunはDocument Analyzerだけを管理する。
- Basic MetricはLLM Providerなしで動作する。
- Partial Analyzer outputは成功subjectを保持できる。
- Low-confidence/unknownを全件ReviewQueueへ送らない。
- ManualOverrideはReviewItemなしで直接作成可能。
- Direct Overrideへ不要な二重CAS/必須reasonを追加しない。

### Profile / Lint

- StyleProfile stable identityとStyleProfileVersionを分離する。
- Active Profileは `active_version_id` を明示する。
- New Version作成だけではactive Versionを切替えない。
- LintはProfile Versionを明示指定する。
- Missing Metricの割合だけでLintをfailさせずcoverageを返す。
- 総合文章品質scoreや自動書き換えはv1 scope外。

### Source/UI safety balance

- Source Importに `rights_basis` 必須fieldを追加しない。
- 毎回の同意checkbox/確認dialogを追加しない。
- ログイン/CAPTCHA/有料壁回避、汎用crawlerは実装しない。
- Purgeは通常の削除確認1回でよい。
- CIは実サイト/実LLM Providerへ接続しない。

## Codex実装時の標準運用

ChatGPT側ですでに設計済みのため、Codex向け指示では次を明記する。

- 提示された設計を承認済み仕様として扱い、brainstorming/planning由来の再承認待ちで停止しない。
- サブエージェント禁止。
- multi-agent / delegation / parallel agent work禁止。
- model escalation禁止。
- Codex自身が単一エージェントとして順番に作業する。
- 別エージェントによる調査・レビュー禁止。
- 不要な実装案比較、広範なrefactor禁止。
- 現在branch/working treeを開始時に確認する。
- 既存未commit変更をreset/stash/checkout/deleteしない。
- main/shared branchなら通常の作業branchを作る。既に適切な作業branchなら重ねて作らない。
- 新規worktreeは原則作らない。
- 対応Phaseのscope外機能を追加しない。
- 必要なtest/static checkを実行し、未実施をPASS扱いしない。
- 実装後commit/pushし、ChatGPTがGitHub上でレビュー可能な状態にする。
- merge/force push/rebase/tag/release/deployは明示依頼なしでは行わない。

## 詳細設計の変更ルール

- `basic-design.md` と矛盾する変更は基本設計も同時更新する。
- 結果互換性が変わるNormalizer/Segmenter/Analyzer/Taxonomy/Prompt/Metric/Policyはversionを上げる。
- 実装中に設計不足が判明した場合、Codexが大規模再設計しない。軽微な既存pattern適用で解決できない事項は最終報告へ明示しChatGPTレビューへ戻す。
- unrelated refactorをしない。
- 既存Authoringデータ・ManualOverride・ユーザー未commit変更を破壊しない。
- 「安全のため」だけを理由に追加confirmation、追加CAS、追加ReviewQueue、追加fail-closed条件を増やさない。必要性がある場合は設計変更としてChatGPT側で判断する。

## レビュー前提

```text
ChatGPTでPhase scope確定
-> Codexへ具体的実装指示
-> Codexが実装・test・commit・push
-> ChatGPTがGitHub差分レビュー
-> 必要なら限定修正
-> CI/レビュー完了
```

Codex実装完了を最終完了とは扱わない。
