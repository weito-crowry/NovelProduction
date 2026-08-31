# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、本機能の詳細設計を領域別に管理する。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | なろう・カクヨム・TXT・EPUB・HTML、Source Adapter、Snapshot | v0.2 |
| 02 | [02-normalization.md](02-normalization.md) | Raw/Canonical Text、TextMapping、offset | v0.1 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | automatic/semantic/manual Scene、Block、Sentence | v0.2 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Entity/Mention、作品跨ぎ人物統合、話者推定 | v0.2 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | 用語、作品跨ぎTerm、初出、説明遅延 | v0.2 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene taxonomy、POV、Block semantic、Scene境界 | v0.2 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | basic/semantic Metric、Measurement、算出式 | v0.2 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Aggregate、Corpus、Profile identity/version、Rule | v0.2 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | Document Analyzer DAG、AnalysisPolicy、job、LLM境界 | v0.2 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | ReviewItem、ManualOverride、Effective View | v0.2 |
| 11 | [11-style-lint.md](11-style-lint.md) | Finding、Evidence、coverage、severity | v0.2 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite schema、006〜008 migration、index/FK | v0.2 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | FastAPI契約、React UI、job/query | v0.2 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | fixture、evaluation、CI、dogfood | v0.2 |

ファイル番号は読解順であり、実装Phaseと一対一ではない。

## Codex向け実装順

| Phase | 実装scope | 主に読む設計 |
|---|---|---|
| SA-A | DB foundation、models/repositories、job/AnalysisPolicy基盤 | 02, 03, 09, 12, 14 |
| SA-B | Source import、Reference Work/Episode | 01, 02, 12, 13, 14 |
| SA-C | Normalization、automatic Structure、basic metrics | 02, 03, 07, 09, 14 |
| SA-D | SemanticModelClient、Scene boundary、Entity/Speaker/Term/Semantics | 03, 04, 05, 06, 09, 10, 14 |
| SA-E | Corpus、Aggregate、Profile identity/version | 07, 08, 12, 13, 14 |
| SA-F | Review/Override、再計算 | 09, 10, 12, 13, 14 |
| SA-G | Project draft capture、Style Lint | 07, 08, 11, 13, 14 |
| SA-H | WebUI integration、E2E、dogfood | 01, 03, 10, 11, 13, 14 |

SA-A〜Hは既存NovelProduction Phase A〜Eとは別系列。

## 実装上の確定事項

Codexは以下を再設計しない。

- Style Analysisはproject-local `story.db` に `style_` prefix tableとして実装する。
- 既存migration001〜005は変更しない。
- 新migrationは006/007/008の3本。
- Source raw payloadはBLOB、Canonical/Raw textはTEXT。
- COREはnetwork/LLM provider非依存。外部HTTPはAPI側。
- ORM、Redis、Celery、WebSocket/SSEは追加しない。
- Normalization/Structure作成、Document Analyzer、Aggregate/Profile/Lintのruntime責務を分離する。
- Analyzer confidence/sample thresholdは09 `AnalysisPolicy` を正本にし、各Analyzerへ重複hard-codeしない。
- automatic Structureは決定論的base。Full analysisでは高confidence Scene boundaryを新semantic StructureRevisionへ自動materializeする。
- manual/semantic StructureRevisionはparentを変更せず新revisionとして作る。
- reference Entity/Termはreference work scopeでepisodeを跨いで統合する。
- Profileはstable identityとimmutable ProfileVersionを分離する。
- low-confidence結果をすべてReviewQueueへ自動投入しない。
- ManualOverrideは再解析で消さない。
- v1ではMCP toolを追加せずtool count 59維持。
- CIでは実サイト/実LLM providerへ接続しない。
- 取得時のrights_basis必須入力や毎回の同意checkboxは設けない。

## 過剰チェックを避ける方針

本機能はローカル単一ユーザー用途を前提とするため、安全性・整合性のためのチェックは「壊れるとデータを誤るもの」へ限定する。

維持する代表例:

- revision/span/FK/JSON等のデータ不変条件
- source host allowlistとログイン/有料壁回避禁止
- ReviewItemの既存VERSION_CONFLICT再利用
- API keyをDBへ保存しない

追加しない代表例:

- rights basisの法的判定・同意record
- Overrideごとの二重CAS token
- low-confidence全件ReviewItem
- missing metric割合によるLint失敗
- 小規模gold datasetへの硬い精度gate
- 各テスト層への同一integrity assertion重複

## 詳細設計の変更ルール

- `basic-design.md` と矛盾する変更は基本設計も更新する。
- 結果互換性が変わるnormalizer/segmenter/taxonomy/prompt/Metric/AnalysisPolicyはversionを上げる。
- Codexは提示設計を承認済み仕様として扱い、brainstorming/planning由来の再承認待ちで停止しない。
- 実装中に不足が判明した場合、軽微な実装詳細は既存パターンへ合わせる。新しいdomain判断が必要ならscopeを広げず最終報告へ記載する。
- unrelated refactor禁止。
- 既存未commit変更をreset/stash/checkoutで消さない。

## レビュー前提

```text
ChatGPTでPhase scope確定
-> Codexへ詳細指示
-> Codexが単一agentで実装/テスト
-> commit/push
-> ChatGPTがGitHubレビュー
-> 必要なら限定修正
-> CI/レビュー完了
```

Codex側のサブエージェント、multi-agent/delegation、model escalation、別agent reviewは使用しない。