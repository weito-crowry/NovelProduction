# 10 Review and Overrides 詳細設計

## 1. 目的

LLM推論を必要に応じて確認・修正できるEffective View / ManualOverrideを定義する。人手修正を再解析で失わず、low-confidence結果を全件ReviewQueueへ送らない。解析状態はDBへbool保存せずCurrent Runから派生する。

上位仕様は `../basic-design.md`。

## 2. Effective View

共通優先順位:

```text
Latest ManualOverride Event
> Confirmed Current Inference
> Current Eligible Inference
> Unknown / Default
```

Rejected Current InferenceはEffectiveにならない。

Current Inferenceは09 Current AnalysisRun Resolverで選ぶ。旧Revision/旧Dependency Lineageを混ぜない。

## 3. ReviewItem

ReviewItemは**ユーザーが後で確認したい項目だけ**persistする。Inferenceの真偽判定そのものはSection 7 InferenceReviewで行う。

論理Schema:

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
resolution_note nullable
version
created_at
resolved_at nullable
```

Priority:

```text
normal
high
```

Default=`normal`。

Status:

```text
open
resolved
ignored
superseded
```

Type:

```text
scene_boundary_proposal
structure_warning
stale_override
manual_review
```

Reason Code初期値:

```text
boundary_candidate
structure_warning
stale_override
user_marked
```

Low Confidence/Unknownだけを理由に自動ReviewItem生成しない。

### 3.1 Manual ReviewItem作成

ユーザーは任意Subjectを「後で確認」として登録できる。

```python
ReviewService.create_manual_review_item(
    *,
    subject_type: str,
    subject_id: int,
    analysis_run_id: int | None = None,
    priority: Literal["normal", "high"] = "normal",
) -> ReviewItem
```

ServiceがSubjectからScopeを解決し、次を固定する。

```text
item_type = manual_review
status = open
reason_code = user_marked
version = 1
resolution_note = NULL
resolved_at = NULL
```

`evidence_json`はSubjectを再表示するためのID/Span参照だけをServiceが生成する。本文全文を複製しない。

同Subjectへ複数`manual_review`を作成することは許容する。v1でUnique/Dedupe制約を追加しない。

### 3.2 Resolve / Ignore

更新可能なのはReviewItemの管理状態だけ。

`resolve(expected_version, note)`:

```text
open -> resolved
resolution_note = note nullable
resolved_at = now
version += 1
```

`ignore(expected_version, note)`:

```text
open -> ignored
resolution_note = note nullable
resolved_at = now
version += 1
```

`expected_version`不一致は409 `VERSION_CONFLICT`。

`resolved|ignored|superseded`からの再Resolve/Ignoreは409 `REVIEW_ITEM_CLOSED`。

ReviewItem Resolve/IgnoreはInference Confirm/Reject、Override、Structure Split/Merge等を暗黙実行しない。

`superseded`は内部Serviceが「元Subject/ProposalがCurrent Lineageでは意味を失った」と判断した場合だけ使用する。User APIから直接指定しない。

## 4. ManualOverride Append-only Event

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
```

Operation:

```text
set
clear
revert
```

- `set`: Explicit Value。
- `clear`: Field定義上のExplicit None/Unknown。
- `revert`: Manual指定を解除し下位Inferenceへ戻す。

Existing EventをUpdate/Deleteしない。Supersede Pointer/Active Unique Indexを持たない。

Effective Manual Event:

```text
ORDER BY created_at DESC, id DESC LIMIT 1
```

Latestが`revert`ならManual値なしとして下位へFallbackする。

Active Manual Eventがない状態で`revert`は404 `OVERRIDE_NOT_FOUND`。

Note/Reasonは任意。

## 5. Override Registry

### Block

```text
block.speaker_entity_id        int|null
block.semantic_primary         semantic primary enum
```

Speaker Clear = Explicit Unknown。Semantic Primary Clear不可。

### Mention

```text
mention.entity_id              int|null
```

Clear = Explicit Unresolved。

### Entity

```text
entity.enabled                 bool
entity.canonical_name          string
entity.entity_type             entity enum
```

Clear不可。Default enabled=true。

### Term

```text
term.enabled                   bool
term.canonical_label           string
term.term_type                 term enum
term.novelty                   novelty enum
```

Clear不可。Default enabled=true。

### TermMention

```text
term_mention.sufficient_explanation_annotation_id   int|null
```

Clear = Explicit No Sufficient Explanation for this Mention。

### Scene

```text
scene.function                 list[function enum]
scene.tone                     list[tone enum]
scene.pace                     pace enum
scene.information_load         information_load enum
scene.interaction              interaction enum
scene.pov_mode                 pov_mode enum
scene.pov_entity_id            int|null
```

Function/Tone重複禁止。`unclear`とConcrete同時指定禁止。POV Entity Clear = Explicit None。

## 6. Validation

Structure Subject (`block|mention|term_mention|scene`):

- `structure_revision_id`必須。
- SubjectがそのStructure/Lineage所属。

Entity/Term:

- 同Project DB内。
- Reference Work/Document Scope Validationを各Serviceで行う。

