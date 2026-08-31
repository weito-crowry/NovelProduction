# 05 Term Analysis 詳細設計

## 1. 目的

作品固有の用語・概念・技術名・制度名等を抽出し、初出・説明位置・説明遅延を計測可能にする。Reference作品ではEpisodeを跨いで同じTermを追跡する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  term_models.py
  term_repository.py
  term_service.py
  analyzers/
    term_candidates.py
    term_resolution.py
    term_explanation.py
```

## 3. Term Scope / Stable Identity

Termは `reference_work_id` または `document_id` のexactly one scope。

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

Term Type:

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

人物名はTermにしない。Identity Rowは再解析でUpdateしない。

Effective Correction:

```text
term.enabled         bool, default true
term.canonical_label string
term.term_type       enum
```

Disabled TermはResolver、Exact-match補完、Explanation、Metricから除外。

## 4. Manual Term / Alias

```python
TermService.create_manual_term(
    reference_work_id: int | None,
    document_id: int | None,
    canonical_label: str,
    term_type: str,
) -> Term

TermService.add_manual_alias(term_id: int, alias: str) -> TermAlias
```

- Scope exactly one
- Label/Alias trim後1〜200文字
- Typeはenum
- Same Label別Termを許容
- Same Term/Alias Manual追加はIdempotent
- Manual Rowは `origin=manual`, Run NULL

Manual作成で09 `term_registry` Stateが変わるが、Work全体を即時自動再解析しない。

## 5. Candidate ExtractorはRegistry非依存

入力はScene Text + Block ID/spanだけ。既存Term/Entity Registryを渡さない。

出力:

```json
{
  "terms": [{
    "surface": "統合国家知性機構",
    "block_id": 4,
    "start_in_block": 8,
    "end_in_block": 17,
    "canonical_label_candidate": "統合国家知性機構",
    "term_type_candidate": "institution",
    "novelty_candidate": "work_specific",
    "exact_match_safe_candidate": true,
    "confidence": 0.94
  }]
}
```

Persistは `term_candidate` Annotation。Candidate ExtractorはTerm Identity/TermMentionを作らない。

## 6. Term Resolver

Candidate Runに依存しCurrent Enabled Term Registryを読む。09で `cacheable=false`。Registry Input Fingerprintを保存する。

Auto Resolution:

1. Effective Canonical Label完全一致。ただし複数候補なら選ばない。
2. Confirmed/Manual Alias完全一致。ただし複数候補なら選ばない。
3. Model同一判定 >= `term_resolution_auto_merge`。

必要なら新 `origin=inferred` Term/Aliasを作る。既存IdentityはUpdateしない。

Resolved Candidateごとに:

```text
style_term_mentions:
  term_id
  structure_revision_id
  scene_id
  block_id
  start_cp/end_cp
  surface
  analysis_run_id
```

Occurrence Indexは保存しない。

## 7. Term-level Attribute Reduction

同じTermへ1Run中に複数Candidateが解決されるため、1 Resolver Run × 1 Termにつき:

```text
term.novelty 最大1 Annotation
term.exact_match_safe 最大1 Annotation
```

### Novelty

```text
work_specific
specialized_real_world
common_real_world
uncertain
```

- `uncertain` を除く具体値が1種類だけ -> その値
- 具体値が複数競合 -> uncertain
- 全Candidate uncertain -> uncertain

Confidenceは採用判断に含まれたCandidate Confidenceの最小値。

### Exact Match

- 1件でもfalse -> false
- 全件true -> true

Confidenceは全Candidate Confidenceの最小値。

Repository/Serviceで同Run/Term/Attribute重複Insertを拒否する。

## 8. Work Registry整合モデル

Reference Work RegistryはIncremental。

- Work一括解析はEpisode Order順
- Resolver Cache不可
- 後続EpisodeでRegistry成長しても前Episodeを即時自動再解析しない
- Work再解析時に全Episode Resolverを再実行
- RunへRegistry Input Fingerprint保存

## 9. Alias

Inferred AliasだけではAuto Resolution根拠にしない。Confirmed Inferred AliasまたはManual Aliasだけを使う。

## 10. Effective Novelty / Exact Match

Enabled Termだけ対象。

Novelty:

```text
ManualOverride > Confirmed Current Resolver > Current Resolver > uncertain
```

Exact Match:

```text
ManualOverride > Confirmed Current Resolver > Current Resolver > false
```

Effective `exact_match_safe=true` のTermだけ決定論的Surface補完可能。補完MentionはCurrent Resolver Run所属。

## 11. First Appearance

Reference Workでは、各Episodeについて:

1. Episodeに属するStyleDocumentを取得
2. `document.current_text_revision_id` を取得
3. `document.current_structure_revision_id` がCurrent Text所属か確認
4. 09 Current Term Resolver Runを解決
5. そのRunのEffective TermMentionを使用

全EpisodeのMentionを:

```text
reference_episode.order_index -> start_cp
```

でSortして最初をFirst Appearanceとする。

Current Text/Structure/Resolver RunがないEpisodeは対象外としCoverageへ反映する。旧Revision/RunへFallbackしない。

Project Documentは指定Current Structure/Current Resolver Runの `start_cp` 最小。

## 12. Term Explanation

`term-explanation-detector` はTerm Resolverに依存しEnabled Current TermMentionだけを対象とする。

```text
annotation_type = term_explanation
subject_type = term
subject_id = term_id
start_cp/end_cp
confidence
analysis_run_id
value_json = {block_id, explanation_kind, completeness}
```

Kind:

```text
definition | paraphrase | example | contextual_clue | contrast | other
```

Completeness `partial|sufficient`。

Window: 初出Block前2/後6、見つからなければ同Scene末尾まで。

Effective Sufficient Explanation:

1. ManualOverride Annotation ID
2. Clear -> Explicit None
3. Confirmed Current
4. Current Explanation RunのSufficient + Policy以上の本文順最初
5. None

## 13. Explanation Delay

同一Episode内:

```text
first sufficient explanation start_cp - first mention start_cp
```

説明先行は負値可。説明なし/別EpisodeはNULL。

## 14. Entity Link / Human State

Term-Entity Linkは双方Enabled + Scope一致。v1 Manual Linkでよい。

`term_registry` State:

- Manual Term Identity
- Active enabled/label/type Override
- Manual Alias
- Inferred Alias最新Review

Inferred Registry全量はResolver Registry Input Fingerprintへ保存する。

## 15. Review / Test

Low-confidenceだけでReviewItemを作らない。UIからManual Term/Alias、Disable、Label/Type、Novelty/Exact Match、Explanation、Alias Reviewを直接操作可能。

Test:

- Candidate Extractor Registry非依存
- Resolver Cache不可/Registry Fingerprint
- Work Episode跨ぎTerm
- Manual Term/Alias
- Disabled Term
- Novelty Reduction一致/Conflict
- Exact Match All True/One False
- Run×Term×Attribute重複拒否
- Alias Resolution
- First AppearanceはDocument Current Text/Structure/Runのみ
- Explanation/Delay
- Work Episode Order

## 16. Codex禁止事項

- Candidate ExtractorへRegistry入力
- Candidate ExtractorからIdentity作成
- Resolver Cache
- Identity Update
- CandidateごとにTerm-level Attribute重複保存
- Occurrence Index保存
- Old Revision/RunへFirst Appearance Fallback
- Inferred AliasだけでAuto Merge
- Authoring World/CanonへManual Term自動反映
