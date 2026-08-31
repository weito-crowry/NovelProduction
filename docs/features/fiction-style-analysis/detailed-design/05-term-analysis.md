# 05 Term Analysis 詳細設計

## 1. 目的

作品固有の用語・概念・技術名・制度名等を抽出し、「初出」「説明された位置」「説明までの距離」を計測可能にする。Reference作品ではEpisodeを跨いで同じTermを追跡する。

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

## 3. Term Scope / Identity

Termは次のどちらか一方へ所属する。

```text
reference_work_id  # Reference作品全Episode共通
document_id        # Project Draft等の単独Document
```

Term RowはStable Identity。

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

人物名はTermにしない。

Effective Correction Field:

```text
term.enabled         bool, default true
term.canonical_label string
term.term_type       enum
```

10 ManualOverrideで修正する。Disabled TermはResolver/Exact-match補完/Term Metricから除外する。

## 4. Term Candidate ExtractorはRegistry非依存

`term-candidate-extractor` はCache可能なDocument Analyzerとし、**既存Term RegistryやEntity Registryを入力にしない。**

入力:

- Scene Text
- Block ID/span

出力例:

```json
{
  "terms": [
    {
      "surface": "統合国家知性機構",
      "block_id": 4,
      "start_in_block": 8,
      "end_in_block": 17,
      "canonical_label_candidate": "統合国家知性機構",
      "term_type_candidate": "institution",
      "novelty_candidate": "work_specific",
      "exact_match_safe_candidate": true,
      "confidence": 0.94
    }
  ]
}
```

Persistは `style_annotations`:

```text
annotation_type = term_candidate
subject_type = block
subject_id = block_id
start_cp/end_cp = candidate surface span
value_json = {
  "surface": "...",
  "canonical_label_candidate": "...",
  "term_type_candidate": "...",
  "novelty_candidate": "...",
  "exact_match_safe_candidate": true
}
confidence
analysis_run_id = term-candidate-extractor run
```

Candidate ExtractorはTerm Identity/TermMentionを作らない。

Span Validationは04共通Utility。

## 5. Term Resolver

`term-resolver` はTerm Candidate Runに依存し、Current Term Registryを読む。

Reference:

```text
同 reference_work_id のEnabled Term Registry
```

Project:

```text
同 document_id のEnabled Term Registry
```

Resolverは09で `cacheable=false`。Full AnalysisごとにCurrent Registryを読む。

入力Registryは09 `registry_input_fingerprint` に記録する。

自動統合条件:

1. Enabled TermのEffective Canonical Label完全一致。ただし同名Enabled Termが複数なら自動選択しない
2. Confirmed/Manual Alias一致。ただし候補複数なら自動選択しない
3. Model同一判定 >= `AnalysisPolicy.term_resolution_auto_merge`

初期0.90。

Disabled Termは候補にしない。

## 6. Resolver Output

Resolverは必要に応じてTerm Identity/Aliasを作成し、各Candidateについて `style_term_mentions` を作る。

```text
id
term_id
structure_revision_id
scene_id
block_id
start_cp
end_cp
surface
analysis_run_id = term-resolver run
```

`occurrence_index` は持たない。

同じRunでEffective推論属性Annotationを作る。

### Novelty

```text
annotation_type = term.novelty
subject_type = term
subject_id = term_id
value_json = {"value": "work_specific"}
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

### Exact Match Safety

```text
annotation_type = term.exact_match_safe
subject_type = term
subject_id = term_id
value_json = {"value": true}
confidence
analysis_run_id = term-resolver run
```

既存Termへ解決してもIdentity RowはUpdateしない。

## 7. Work Registryのv1整合モデル

Reference Work Term RegistryはIncremental Stable Registry。

- Work全体解析JobはEpisode Order順にResolverを実行
- ResolverはCache不可
- 後続Episodeで新しいInferred Termが追加されても過去Episodeを自動全再解析しない
- Work全体解析を再実行すれば全EpisodeをOrder順に再Resolver
- 各Runに `registry_input_fingerprint` を残す

全Episode更新ごとに自動全再解析する仕組みはv1で作らない。

Manual/Confirmed Correctionは09 State Fingerprint対象。

## 8. Alias

```text
style_term_aliases
  id
  term_id
  alias
  origin = inferred | manual
  analysis_run_id nullable
  created_at
