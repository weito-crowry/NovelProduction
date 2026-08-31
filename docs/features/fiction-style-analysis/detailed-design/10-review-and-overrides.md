# 10 Review and Overrides 詳細設計

## 1. 目的

LLM推論の不確実性をユーザーが確認・修正できるReviewQueueとManualOverrideを定義する。AI再解析で人手修正を消さず、raw inferenceとeffective valueを常に分離する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  review_models.py
  review_repository.py
  review_service.py
  effective_view.py
```

WEBUIは13で定義する。

## 3. 基本優先順位

Effective Viewの優先順位を固定する。

```text
manual override
  > confirmed inference
  > inferred value above effective threshold
  > unknown / null
```

`rejected` inferenceはeffective値にならない。

confirmed inferenceは元AnalysisRunの値を保持したままstatusだけ確認済みとして扱う。raw rowをupdateせず確認recordをoverlayする。

## 4. ReviewItem

```text
id
item_type
subject_type
subject_id
analysis_run_id nullable
priority
status
reason_code
evidence_json
created_at
resolved_at nullable
```

status:

```text
open
resolved
ignored
superseded
```

priority:

```text
low
normal
high
critical
```

v1でcriticalは構造invariant/本文mapping不整合だけ。単なる低confidence speakerはnormal。

## 5. Review対象

初期item_type:

```text
speaker
entity_resolution
term_novelty
term_explanation
scene_semantics
pov
scene_boundary_candidate
structure_warning
```

ReviewQueue作成条件は各詳細設計のthresholdを正本とし、ReviewServiceに重複thresholdを持たせない。Analyzerがreview recommendationを返し、ReviewServiceが永続化する。

## 6. ManualOverride

汎用overlay tableを使用する。

```text
id
subject_type
subject_id
field_path
operation
value_json nullable
base_analysis_run_id nullable
reason
created_at
superseded_by_id nullable
```

operation:

```text
set
clear
```

`field_path` は任意JSONPathを許可しない。コードregistryに定義したpathのみ。

初期path:

```text
block.speaker_entity_id
mention.entity_id
term.novelty
term.explanation_status
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
scene.pov_mode
scene.pov_entity_id
entity.status
entity.canonical_name
```

## 7. Override不変性

ManualOverride rowはupdate/deleteしない。修正時は新rowを作り、旧rowの `superseded_by_id` のみ更新可能とする。

この例外updateは監査pointerのみで、旧value/reasonは変更しない。

Effective Viewはsupersededされていない最新overrideを採用する。

## 8. Confirm/Reject

推論確認用に `style_inference_reviews` を別tableで持つ。

```text
subject_type
subject_id
field_path
analysis_run_id
review_status = confirmed | rejected
note
created_at
```

Manual valueを入れない確認はManualOverrideを作らない。

例:

- AI speaker=A、ユーザーもAと確認 → confirmed
- AI speaker=A、正解はB → rejected + ManualOverride set B
- AI speaker=A、分からない → ManualOverride clear でもよい

## 9. Effective resolver

`effective_view.py` に対象ごとのtyped resolverを実装する。汎用dict mergeだけで済ませない。

例:

```python
def resolve_speaker(block_id: int) -> EffectiveValue[int | None]: ...
def resolve_scene_semantics(scene_id: int) -> EffectiveSceneSemantics: ...
def resolve_term_novelty(term_id: int) -> EffectiveValue[str]: ...
```

返却共通情報:

```text
value
source = manual | confirmed | inferred | unknown
confidence nullable
analysis_run_id nullable
override_id nullable
```

## 10. 再解析との関係

新AnalysisRunが作成されてもManualOverrideは自動supersedeしない。

ただしoverrideが古いstructure revisionのsubjectを参照し、新StructureRevisionでsubject IDが消滅した場合:

1. span一致する新subjectを自動候補化
2. 完全一致で1件ならoverride migration proposalをReviewQueueへ作る
3. 自動移行しない
4. 旧overrideは保持

## 11. Scene split/merge review

03のmanual StructureRevision生成をReview UIから行う。

`scene_boundary_candidate` accept:

- candidate `after_block_id` でmanual split
- 新StructureRevision作成
- 旧semantic/metricsをinvalidate
- 新しいanalyze jobを自動queueしてよい

reject:

- candidate ReviewItemをresolved/rejected相当として閉じる
- structure変更なし

Scene mergeはユーザーが隣接sceneを2つ選択した明示操作だけ。

## 12. Cascading影響

Override確定後、必要な再計算jobを自動queueする。

| override | 再計算 |
|---|---|
| speaker | speaker/character metrics → aggregate → lint |
| scene semantics | semantic metrics/scene-filter aggregate → lint |
| term novelty/explanation | term metrics → aggregate → lint |
| entity canonical name | 原則表示のみ。metric再計算なし |
| mention entity | speaker候補依存runをstale化。自動full re-analysisはしない |
| POV | profile/lintでPOV filterを使う場合のみaggregate/lint |

再計算はAnalysis Runtime jobを使う。UI request内で同期実行しない。

## 13. Review Queue sort

固定sort:

```text
priority DESC
created_at ASC
id ASC
```

filter:

```text
item_type
status
document_id
analysis_run_id
```

全文検索はv1不要。

## 14. Evidence

ReviewItem evidenceにはraw本文全文を複製しない。

```json
{
  "text_revision_id": 10,
  "spans": [
    {"start_cp": 120, "end_cp": 152}
  ],
  "block_ids": [5, 6]
}
```

APIが表示時にTextRevisionからexcerptを切り出す。excerpt最大1000 code points。

## 15. UI操作の競合

Review/overrideにCAS versionを導入する。

ReviewItem responseに `version` integerを返す。resolve/ignore時は `expected_version` 必須。競合時は既存NovelProductionの `VERSION_CONFLICT` error contractを再利用する。

ManualOverride作成時もsubject effective revision tokenを要求し、古い画面からの上書きを防ぐ。

## 16. Bulk action

v1で許可:

- 複数ReviewItemを `ignored` にする

禁止:

- 複数speakerを一括自動accept
- 複数Entity merge
- 複数Scene split

高影響操作は1件ずつ確認する。

## 17. テスト

- manual > confirmed > inferred
- rejected inferenceがeffectiveにならない
- override supersede
- re-analysis後manual維持
- stale structure override移行を自動実行しない
- speaker overrideでmetric job queue
- Review CAS conflict
- evidence excerpt最大長
- scene boundary acceptで新StructureRevision
- mergeは隣接sceneのみ

## 18. Codex実装時の禁止事項

- AI rowを直接編集して人手修正を表現しない。
- 再解析でManualOverrideを削除しない。
- field_pathに任意JSONPathを許可しない。
- scene splitを同じStructureRevision上でupdateしない。
- low-confidence推論を一括acceptする機能を追加しない。
- override reasonを空文字許可しない。最低1文字、最大1000文字とする。
