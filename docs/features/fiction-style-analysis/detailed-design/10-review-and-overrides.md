# 10 Review and Overrides 詳細設計

## 1. 目的

LLM推論を必要に応じて確認・修正できるReview/ManualOverrideを定義する。人手修正は再解析で消さない。一方、Low Confidence結果を全件ReviewQueueへ積む運用は避ける。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  review_models.py
  review_repository.py
  review_service.py
  effective_view.py
  override_registry.py
```

## 3. Effective View

基本優先順位:

```text
ManualOverride
  > Confirmed Current Inference
  > Current Eligible Inference above AnalysisPolicy threshold
  > Unknown/Default
```

Rejected InferenceはEffectiveにならない。

Current Inferenceは09 Current AnalysisRun Resolverに従う。旧Analyzer/旧Policy/旧Dependency LineageのAnnotationを混ぜない。

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

Status:

```text
open
resolved
ignored
superseded
```

Priority:

```text
low
normal
high
```

Structure Invariant/Mapping破損はReviewではなくError。

## 5. 初期ReviewItem Type

```text
scene_boundary_proposal
structure_warning
stale_override
manual_review
```

Speaker/Entity/Term/POV等のLow Confidenceや候補複数はSemantics画面でRaw/Unknownとして表示し、ReviewItemを自動作成しない。

ユーザーは任意Subjectを明示的にReviewへ追加できる。

## 6. Scene Boundary Proposal

06 Candidate Min以上/Auto Apply未満Candidateは通常Structure画面に表示するだけ。

ユーザーがReviewへ追加した場合:

```text
item_type = scene_boundary_proposal
subject_type = block
subject_id = after_block_id
analysis_run_id = boundary run
```

Acceptは03 Manual Split、RejectはReviewItem Resolveのみ。

## 7. ManualOverride

ReviewItemを経由せず直接作成可能。

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

Operation:

```text
set
clear
```

`field_path` はOverride Registry定義だけ許可する。

## 8. Override Registry

初期Fieldを以下で固定する。

### Block / Mention

```text
block.speaker_entity_id        int|null
mention.entity_id              int|null
```

### Entity

```text
entity.enabled                 bool
entity.canonical_name          non-empty string
entity.entity_type             Entity Type enum
```

Default:

```text
entity.enabled = true
```

### Term

```text
term.enabled                              bool
term.canonical_label                      non-empty string
term.term_type                            Term Type enum
term.novelty                              novelty enum
term.exact_match_safe                     bool
term.sufficient_explanation_annotation_id int|null
```

Default:

```text
term.enabled = true
```

### Scene

```text
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
scene.pov_mode
scene.pov_entity_id
```

Taxonomy Valueは06 RegistryでValidationする。

## 9. Set / Clear Semantics

### set

RegistryでValue TypeをValidationし、その値をEffective最優先にする。

### clear

「Manual指定を解除してInferenceへ戻す」と「明示的にNoneにする」を混同しない。

そのためFieldごとにClear Semanticsを固定する。

- `block.speaker_entity_id`: `clear` = Explicit Unknown Speaker。Inferenceへ戻す操作ではない。
- `mention.entity_id`: `clear` = Explicit Unresolved。
- `term.sufficient_explanation_annotation_id`: `clear` = Explicit No Sufficient Explanation。
- Nullable Scene POV Entity: `clear` = Explicit None。
- Non-null Identity/Enum/Bool Field（entity.enabled/name/type, term.enabled/label/type/novelty/exact_match_safe等）: `clear` は許可しない。

Manual指定を取り消してInferenceへ戻したい場合は、現在Active Overrideを`superseded`する新しい専用操作 `revert` をService APIとして提供する。DB operation enumへ `revert` rowを追加せず、ServiceがActive Overrideの `superseded_by_id` を「revert marker row」へ向ける方式も不要。

v1では簡潔に、**Revert時はActive Override rowの `superseded_by_id` に新しいTombstone Override row IDを設定し、Tombstone rowは `operation=clear` ではなく `operation=revert` とする。**

したがってDB operation enumは:

```text
set
clear
revert
```

`revert`:

- value_json=NULL
- Effective ResolverはそのrowをManual Valueとして扱わず、下位のConfirmed/Inferenceへフォールバックする
- Revert row自体は履歴として残る

これで「Explicit None」と「Manual Override解除」を区別する。

## 10. Override Validation

### Structure Subject

Block/Mention/Scene:

- `structure_revision_id` 必須
- SubjectがそのStructureRevision所属

### Entity/Term Stable Identity

`structure_revision_id` は通常NULL可。

### Entity/Term Enabled

BoolだけValidation。`false` はIdentityを削除しないCorrection。

### Canonical Name/Label

Trim後1文字以上、既存上限に合わせ最大200文字。Uniquenessを強制しない。同名実体が存在し得るため。

### Entity/Term Type

04/05 enumだけ。

### Term Sufficient Explanation Annotation ID

Set時:

- `annotation_type=term_explanation`
- Subjectが同Term
- Current Effective Text/Structure LineageのAnalysisRun

ClearならExplicit None。

### Revert

Active Overrideが存在するFieldだけ許可。ActiveなしはNo-op成功ではなく `OVERRIDE_NOT_FOUND` 404。

## 11. Override履歴

Override Value rowはUpdate/Deleteしない。

新Set/Clear/Revert時:

1. Active OverrideをTransaction内で取得
2. 新Override row insert
3. 旧Active rowの `superseded_by_id` だけ新IDへupdate
4. commit

Active Overrideは `superseded_by_id IS NULL` の最新row。

Revert row自身がActiveでも、Effective ResolverはManual値として扱わず下位へフォールバックする。

その後SetすればRevert rowをsupersedeして新SetがActiveになる。

## 12. Confirm / Reject

`style_inference_reviews`:

```text
id
subject_type
subject_id
field_path
analysis_run_id
review_status = confirmed | rejected
note nullable
created_at
```

同一Inferenceへ判定を変更する場合、最新Review rowを採用する。InferenceReview専用supersede pointerは増やさない。

- Inference正しい -> Confirmed
- 正解が別値 -> Rejected + ManualOverride Set/Clear
- 判断不能 -> Rejectまたは何もしない

ReviewItemが存在しなくても利用可能。

## 13. Alias Confirmation

04/05のInferred AliasをAuto Resolution根拠へ昇格する場合:

```text
subject_type = entity_alias | term_alias
subject_id = alias row id
field_path = alias.confirmed
analysis_run_id = alias.analysis_run_id
review_status = confirmed | rejected
```

Manual AliasはConfirmation不要。

Rejected Inferred AliasはCandidate一覧のRaw表示以外には利用しない。

## 14. Typed Resolver

```python
def resolve_speaker(block_id: int, structure_revision_id: int) -> EffectiveValue[int | None]: ...
def resolve_scene_semantics(scene_id: int, structure_revision_id: int) -> EffectiveSceneSemantics: ...
def resolve_entity_enabled(entity_id: int, context: EffectiveContext) -> bool: ...
def resolve_entity_name(entity_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
def resolve_entity_type(entity_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
def resolve_term_enabled(term_id: int, context: EffectiveContext) -> bool: ...
def resolve_term_label(term_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
def resolve_term_type(term_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
def resolve_term_novelty(term_id: int, context: EffectiveContext) -> EffectiveValue[str]: ...
def resolve_term_exact_match_safe(term_id: int, context: EffectiveContext) -> EffectiveValue[bool]: ...
def resolve_term_explanation(term_id: int, context: EffectiveContext) -> EffectiveValue[int | None]: ...
```

`EffectiveContext`:

```text
document_id
text_revision_id
structure_revision_id
reference_work_id nullable
reference_episode_id nullable
```

Resolver内部でLatest Revisionを暗黙選択しない。

返却共通情報:

```text
value
source = manual | confirmed | inferred | default | unknown
confidence nullable
analysis_run_id nullable
override_id nullable
stale_override boolean
```

Enabled Defaultはtrue。Identity Name/TypeのDefaultはIdentity rowの初期値。

## 15. Disabled Identityの扱い

### Entity

`entity.enabled=false`:

- Current Entity Resolver候補から除外
- Effective Speakerが指していてもSpeakerはUnknown
- Current Relation/Participant/Character Metricから除外

### Term

`term.enabled=false`:

- Current Term Resolver候補から除外
- Exact-match補完しない
- Current Term Metricから除外
- Explanation/NoveltyはRaw閲覧のみ

Disabled IdentityをDBから物理削除しない。

## 16. Stale Override

新AnalysisRunだけではManualOverrideをSupersedeしない。

### Structure Subject消滅

1. Canonical Span + Subject Type完全一致を新Structureで検索
2. 1件ならMigration Proposal
3. 自動移行しない
4. 旧Override保持

### Annotation ID参照

`term.sufficient_explanation_annotation_id` がCurrent Lineage外ならEffectiveにせず `stale_override=true`。

Stale Override ReviewItemは同Subject/Fieldで重複Openを作らない。

## 17. Override後Recompute

| Override | Recompute |
|---|---|
| Speaker | Speaker Metric -> Aggregate -> Lint |
| Entity enabled | Speaker/Relation dependent analysis stale、Speaker Metric/Aggregate/Lint |
| Entity name/type | Resolver dependent Run stale。既存Basic Metric変更なし |
| Mention Entity | Speaker Attribution stale。自動Full Analysisはしない |
| Term enabled/label/type | Term Resolver/Explanation dependent Run stale、Term Metric/Aggregate/Lint |
| Term novelty/exact match/explanation | Term Metric -> Aggregate -> Lint |
| Scene Semantics | Semantic Metric/Scene Aggregate -> Lint |
| POV | Selector使用Aggregate/Lint |

Identity候補集合を変えるOverride（Entity/Term enabled/name/type）は09 Current Run ResolverのFingerprint入力そのものではないため、AnalysisService側で関連AnalyzerをStale Mark/Deleteせず**新Analyze Jobを必要としている状態**をDocument Statusへ表示する。

v1ではOverride確定後に必要最小のAnalyze/Recompute Jobを自動Queueしてよい。毎回ユーザー確認を挟まない。

## 18. Concurrency

ローカル単一User前提。

- ReviewItem Resolve/Ignore: `expected_version`
- Structure Split/Merge: `expected_structure_revision_id`
- Direct Override: Structure依存Subjectだけ `structure_revision_id`
- 別Generic CAS Tokenは追加しない

## 19. Evidence

ReviewItemは本文全文を複製しない。

```json
{
  "text_revision_id": 10,
  "spans": [{"start_cp": 120, "end_cp": 152}],
  "block_ids": [5, 6]
}
```

表示時Excerpt最大1000 Code Points。

## 20. Bulk Action

v1は複数ReviewItem Ignoreだけ。必要性が出るまで他Bulk Actionは追加しない。

## 21. Test

- Manual > Confirmed > Inferred
- Rejected非Effective
- Direct Override without ReviewItem
- Set/Clear/Revert差
- Speaker Clear = Explicit Unknown
- Revert = InferenceへFallback
- Non-null Field Clear拒否
- Active Override Supersede
- Entity Enabled Default True / False Override
- Term Enabled Default True / False Override
- Entity/Term Name/Type Override
- Alias Confirm/Reject
- Reanalysis後Manual維持
- Structure Subject Stale Proposal
- Explanation Annotation ID Validation/Stale
- Speaker/Term Override Recompute
- ReviewItem CAS
- Low-confidence自動Reviewなし
- Optional Note

## 22. Codex禁止事項

- Inference Row直接編集
- 再解析でManualOverride削除
- 任意JSONPath許可
- Scene Splitを同Revision Update
- Low-confidence自動Review量産
- Note/Reason必須化
- Direct Overrideに汎用二重CAS追加
- `clear` と「Override解除」を同じ意味にする
- Entity/Term誤抽出訂正のためIdentity Rowを物理Delete/Update
- Term説明Overrideを曖昧Booleanだけで表現
