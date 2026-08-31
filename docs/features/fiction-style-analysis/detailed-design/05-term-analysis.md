# 05 Term Analysis 詳細設計

## 1. 目的

作品固有の用語・制度・技術・概念等を抽出し、Reference Work全体で同じTermを追跡する。Work/Document内初出、同Scene内説明、説明遅延を再現可能に計測できることを目的とする。

上位仕様は `../basic-design.md`。

## 2. Term Scope / Stable Identity

Exactly One Scope:

```text
reference_work_id  # Reference作品全Episode共通
document_id        # Project Draft等の単独Document
```

```text
id
reference_work_id nullable
document_id nullable
canonical_label
term_type
origin = inferred | manual
created_by_run_id nullable
created_at
```

`term_type`:

```text
world_term
technology
institution
organization_name
location_name
product_name
ability
historical_event
specialized_term
other
```

人物名はTermにしない。

Stable Identity Rowは再解析でUpdateしない。Correctionは10 ManualOverrideで:

```text
term.enabled
term.canonical_label
term.term_type
term.novelty
```

をOverlayする。

## 3. Manual Term / Alias

Modelが見落としたTermはStyle Analysis内へ直接Manual作成できる。

```python
TermService.create_manual_term(
    *,
    reference_work_id: int | None,
    document_id: int | None,
    canonical_label: str,
    term_type: str,
) -> Term
```

- Scope exactly one。
- Label trim後1〜200文字。
- Same Label別Term可。
- `origin=manual`, `created_by_run_id=NULL`。
- ReviewItem不要。

`style_term_aliases`はTerm/Alias/Origin/Run/Timestampを持つ。

Manual Alias同一再送はIdempotent。Inferred AliasだけではAuto Resolution根拠にせず、Confirmed Inferred AliasまたはManual Aliasだけを使う。

## 4. Term Candidate Extractor

`term-candidate-extractor` はTerm/Entity Registry非依存のCache可能Analyzer。

入力: Scene Text + Block ID/type/span。

出力:

```json
{
  "block_id":4,
  "surface":"統合国家知性機構",
  "start_in_block":8,
  "end_in_block":17,
  "canonical_label_candidate":"統合国家知性機構",
  "term_type_candidate":"institution",
  "novelty_candidate":"work_specific",
  "confidence":0.94
}
```

Persist:

```text
annotation_type = term_candidate
subject_type = block
subject_id = block_id
start_cp/end_cp = candidate span
value_json = surface/canonical_label_candidate/term_type_candidate/novelty_candidate
confidence
analysis_run_id
```

Span Validationは04 Mentionと同じ規則。Candidate ExtractorはTerm Identity/TermMentionを作らない。

## 5. Term Resolver

`term-resolver` はCandidate Runに`subject_partial_allowed`で依存し、Current Enabled Term Registryを読む。Cache不可。

Reference: same reference_work_id。Project: same document_id。

Auto Resolution:

1. Effective Canonical Label完全一致。ただし複数候補なら選ばない。
2. Confirmed/Manual Alias一致。ただし複数候補なら選ばない。
3. Model同一判定が09 `term_resolution_auto_merge` 以上。

既存候補なし、または明確に別Termの場合だけ新`origin=inferred` Identityを作成できる。既存Identity RowをUpdateしない。

Resolved CandidateごとにTermMentionを作成する。

```text
id
term_id
structure_revision_id
scene_id
block_id
start_cp/end_cp
surface
analysis_run_id
```

`occurrence_index`は保存しない。

## 6. Novelty

NoveltyはStable Identity列へ置かずResolver Run付きAnnotationとして保存する。

```text
annotation_type = term.novelty
subject_type = term
subject_id = term_id
value_json = {"value":"work_specific"}
confidence
analysis_run_id = term-resolver run
```

Value:

```text
work_specific
specialized_real_world
common_real_world
uncertain
```

1 Resolver Run × 1 Termにつき最大1 Annotation。

Candidate Reduce:

- concrete valueが1種類だけ -> その値。
- concrete conflict -> `uncertain`。
- 全uncertain -> `uncertain`。
- confidenceはReduce対象Candidateの最小値。

Effective Novelty:

```text
ManualOverride
> Confirmed Current Resolver Inference
> Current Resolver Inference
> uncertain
```

Rejected InferenceはEffectiveにしない。

## 7. Reference Work Registry

Reference Work Term RegistryはIncremental Stable Registry。

- Work一括解析はEpisode Order順にResolver実行。
- Resolver Cache不可。
- 後続EpisodeでRegistryが増えても前Episodeを即時全再解析しない。
- Work一括解析を再実行すれば全Episode ResolverをOrder順に再実行。
- 各Runは入力Registry Fingerprintを保存する。

## 8. First Appearance Completeness

### Reference Work

