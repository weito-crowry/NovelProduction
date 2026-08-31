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

- [basic-design.md](basic-design.md): 上位の責務・データフロー・Runtime方針。
- [detailed-design/README.md](detailed-design/README.md): 詳細設計一覧、確定事項、SA-A〜SA-H、Codex実装運用。

## 設計方針

- Source/Revision/Run/Version/Dependencyを追跡可能にする。
- Stable IdentityとRunごとの推論を分離する。
- Reference WorkではEntity/Term RegistryをEpisode横断で管理する。
- Analyzer入力へ影響するHuman DecisionはState Fingerprintで追跡する。
- 再解析で人手修正を破壊しない。
- Unknown/Low-confidenceを正常状態として扱い、Reviewを必須化しない。
- JobはProject-local DBへ永続化し、単一Workerで処理する。
- 実装判断をCodexへ残さないため、DB/API/UI/Testの契約を詳細設計で具体化する。

## 実装境界

- CORE: Domain、SQLite、Normalization、Structure、Analyzer、Metric、Profile、Lint
- API: Source Adapter、Model Adapter、StyleJobWorker、FastAPI Routes
- WEBUI: Collection、Reference Work Analysis、Document Analysis、Corpus/Profile、Override/Review、Lint
- MCP: v1 Scope外。既存59 Tool Contractを維持

## ステータス

- 基本設計: v0.3 Draft
- 詳細設計: v0.3 Self-review反映版
- 実装: 未着手

実装開始時は `detailed-design/README.md` のSA-A〜SA-Hを基準に、ChatGPT側でPhase Scopeを確定してCodex Lunaへ具体的に指示する。
