# Fiction Style Analysis

小説本文のLocal Import、正規化、構造解析、意味抽出、文体計測、Corpus/Profile化、自作品Lintを扱う開発単位の設計ドキュメント。

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

- [basic-design.md](basic-design.md): 上位責務とv1 Scope。
- [detailed-design/README.md](detailed-design/README.md): 詳細設計一覧、SA-A〜SA-H、Codex実装運用。

## v1の入口

Reference Corpusの入口はユーザーが手元に用意したLocal Fileだけとする。

```text
TXT
HTML file
EPUB
```

Narou/Kakuyomu等のサイト固有Network Downloader、Generic Crawler、Refreshはv1 Scope外。取得方式は別途検討し、将来Phaseで追加する。

## 設計方針

- Source/Revision/Run/Version/Dependencyを追跡可能にする。
- Current Text/StructureはStyleDocumentの明示Pointerで管理する。
- Raw/Canonical/Structure/Semantic/Measurement/Aggregate/Profileを分離する。
- Stable Entity/Term IdentityとRunごとの推論を分離する。
- Reference WorkではEntity/Term RegistryをEpisode横断で管理する。
- Registry自然成長とManual Correctionを区別し、不要な全再解析を避ける。
- Manual Entity/Term/AliasをStyle Analysis内で作成可能にする。
- Human Decisionは必要なAnalyzer/Metric/Aggregate/LintだけへStateとして反映する。
- Unknown/Low-confidenceを正常状態として扱い、Reviewを必須化しない。
- JobはProject-local DBへ永続化し、API Process全体の単一Workerで処理する。
- Work一括解析は子Jobを作らず同Work Job内でEpisode順に実行する。
- Aggregate/Profile/Lintは入力FingerprintとCoverageを持つ。
- 実装判断をCodexへ残さないため、DB/API/UI/Test契約を詳細設計で具体化する。

## 実装境界

- CORE: Domain、SQLite、Normalization、Structure、Analyzer、Metric、Aggregate、Profile、Lint。
- API: Local Source Adapter、Model Adapter、StyleJobWorker、FastAPI Routes。
- WEBUI: Local Sources、Reference Work Analysis、Document Analysis、Corpus/Profile、Override/Review、Lint。
- MCP: v1 Scope外。既存59 Tool Contractを維持。

## Status

- 基本設計: v1.0 Implementation Ready。
- 詳細設計: v1.0 Implementation Ready。
- 実装: 未着手。

実装開始時は `detailed-design/README.md` のSA-A〜SA-Hを基準に、ChatGPT側でPhase Scopeを確定してCodex Lunaへ具体的に指示する。
