# Fiction Style Analysis

小説本文の収集・正規化・構造解析・意味抽出・文体計測・文体プロファイル化・自作品評価を扱う開発単位の設計ドキュメント。

## ドキュメント構成

```text
docs/features/fiction-style-analysis/
├─ README.md
├─ basic-design.md
└─ detailed-design/
   ├─ README.md
   ├─ 01-source-ingestion.md
   ├─ 02-normalization.md
   ├─ 03-structure-segmentation.md
   ├─ 04-entity-and-speaker.md
   ├─ 05-term-analysis.md
   ├─ 06-scene-semantics.md
   ├─ 07-style-metrics.md
   ├─ 08-corpus-and-profile.md
   ├─ 09-analysis-runtime.md
   ├─ 10-review-and-overrides.md
   ├─ 11-style-lint.md
   ├─ 12-storage-schema.md
   ├─ 13-api-and-webui.md
   └─ 14-testing-and-evaluation.md
```

- [basic-design.md](basic-design.md): 本機能全体の上位設計。
- [detailed-design/README.md](detailed-design/README.md): 詳細設計一覧、確定事項、SA-A〜SA-H実装順、Codex実装運用。

## 設計方針

- Source/Revision/Run/Versionを追跡可能にする。
- Stable identityと推論結果を分離する。
- 再解析で人手修正を破壊しない。
- Analyzer/Policy/Metricをversion管理する。
- Low-confidenceを正常状態として扱え、全件ReviewQueueへ送らない。
- 安全確認・競合確認・停止条件は必要な箇所だけに置き、通常操作を過剰に阻害しない。
- 実装判断をCodexへ残さないため、詳細設計側でデータ契約・失敗時挙動・API/UI・test条件まで具体化する。

## 実装境界

- CORE: domain、SQLite、Normalization、Structure、Analyzer、Metric、Profile、Lint
- API: Source HTTP Adapter、LLM Provider Adapter、Job Worker、FastAPI routes
- WEBUI: Collection、Analysis、Corpus/Profile、Review/Override、Lint
- MCP: v1 scope外。既存59 tool contractを維持

## ステータス

- 基本設計: v0.2 Draft
- 詳細設計: v0.2 review反映版
- 実装: 未着手

実装開始時は `detailed-design/README.md` のSA-A〜SA-Hを基準に、各PhaseごとにChatGPTでscopeを確定しCodex Lunaへ具体的に指示する。