Target Episode orderを`k`とする。

Order 1..kの全Episodeについて:

```text
StyleDocument.current_text_revision_id
StyleDocument.current_structure_revision_id
Current term-resolver Run status = succeeded
```

が必要。

Order < kはDocument Current Pointerを使う。

Order = kがAnalysis実行中ならAnalyzerContextのText/Final Structure + 今回Succeeded Resolver Runを使う。

1件でも欠落/Partial/Failedなら`first_appearance_complete=false`。

### Project Document

Work Prefixはない。指定Text/StructureのCurrent `term-resolver` Runが`succeeded`であることを必須とする。Partial/UnavailableからDocument初出を確定しない。

## 9. `term_first_appearance` State Fingerprint

Reference:

```text
episode_id
document_id
text_revision_id
structure_revision_id
term_resolver_run_id
resolver_status
```

をOrder 1..kでHash。欠落値もNULLとして含める。

Project:

```text
document_id
text_revision_id
structure_revision_id
term_resolver_run_id
resolver_status
```

をHash。

前方EpisodeまたはTarget Resolver状態が変われば初出依存MetricもStaleになる。

## 10. First Appearance算出

ReferenceはCompletenessを満たす場合だけOrder 1..kのCurrent Resolver TermMentionを`episode order -> start_cp`でSortし、Termごとの最初をWork First Appearanceとする。

ProjectはTarget Structure内Current Resolver TermMentionを`start_cp`でSortしDocument First Appearanceを求める。

Completenessを満たさない場合、07の初出依存Metricを作らない。

## 11. Term ExplanationはTermMention単位

`term-explanation-detector` は`term-resolver`に`subject_partial_allowed`で依存し、Current Enabled TermMentionを対象にする。

```text
annotation_type = term_explanation
subject_type = term_mention
subject_id = term_mention_id
start_cp/end_cp = explanation span
confidence
analysis_run_id
value_json = {
  block_id,
  explanation_kind,
  completeness
}
```

Kind:`definition|paraphrase|example|contextual_clue|contrast|other`。

Completeness:`partial|sufficient`。

探索Window:

- Mention Block前2 Block。
- Mention Block後6 Block。
- 見つからなければ同Scene末尾まで。
- 別Sceneへ自動拡張しない。

## 12. Effective Sufficient Explanation

```text
ManualOverride term_mention.sufficient_explanation_annotation_id
> Confirmed Current term_explanation
> Current term_explanation if completeness=sufficient and confidence >= AnalysisPolicy.term_explanation_effective
> None
```

Manual Clearは「このMentionには十分な説明なし」。

Override Annotationは同TermMention Subject + 指定Text/Structure LineageをService Validationする。

## 13. 説明Metricとの関係

First Appearance Mentionを`M`とする。

- `explained_same_scene`: `M`にEffective Sufficient Explanationがあればtrue。
- `explanation_delay = explanation.start_cp - M.start_cp`。
- 説明先行は負値可。
- 説明なしTermはDelay観測外だが`explained_same_scene_ratio`分母へ入る。

## 14. Human State

09 `term_registry_state`:

- Manual Term Identity。
- Term `enabled/label/type` Override。
- Manual Alias。
- Inferred Alias最新Confirm/Reject。

09 `metric_effective_state`:

- Effective Term Novelty Correction/Review。
- First Appearance TermMention Explanation Correction/Review。

09 `term_first_appearance`はSection 9を正本とする。

## 15. Test

- Candidate Extractor Registry非依存。
- Candidate Span/Block Persist。
- Resolver Partial Candidate入力。
- Resolver Cache不可。
- Manual Term/Alias。
- Same Label別Term。
- Work Episode跨ぎResolution。
- Novelty Reduce Agreement/Conflict。
- Reference Prefix全Succeeded -> Complete。
- 前方Current Text/Structure欠落 -> Incomplete。
- 前方Resolver Partial -> Incomplete。
- Project Resolver Succeeded -> Complete。
- Project Resolver Partial -> Incomplete。
- Target In-flight Context使用。
- 前方Revision変更でState変更。
- Explanation subject=TermMention。
- 同Scene前方説明/後方説明/説明なし。
- 別Sceneへ探索しない。
- Delay負/正。
- Incomplete時初出依存Metricなし。

## 16. Codex禁止事項

- Term Candidate Span/Block情報を捨てる。
- 解析済みEpisode subsetだけでWork First Appearanceを確定。
- Project Partial ResolverからDocument First Appearanceを確定。
- `occurrence_index`保存。
- Candidate ExtractorへRegistry入力。
- Resolver Cache。
- Stable IdentityへNoveltyを戻す。
- ExplanationをTerm Identity単位で保存。
- Explanation探索を別Sceneへ勝手に拡張。
- Project World/Canonへ自動登録。
