# 10 Review and Overrides 詳細設計

## 1. 目的

LLM推論を必要に応じて確認・修正できるReview/ManualOverrideを定義する。人手修正は再解析で消さない。一方、低confidence結果を全件ReviewQueueへ積む運用は避ける。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  review_models.py
  review_repository.py
  review_service.py
  effective_view.py
```

## 3. Effective View

```text
manual override
  > confirmed inference
  > latest eligible inferred value above AnalysisPolicy threshold
  > unknown/null
```

rejected inferenceはeffectiveにならない。

「latest eligible inferred」は09 Effective AnalysisRun選択に従う。別Text/Structure lineageの古いAnnotationを混ぜない。

## 4. ReviewItem

ReviewItemはユーザー操作を促す価値がある項目だけpersistする。

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
version
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
```

structure invariant/mapping破損はReviewではなくerror。

## 5. 初期ReviewItem type

```text
scene_boundary_proposal
structure_warning
stale_override
```

Speaker/Entity/Term/POV等の低confidenceや候補複数はSemantics画面でraw/unknownとして表示する。ReviewItemを自動作成しない。

ユーザーは任意subjectをSemantics/Structure画面から明示的に「Reviewへ追加」できる。その場合item typeは対象に応じた汎用 `manual_review` を使用してよい。

## 6. Scene Boundary proposal

06 candidate_min以上/auto_apply未満candidateは通常Structure画面に表示するだけ。

ユーザーがReviewへ追加した場合:

```text
item_type = scene_boundary_proposal
subject_type = block
subject_id = after_block_id
analysis_run_id = boundary run
```

acceptは03 manual split、rejectはReviewItem resolvedのみ。

## 7. ManualOverride

ReviewItemを経由せず直接作成可能。Semantics画面からの修正をReviewQueueへ迂回させない。

```text
id
subject_type
subject_id
field_path
operation
value_json nullable
base_analysis_run_id nullable
structure_revision_id nullable
note nullable
created_at
superseded_by_id nullable
```

operation:

```text
set
clear
```

`field_path` はregistry定義だけ許可。

初期path:

```text
block.speaker_entity_id
mention.entity_id
term.novelty
term.exact_match_safe
term.sufficient_explanation_annotation_id
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
scene.pov_mode
scene.pov_entity_id
entity.canonical_name
entity.entity_type
```

Term説明は曖昧な `term.explanation_status` を使わない。effective sufficient explanationとして使う具体的 `term_explanation` Annotation IDを指定する。

`note` は任意。

## 8. Override validation

### block / mention / scene

`structure_revision_id` 必須。subjectがそのStructureRevisionに所属することを検証する。

### term/entity stable identity field

`structure_revision_id` は通常NULL可。

### term.sufficient_explanation_annotation_id

set valueのAnnotationが:

- `annotation_type=term_explanation`
- `subject_type=term`
- 同 `term_id`
- current effective Text/Structure lineageに属するAnalysisRun

であることを検証する。

clearならeffective explanationなし。

### term.novelty / exact_match_safe

value enum/boolだけvalidationし、特定AnalysisRun tokenを別途要求しない。

## 9. Override履歴

Override valueはupdate/deleteしない。修正時は新row insert + 旧row `superseded_by_id` 更新だけ。

同一subject/fieldでactive overrideは1件。repositoryがtransaction内で現在active rowをsupersedeして新rowを作る。

## 10. Confirm/Reject

`style_inference_reviews`:

```text
subject_type
subject_id
field_path
analysis_run_id
review_status = confirmed | rejected
note nullable
created_at
```

- inference正しい -> confirmed
- 正解が別値 -> rejected + ManualOverride
- 判断不能 -> rejectedまたはManualOverride clear

ReviewItemが存在しなくてもconfirm/reject APIを利用可能にしてよい。

## 11. Typed resolver

```python
def resolve_speaker(block_id: int, structure_revision_id: int) -> EffectiveValue[int | None]: ...
def resolve_scene_semantics(scene_id: int, structure_revision_id: int) -> EffectiveSceneSemantics: ...
def resolve_term_novelty(term_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
def resolve_term_exact_match_safe(term_id: int, context: EffectiveContext) -> EffectiveValue[bool]: ...
def resolve_term_explanation(term_id: int, context: EffectiveContext) -> EffectiveValue[int | None]: ...
def resolve_entity_name(entity_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
```

`EffectiveContext` はdocument/TextRevision/StructureRevisionと、reference workの場合は対象episode contextを持つ。暗黙latest参照をresolver内部で行わない。

返却:

```text
value
source = manual | confirmed | inferred | unknown
confidence nullable
analysis_run_id nullable
override_id nullable
stale_override boolean
```

## 12. Stale Override

新AnalysisRunだけではManualOverrideをsupersedeしない。

### Structure subject消滅

1. canonical span + subject type完全一致を新Structureで検索
2. 1件ならmigration proposal
3. 自動移行しない
4. 旧Override保持

### Annotation ID参照Override

`term.sufficient_explanation_annotation_id` がcurrent lineage外ならvalueをeffectiveにせず `stale_override=true`。自動で別Annotationへ差し替えない。

stale OverrideはReviewItemを1件作ってよい。重複open itemは作らない。

## 13. Override後再計算

| override | recompute |
|---|---|
| speaker | speaker Metric -> Aggregate -> Lint |
| Scene semantics | semantic Metric/Scene Aggregate -> Lint |
| Term novelty/exact match/explanation | Term Metric -> Aggregate -> Lint |
| Entity name/type | 表示・resolver候補cache。既存Measurementは通常再計算不要 |
| Mention Entity | speaker attribution stale化。自動full analysisはしない |
| POV | POV selector使用Aggregate/Lintのみ |

job queueを使用。

## 14. Concurrency

ローカル単一user前提。

- ReviewItem resolve/ignore: `expected_version`。
- Structure split/merge: `expected_structure_revision_id`。
- Direct ManualOverride: `structure_revision_id` が必要なsubjectだけ要求し、別generic CAS tokenは追加しない。

## 15. Evidence

ReviewItemは本文全文を複製しない。

```json
{
  "text_revision_id": 10,
  "spans": [{"start_cp": 120, "end_cp": 152}],
  "block_ids": [5, 6]
}
```

表示時excerpt最大1000 code points。

## 16. Bulk action

v1は複数ReviewItem ignoreだけ。必要性が出るまで他bulk actionは追加しない。

## 17. Test

- manual > confirmed > inferred
- rejected非effective
- direct Override without ReviewItem
- active Override supersede
- reanalysis後manual維持
- structure subject stale migration proposal
- explanation Annotation ID validation
- explanation Annotation stale -> unknown + stale flag
- duplicate stale ReviewItemなし
- speaker/term override recompute
- ReviewItem CAS
- low-confidence自動Reviewなし
- optional note

## 18. Codex禁止事項

- inference row直接編集
- 再解析でManualOverride削除
- 任意JSONPath許可
- Scene splitを同revision update
- low-confidence自動Review量産
- note/reason必須化
- Direct Overrideに汎用二重CAS追加
- Term説明Overrideを曖昧boolean/statusだけで表現