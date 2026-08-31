# Fiction Style Analysis 詳細設計

`../basic-design.md` を上位仕様として、本機能の詳細設計を領域別に管理します。

## 予定ドキュメント

| ファイル | 対象 |
|---|---|
| `01-source-ingestion.md` | なろう・カクヨム・TXT・EPUB・HTML等の収集、Source Adapter、Snapshot管理 |
| `02-normalization.md` | Raw/Canonical Text、正規化規則、TextMapping、offset仕様 |
| `03-structure-segmentation.md` | Episode/Scene/Block/Sentence、Scene境界、構造解析 |
| `04-entity-and-speaker.md` | Entity/Mention、人物抽出、coreference、話者推定、関係抽出 |
| `05-term-analysis.md` | 用語抽出、初出、新規性、説明タイミング |
| `06-scene-semantics.md` | Scene taxonomy、POV、semantic block分類、multi-label判定 |
| `07-style-metrics.md` | Measurement、MetricDefinition、文体指標、統計定義 |
| `08-corpus-and-profile.md` | Aggregate、Corpus、StyleProfile、StyleRule |
| `09-analysis-runtime.md` | AnalyzerDefinition、AnalysisRun、DAG、fingerprint、再解析 |
| `10-review-and-overrides.md` | Confidence、ReviewQueue、ManualOverride、Effective View |
| `11-style-lint.md` | 自作品比較、Finding、Evidence、severity policy |
| `12-storage-schema.md` | 永続化モデル、テーブル/インデックス、revision/provenance |
| `13-api-and-webui.md` | API契約、Web UI、NovelProductionとの統合境界 |
| `14-testing-and-evaluation.md` | fixture、gold dataset、回帰評価、integration test |

ファイル番号は依存関係と読解順を示すためのものであり、実装Phaseと一対一には対応しません。

## 詳細設計のルール

- `basic-design.md` と矛盾する場合は、基本設計の更新要否を先に判断する。
- 各文書は対象scope、前提、データ契約、処理フロー、失敗時挙動、テスト条件を明示する。
- LLM利用箇所はmodel/prompt/analyzer versionと再現性の扱いを明記する。
- 推論結果には可能な限りevidence spanとconfidenceを持たせる。
- 人手修正を再解析で破壊しない。
- unrelatedなNovelProduction本体仕様をこの配下へ混在させない。
