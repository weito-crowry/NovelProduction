# 10 Review and Overrides 詳細設計

## 1. 目的

LLM推論を必要に応じて確認・修正できるReview/ManualOverrideを定義する。人手修正は再解析で消さない。一方、低confidence結果をすべてReviewQueueへ積むような運用は避ける。

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
  > inferred value above AnalysisPolicy threshold
  > unknown/null
```

rejected inferenceはeffectiveにならない。

raw inference rowは編集せずoverlayで解決する。

## 4. ReviewItemの役割

ReviewItemは「ユーザー操作を促す価値がある曖昧さ」だけをpersistする。unknown/低confidenceという理由だけでは必ずしも作らない。

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

structure invariantやmapping破損はReviewではなくerrorとして扱うため`critical` priorityは設けない。

## 5. 初期ReviewItem

```text
speaker_conflict
entity_resolution_conflict
scene_boundary_proposal
structure_warning
stale_override
```

Term novelty、Scene semantics、POV等の低confidence結果はSemantics画面のfilterで確認できるため、自動ReviewItemは原則作らない。将来ユーザーがreview workflowを望む項目だけ追加する。

## 6. ReviewItem生成条件

- speaker候補が複数あり、有力候補差が小さい
- Entity resolverが複数候補conflictを返した
- Scene boundary candidateが `candidate_min` 以上 `auto_apply` 未満で、ユーザーが「境界候補をReviewに追加」を実行した
- automatic structure warningのうちユーザー操作で修正可能なもの
- ManualOverride対象が新StructureRevisionで消え、移行候補がある

Scene boundary proposalはデフォルトではStructure画面に表示するだけで、ReviewQueueへ全件自動追加しない。

## 7. ManualOverride

```text
id
subject_type
subject_id
field_path
operation
value_json nullable
base_analysis_run_id nullable
note nullable
created_at
superseded_by_id nullable
```

operation:

```text
set
clear
```

`field_path` はregistry定義だけ許可する。

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

`note` は任意。理由入力を毎回必須にしない。

## 8. Override履歴

Override valueをupdate/deleteしない。修正時は新rowをinsertし旧rowの `superseded_by_id` だけ更新する。

Effective Viewはactive最新overrideを採用する。

## 9. Confirm/Reject

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

- AI=A、正しい=A -> confirmed
- AI=A、正しい=B -> rejected + ManualOverride B
- 判断不能 -> rejectまたはManualOverride clear。noteは任意

## 10. Typed resolver

```python
def resolve_speaker(block_id: int) -> EffectiveValue[int | None]: ...
def resolve_scene_semantics(scene_id: int) -> EffectiveSceneSemantics: ...
def resolve_term_novelty(term_id: int) -> EffectiveValue[str]: ...
```

共通返却:

```text
value
source = manual | confirmed | inferred | unknown
confidence nullable
analysis_run_id nullable
override_id nullable
```

## 11. 再解析とstale override

新AnalysisRunだけではManualOverrideをsupersedeしない。

StructureRevision変更でsubject IDが消えた場合:

1. canonical span + subject typeが完全一致する新subjectを検索
2. 1件だけならmigration proposalを作る
3. 自動移行しない
4. 旧overrideは保持

span完全一致がなければstaleとして表示するだけでよい。複雑な類似度migrationはv1で実装しない。

## 12. Scene split/merge

Scene boundary proposal accept:

- `after_block_id` でmanual split
- 新StructureRevision
- 後続Semantic/Metricをstale化
- analyze jobを自動queueしてよい

rejectはproposalを閉じるだけ。

Mergeは隣接Sceneの明示操作。

## 13. Override後再計算

| override | recompute |
|---|---|
| speaker | speaker metric -> Aggregate -> Lint |
| scene semantics | semantic metric/scene Aggregate -> Lint |
| term novelty/explanation | term metric -> Aggregate -> Lint |
| entity canonical name | 表示のみ |
| mention entity | speaker analyzer stale化。自動full analysisはしない |
| POV | POV selectorを使うAggregate/Lintのみ |

job queueを使いHTTP request内で同期再計算しない。

## 14. Concurrency

ローカル単一user前提なので二重の競合tokenは導入しない。

- ReviewItem resolve/ignore: `expected_version` を使い既存VERSION_CONFLICT contractを再利用。
- ManualOverride作成: 対象 `subject_id` と、Structure依存subjectでは `structure_revision_id` を送る。別のeffective revision tokenは要求しない。
- Scene split/merge: `expected_structure_revision_id`。

これで古い画面からの構造変更は防ぎつつ、通常Override操作の入力を増やさない。

## 15. Evidence

ReviewItemへ本文全文を複製しない。

```json
{
  "text_revision_id": 10,
  "spans": [{"start_cp": 120, "end_cp": 152}],
  "block_ids": [5, 6]
}
```

表示時にTextRevisionからexcerptを取得。最大1000 code points。

## 16. Bulk action

v1は複数ReviewItemのignoreのみ用意する。他のbulk処理は必要性が出てから追加する。

## 17. テスト

- manual > confirmed > inferred
- rejected非effective
- override supersede
- reanalysis後manual維持
- stale subject exact-span proposal
- speaker override recompute
- ReviewItem CAS
- Scene proposal accept
- low-confidenceだけではReviewItem大量生成なし
- optional note

## 18. Codex実装時の禁止事項

- inference rowを直接編集しない。
- 再解析でManualOverrideを削除しない。
- 任意JSONPathをfield_pathに許可しない。
- Scene splitを同じStructureRevision上でupdateしない。
- 低confidence結果ごとにReviewItemを自動生成しない。
- Override note/reasonを必須入力にしない。
- ManualOverrideへReviewItemとは別の汎用CAS tokenを追加しない。