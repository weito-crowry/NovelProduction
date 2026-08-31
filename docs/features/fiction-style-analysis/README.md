# Fiction Style Analysis

小説本文のLocal取込・正規化・構造解析・Semantic抽出・文体計測・Corpus/Profile化・自作品Lintを扱う開発単位の設計ドキュメント。

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
   ├─ 14-testing-and-evaluation.md
   └─ 15-semantic-model-contracts.md
```

- [basic-design.md](basic-design.md): v1 Scope、上位責務、Current Revision、Registry、Runtime、Corpus/Profile/Lintの基本設計。
- [detailed-design/README.md](detailed-design/README.md): 詳細設計一覧、SA-A〜SA-H実装順、Codex実装運用。

## v1入口

Reference Corpusの入口はユーザーが手元に用意した:

```text
TXT
HTML file
EPUB
```

だけ。Local同期Importとする。

Narou/Kakuyomu等のSite-specific Downloader、Generic Crawler、Remote URL Import、Refreshはv1対象外。取得方式は別途検討し将来Phaseで設計する。

## 設計方針

- Source/Revision/Run/Version/Dependencyを追跡可能にする。
- Current Text/StructureはStyleDocumentの明示Pointer。
- Stable Entity/Term IdentityとRun推論を分離する。
- Reference WorkではEntity/Term RegistryをEpisode横断管理する。
- Manual Entity/Term/AliasをStyle Analysis内に作成可能。
- Relevant Human DecisionだけState Fingerprintへ反映する。
- Unknown/Low-confidenceを正常状態として扱いReviewを必須化しない。
- Persisted Jobは単一Workerで処理する。
- Model Prompt/JSON/Provider契約は15を正本とする。
- 実装判断をCodexへ残さないためDB/API/UI/Test/Model Contractを詳細設計で固定する。

## 実装境界

- CORE: Domain、SQLite、Normalization、Structure、Analyzer、Metric、Profile、Lint、Prompt/Response Contract
- API: Local Source Adapter、OpenAI-compatible Model Adapter、StyleJobWorker、FastAPI Routes
- WEBUI: Sources、Reference Work、Document Analysis、Corpus/Profile、Override/Review、Lint
- MCP: v1 Scope外。既存59 Tool Contract維持

## ステータス

- 基本設計: v1.0 Implementation Ready
- 詳細設計: v1.0 Implementation Ready
- 実装: 未着手

実装開始時は `detailed-design/README.md` のSA-A〜SA-Hを基準に、ChatGPT側で現在Phase Scopeを確定してCodex Lunaへ具体的に指示する。