Name/Label:

- trim後1〜200文字。
- Uniqueness強制なし。

Speaker/POV Entity:

- Enabled Person Entity。
- 対象Scopeで利用可能。

TermMention Explanation Annotation:

- `annotation_type=term_explanation`。
- `subject_type=term_mention`。
- 同TermMention Subject。
- 指定Text/Structure Lineage。

ReviewItem Manual Create:

- Subjectが同Project DB内に存在。
- `analysis_run_id`指定時は同Subject Scopeかつ同Project DB。
- Priority Known Enum。

## 7. Inference Review

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

同Inferenceの最新Reviewを採用する。

ReviewItemなしで利用可能。

ConfirmedはConfidence Thresholdに関係なくRaw Inferenceを承認したものとしてEffectiveに使う。ただしField Schema/Taxonomy Validationは行う。

Alias ConfirmationもInferenceReviewを使う。

## 8. Typed Effective Resolver

最低限:

```python
resolve_speaker(...)
resolve_block_semantic(...)
resolve_mention_entity(...)
resolve_entity_enabled(...)
resolve_entity_name(...)
resolve_entity_type(...)
resolve_term_enabled(...)
resolve_term_label(...)
resolve_term_type(...)
resolve_term_novelty(...)
resolve_term_mention_explanation(...)
resolve_scene_semantics(...)
```

Resolver内部でLatest Text/Structureを暗黙選択しない。

共通返却:

```text
value
source = manual | confirmed | inferred | default | unknown
confidence nullable
analysis_run_id nullable
override_id nullable
stale_override boolean
```

## 9. Disabled Identity

Entity disabled:

- Entity Resolver候補外。
- Speaker/POV Entity参照Unknown/None。
- Character Metric対象外。

Term disabled:

- Term Resolver候補外。
- Term Metric対象外。

Historical Rowは削除しない。

## 10. Stale Override

Structure依存Subjectが新Structureで消えた場合、そのOverrideはCurrent Effectiveに使わず`stale_override=true`を返す。

Migration候補を提示する場合だけ:

1. Canonical Span + Subject Type完全一致を新Structureで検索。
2. Exactly 1件ならMigration Proposalを作成可能。
3. 自動移行しない。
4. 旧Event保持。

TermMention Explanation Overrideが指定Current Lineage外ならEffectiveにしない。

Stale Overrideは明示的人手修正が使えなくなった場合なのでReviewItem生成を許可する。ただし同Subject/FieldのOpen `stale_override` Itemは重複生成しない。

## 11. Correction後の処理分類

### A. Metric-only Recompute

09内部`analyze_document preset=metrics`を自動Queueしてよい。

```text
block.speaker_entity_id
block.semantic_primary
term.novelty
term_mention.sufficient_explanation_annotation_id
```

次のInference ReviewでEffective値が変わる場合も同分類:

```text
speaker
block.semantic_primary
term.novelty
term_explanation
```

Semantic Metric Groupだけ再計算する。確認Dialog不要。

### B. Semantic Reanalysis Required

Resolver/Speaker/POV等の入力集合を変えるためSemantic Current RunがStaleになる。Full Analysisを自動Queueしない。

```text
Manual Entity/Alias
entity.enabled
entity.canonical_name
entity.entity_type
mention.entity_id
mention.entity_resolution Confirm/Reject
Entity Alias Confirm/Reject
Manual Term/Alias
term.enabled
term.canonical_label
term.term_type
Term Alias Confirm/Reject
```

Entity/Term Enable変更をMetric-onlyで完了扱いしない。

### C. Aggregate/Lint Selector State Only

```text
scene.function
scene.tone
scene.pace
scene.information_load
scene.interaction
```

および同Axis Inference Review。

Semantic Metricは再計算しない。08/11 FingerprintでAggregate/Lint Staleを表現する。

### D. Display-only v1

```text
scene.pov_mode
scene.pov_entity_id
```

およびPOV Review。

v1 Metric/Selectorへ使わないため再計算Jobなし。

## 12. Analysis Statusは派生・Group別

`analysis_stale`等のbool ColumnをDBへ保存しない。

`AnalysisStatusService` はDocument Current Text/Current Structureに対して次を返す。

```json
{
  "basic": {
    "state":"not_analyzed | current | stale",
    "reasons":[]
  },
  "semantic": {
    "state":"not_analyzed | current | stale | partial",
    "reasons":[]
  }
}
```

### 12.1 Current判定を最優先

まず09 Current ResolverでCurrent Runを解決する。

- Current Basic Metric Succeeded Runがあれば`basic=current`。
- Required Semantic SetがCurrent Succeeded/Not Applicableで揃えば`semantic=current`。

古いHistorical Runが残っていてもCurrentが揃っている限りStaleにしない。

### 12.2 basic

Current Basicが無い場合:

- Documentに過去のSucceeded Basic Metric Runが1件以上ある -> `stale`。
- 成功履歴なし -> `not_analyzed`。

旧TextRevision/旧StructureRevisionの成功歴もStale根拠になる。

Failed attemptだけはJob履歴で表示し、成功履歴がなければ`not_analyzed`のままでよい。

