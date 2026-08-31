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

- [basic-design.md](basic-design.md): アーキテクチャ、責務分離、データモデル、パイプラインを定める基本設計。
- [detailed-design/README.md](detailed-design/README.md): 詳細設計14文書の索引、確定事項、Codex向け推奨実装順。

## 設計方針

基本設計を上位仕様とし、詳細設計はその責務境界・データレイヤー・再解析可能性を具体化する。

分析器、分類体系、Metric、LLM promptなど結果互換性に影響する要素にはversionを持たせる。Raw inferenceとHuman Overrideを分離し、再解析で人手修正を破壊しない。

外部作品の収集はユーザーが明示指定したローカル・私的分析用途を前提とし、汎用crawlerやアクセス制限回避を実装しない。

## 実装境界

- CORE: domain、SQLite、normalization、structure、Analyzer、metric、profile、lint
- API: source HTTP adapter、LLM provider adapter、job worker、FastAPI routes
- WEBUI: collection、analysis、review、corpus/profile、lint
- MCP: v1 scope外。既存59 tool contractを維持

## ステータス

- 基本設計: v0.1 Draft
- 詳細設計: v0.1 一式作成済み
- 実装: 未着手

実装開始時は `detailed-design/README.md` の SA-A〜SA-H 分割を基準に、各PhaseごとにChatGPTでscopeを確定してCodexへ指示する。
