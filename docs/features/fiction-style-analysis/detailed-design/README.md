# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、本機能の詳細設計を領域別に管理する。

## 詳細設計一覧

| # | ファイル | 対象 | 状態 |
|---:|---|---|---|
| 01 | [01-source-ingestion.md](01-source-ingestion.md) | なろう・カクヨム・TXT・EPUB・HTML、Source Adapter、Snapshot | v0.1 |
| 02 | [02-normalization.md](02-normalization.md) | Raw/Canonical Text、TextMapping、offset | v0.1 |
| 03 | [03-structure-segmentation.md](03-structure-segmentation.md) | Scene/Block/Sentence、StructureRevision | v0.1 |
| 04 | [04-entity-and-speaker.md](04-entity-and-speaker.md) | Entity/Mention、人物統合、話者推定 | v0.1 |
| 05 | [05-term-analysis.md](05-term-analysis.md) | 用語、初出、説明、説明遅延 | v0.1 |
| 06 | [06-scene-semantics.md](06-scene-semantics.md) | Scene taxonomy、POV、Block semantic | v0.1 |
| 07 | [07-style-metrics.md](07-style-metrics.md) | MetricDefinition、Measurement、算出式 | v0.1 |
| 08 | [08-corpus-and-profile.md](08-corpus-and-profile.md) | Aggregate、Corpus、StyleProfile、StyleRule | v0.1 |
| 09 | [09-analysis-runtime.md](09-analysis-runtime.md) | Analyzer DAG、job、fingerprint、LLM provider境界 | v0.1 |
| 10 | [10-review-and-overrides.md](10-review-and-overrides.md) | Confidence、ReviewQueue、ManualOverride | v0.1 |
| 11 | [11-style-lint.md](11-style-lint.md) | 自作品比較、Finding、Evidence、severity | v0.1 |
| 12 | [12-storage-schema.md](12-storage-schema.md) | SQLite schema、006〜008 migrations、index/FK | v0.1 |
| 13 | [13-api-and-webui.md](13-api-and-webui.md) | FastAPI契約、React UI、query invalidation | v0.1 |
| 14 | [14-testing-and-evaluation.md](14-testing-and-evaluation.md) | fixture、gold dataset、CI、dogfood | v0.1 |

ファイル番号は読解順であり、実装Phaseと一対一ではない。

## Codex向け実装順

実装時は以下の順序を標準とする。ChatGPT側で各Phaseのscopeを切ってCodexへ渡し、Codexに全体再設計をさせない。

| Phase | 実装scope | 主に読む設計 |
|---|---|---|
| SA-A | DB foundation、models/repositories、job基盤 | 02, 03, 09, 12, 14 |
| SA-B | Source import、Reference Work/Episode | 01, 02, 12, 13, 14 |
| SA-C | Normalization、Structure、deterministic metrics | 02, 03, 07, 09, 14 |
| SA-D | SemanticModelClient、Entity/Speaker/Term/Scene semantics | 04, 05, 06, 09, 10, 14 |
| SA-E | Corpus、Aggregate、StyleProfile | 07, 08, 12, 13, 14 |
| SA-F | Review/Override、再計算 | 09, 10, 12, 13, 14 |
| SA-G | Project draft capture、Style Lint | 07, 08, 11, 13, 14 |
| SA-H | WebUI integration、E2E、dogfood | 01, 10, 11, 13, 14 |

SA-A〜Hは実装管理用の推奨分割であり、既存NovelProduction Phase A〜Eとは別系列とする。

## 実装上の確定事項

以下はCodexが再判断しない。

- Style Analysisは既存projectの `story.db` 内に `style_` prefix tableとして実装する。
- 既存migration `001`〜`005` は変更しない。
- 新migrationは `006_style_analysis_foundation.sql`、`007_style_analysis_semantics.sql`、`008_style_analysis_analytics.sql`。
- COREはnetwork/LLM provider非依存。外部HTTP通信はAPI側。
- ORM、Redis、Celery、WebSocket/SSEは追加しない。
- Analyzerはversion/fingerprint付きDAG。
- semantic推論はManualOverrideを上書きしない。
- 自動Scene構造は保守的・決定論的。曖昧な境界はReview候補。
- v1ではMCP toolを追加せず、既存tool count 59を維持する。
- 外部作品本文はMCPへ露出しない。
- CIでは実サイト・実LLM providerへ接続しない。

## 詳細設計の変更ルール

- `basic-design.md` と矛盾する変更は、まず基本設計を更新する。
- 計算式・taxonomy・prompt・normalizer等、結果互換性が変わる変更は必ずversionを上げる。
- 実装中に設計不足が判明しても、Codexが独断で大規模設計変更しない。作業を止める必要がない軽微な実装詳細は既存パターンに合わせ、設計判断が必要な事項は最終報告へ明示してChatGPT側レビューへ戻す。
- unrelated refactorは行わない。
- 人手修正、既存未commit変更、既存authoringデータを破壊しない。

## レビュー前提

Codex実装完了は最終完了ではない。

```text
ChatGPTでPhase scope確定
→ Codexへ詳細な実装指示
→ Codexが実装・テスト・commit・push
→ ChatGPTがGitHub差分レビュー
→ 必要ならCodexへ限定修正
→ CI/レビュー完了
```
