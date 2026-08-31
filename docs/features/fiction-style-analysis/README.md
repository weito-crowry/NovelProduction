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

- [basic-design.md](basic-design.md): 長期的な責務境界とデータフローを定める基本設計。
- [detailed-design/README.md](detailed-design/README.md): 詳細設計一覧、確定事項、Codex向けSA-A〜SA-H実装順。

## 設計方針

- Raw / Canonical / Structure / Semantic / Measurement / Aggregate / Profileを分離する。
- reference Entity/Termはepisodeを跨ぐwork scopeで扱う。
- Automatic / Semantic / Manual StructureRevisionを分離し、原文を変更せずScene境界を改善する。
- confidence/sample thresholdはversioned AnalysisPolicyへ集約する。
- low-confidence結果を全件ReviewQueueへ送らず、unknownを正常状態として扱う。
- Profileはstable identityとimmutable versionを分離する。
- Lintは参照Profileとの差とcoverageを示し、文章品質の断定や自動修正はしない。

## 実装境界

- CORE: domain、SQLite、normalization、structure、Analyzer、metric、profile、lint
- API: source HTTP adapter、LLM provider adapter、job worker、FastAPI routes
- WEBUI: collection、analysis、review、corpus/profile、lint
- MCP: v1 scope外。既存59 tool contractを維持

## 過剰チェックを避ける

ローカル単一user用途を前提とし、データ破損や誤ったrevision参照を防ぐためのvalidationは維持する。一方、rights_basis必須入力、毎回の同意dialog、Overrideの二重CAS、low-confidence全件Review、missing Metric割合によるLint失敗等は実装しない。

## ステータス

- 基本設計: v0.2 Draft
- 詳細設計: v0.2 自己レビュー第1巡修正版（02のみv0.1維持）
- 実装: 未着手

実装開始時は `detailed-design/README.md` のSA-A〜SA-H分割を基準に、各PhaseごとにChatGPTでscopeを確定してCodexへ指示する。