```

- Inferred AliasだけではAuto Mergeしない
- Confirmed Inference ReviewまたはManual AliasだけをResolution根拠に使う
- Alias専用Disable機構はv1不要

## 9. Effective Novelty / Exact Match

Enabled Termだけ対象。

Novelty:

```text
ManualOverride
> Confirmed Current Resolver Inference
> Current Resolver Inference
> uncertain
```

Exact Match:

```text
ManualOverride
> Confirmed Current Resolver Inference
> Current Resolver Inference
> false
```

Unknown状態でSurface補完しない。

Effective `term.exact_match_safe=true` のTermだけ決定論的Surface補完を許可する。補完で作るTermMentionも、その補完を実行したCurrent `term-resolver` Run IDに所属させる。

## 10. 初出

### Reference Work

各ReferenceEpisodeのCurrent Text/Current Effective Structureに属するCurrent Term Resolver RunのTermMentionを:

```text
reference_episode.order_index
-> start_cp
```

でSortして最初をFirst Appearanceとする。

### Project Document

指定Current Structure内のCurrent Resolver Runで `start_cp` 最小。

旧Structure/旧Resolver Runを混ぜない。

## 11. Term Explanation

`term-explanation-detector` は `term-resolver` に依存する。

Enabled TermのCurrent TermMentionだけを対象にする。

```text
annotation_type = term_explanation
subject_type = term
subject_id = term_id
start_cp/end_cp = explanation span
confidence
analysis_run_id
value_json = {
  "block_id": 22,
  "explanation_kind": "definition",
  "completeness": "sufficient"
}
```

Kind:

```text
definition
paraphrase
example
contextual_clue
contrast
other
```

Completeness: `partial | sufficient`。

初回Windowは初出Block前2/後6。見つからなければ同Scene末尾。別Sceneへ自動拡張しない。

## 12. Effective Sufficient Explanation

Enabled Termだけ対象。

1. ManualOverride `term.sufficient_explanation_annotation_id`
2. Clear Override -> Explicit None
3. Confirmed Current Sufficient Explanation
4. Current Explanation Runの `sufficient` + Confidence >= Policy の本文順最初
5. それ以外なし

Override Annotationは同TermかつCurrent Text/Structure LineageをServiceでValidation。

## 13. 説明遅延

```text
first sufficient explanation start_cp - first mention start_cp
```

同一Episodeのみ。

- 説明先行: 負値可
- Sufficientなし/別Episode: NULL

## 14. Entity Link

```text
term_id
entity_id
origin = inferred | manual
confidence nullable
analysis_run_id nullable
created_at
```

双方EnabledかつScope一致がEffective条件。

v1はManual Linkだけでよい。Term Candidate ExtractorへEntity一覧を入力しない。

## 15. Human State Dependency

09 `term_registry` State Fingerprint:

- Manual Term Identity
- Active `term.enabled/label/type` Override
- Manual Alias
- Inferred Alias最新Confirm/Reject

Inferred Term Registry自体はCurrent Validity Stateには入れず、Resolver `registry_input_fingerprint` に記録する。

`term-explanation-detector` は `term_registry` StateをCurrent判定に使う。

`style-metrics-semantic` は10のEffective Semantic Stateを別途Fingerprintへ含める。

## 16. Analyzer / Version

```text
term-candidate-extractor v1
term-resolver v1
term-explanation-detector v1
```

Promptには一般語過剰抽出Negative Example。

## 17. AnalysisPolicy

```text
term_resolution_auto_merge = 0.90
term_entity_auto_link = 0.90
term_explanation_effective = 0.85
```

09が正本。

## 18. Review方針

Unknown/Uncertainだけを理由にReviewItemを作らない。

Semantics/Term画面から:

- Term Disable
- Label/Type修正
- Novelty/Exact Match修正
- Sufficient Explanation指定
- Alias Confirm/Reject

をDirect操作可能。

## 19. Test

- Candidate ExtractorがTerm/Entity Registry非依存
- CandidateはAnnotation、Identity/TermMentionを作らない
- Resolver `cacheable=false`
- Registry Input Fingerprint
- Reference Work Episode跨ぎTerm統合
- 同名Enabled Term複数で強制選択なし
- Term Identity再解析Updateなし
- Disabled Term除外
- Label/Type Override
- Novelty/Exact Match Run Annotation
- Inferred AliasだけではAuto Mergeなし
- Confirmed/Manual Alias Resolution
- 初出/説明/説明遅延
- Refresh/Order変更でOccurrence Index依存なし
- Current Resolver Runだけから初出算出
- Work全体解析Episode Order

## 20. Codex禁止事項

- Term Candidate Extractorへ既存Term/Entity Registryを入力
- Candidate ExtractorからTerm Identityを作成
- Term ResolverをCache Hitで省略
- Term Identity Rowを再解析でUpdate
- Novelty/ExactMatchSafeをIdentity Columnへ戻す
- Disabled TermをResolver/Metricへ含める
- Occurrence Indexを保存
- Inferred AliasだけでAuto Merge
- MeCab/Sudachiを勝手に追加
- Project World/Canonへ自動登録