### 12.3 semantic required set

```text
entity-mention-extractor
entity-resolver
speaker-attribution
term-candidate-extractor
term-resolver
term-explanation-detector
scene-semantic-classifier
block-semantic-classifier
pov-classifier
style-metrics-semantic
```

Analyzerが対象Subject 0件で正常完了した場合はSucceeded/Not Applicableとして扱う。

Boundary AnalyzerはStructure決定系でありSemantic Required Setには含めない。

### 12.4 semantic Currentが揃わない場合

優先順位:

```text
stale > partial > not_analyzed
```

#### stale

DocumentにHistorical Succeeded/Partial Semantic Runが存在し、Current Required Setが揃わない原因の少なくとも1つが次ならStale:

- Current TextRevision変更。
- Current StructureRevision変更。
- Analyzer/Prompt/Taxonomy/MetricDefinition変更。
- Relevant Policy Input変更。
- Human State変更。
- Required Dependency Lineage変更。

Entity/Term Registry Correction、Mention Resolution Correction/Review後は、他BranchがCurrentでも`semantic=stale`を優先する。

#### partial

Stale原因がなく、Current Text/Structure Lineage上で:

- Current Partial Runがある、または
- 初回/再実行Full Analysisで一部Semantic BranchがFailed/Dependency不足だが他のCurrent Semantic Outputが利用可能

場合。

#### not_analyzed

DocumentにSucceeded/Partial Semantic Historical Runがなく、Current Semantic Outputもない。

Deterministic Analysisだけ実施済みなら:

```text
basic=current
semantic=not_analyzed
```

Reason例:

```text
TEXT_REVISION_CHANGED
CURRENT_STRUCTURE_CHANGED
ENTITY_REGISTRY_CHANGED
TERM_REGISTRY_CHANGED
MENTION_RESOLUTION_CHANGED
SEMANTIC_BRANCH_PARTIAL
```

## 13. Concurrency

ローカル単一User前提。

- ReviewItem Resolve/Ignore: `expected_version`。
- ReviewItem Create: CAS不要。
- Structure Split/Merge: `expected_structure_revision_id`。
- Direct Override: Structure依存Subjectだけ`structure_revision_id`。
- Generic CAS Tokenなし。

Append-only OverrideなのでActive Row更新競合なし。

## 14. Evidence

ReviewItemは本文全文を複製しない。

```json
{
  "text_revision_id":10,
  "spans":[{"start_cp":120,"end_cp":152}],
  "block_ids":[5,6]
}
```

表示時Excerpt最大1000 Code Points。

## 15. Test

- Manual > Confirmed > Inferred。
- Rejected非Effective。
- Append-only Set/Clear/Revert/Fallback/New Set。
- Existing Override Update/Deleteなし。
- Manual ReviewItem Createはmanual_review/user_marked/open/version1。
- ReviewItem priority normal/high。
- ReviewItem Resolve/Ignore expected_version、resolution_note、version increment。
- Closed ReviewItem再更新拒否。
- ReviewItem ResolveでDomain Correctionなし。
- Low-confidence自動Reviewなし。
- Speaker Clear = Explicit Unknown。
- Mention Clear = Explicit Unresolved。
- TermMention Explanation Clear = Explicit None。
- Confirmed InferenceはThreshold未満でも承認値採用。
- Function/Tone Validation。
- Disabled Identity。
- Alias Confirm/Reject。
- Structure Subject Stale。
- Explanation Lineage。
- Metric-only4分類だけmetrics preset。
- Mention Resolution ReviewはSemantic Reanalysis Required。
- Entity/Term enabledはSemantic Reanalysis Required。
- Scene AxisでMetric Jobなし。
- Deterministicのみ -> basic current / semantic not_analyzed。
- New Current Text + old Basic/Semantic歴 -> both stale。
- Manual Current Structure切替 + old歴 -> stale。
- Semantic Registry Correction + 他Branch current -> semantic stale優先。
- Current Execution Partialのみ -> semantic partial。
- Semantic all current + old historical rows -> current。
- Failed Basic attemptのみ -> basic not_analyzed。

## 16. Codex禁止事項

- ReviewItemをInference Reviewの代替にする。
- Manual ReviewItem作成をReview対象Typeごとの個別APIへ分散する。
- Low-confidence Review量産。
- ReviewItem Resolve/IgnoreでInference/Override/Structureを暗黙変更。
- ReviewItem note/priorityを必須入力化。
- Supersede Pointer/Active UniqueをManualOverrideへ再導入。
- Existing Override Event Update/Delete。
- Generic二重CAS追加。
- `clear`と`revert`同義化。
- Entity/Term Enable変更をMetric-onlyで完了扱い。
- Scene Axis変更だけでSemantic Metric再解析。
- Human Correctionの度にFull Analysis自動実行。
- `analysis_stale`等の永続bool Column追加。
- Basic/Semantic状態を単一Stateへ潰す。
- Currentが揃っているのにHistorical Runの存在だけでStale扱い。
- Revision/State変更によるStaleをPartialで隠す。
