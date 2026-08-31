# 05 Term Analysis 詳細設計

## 1. 目的

作品固有の用語・概念・技術名・制度名等を抽出し、「初出」「説明された位置」「説明までの距離」を計測可能にする。人物名抽出とは分離し、reference作品ではepisodeを跨いで同じTermを追跡する。

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

## 3. Term scope / identity

Termは次のどちらか一方へ所属する。

```text
reference_work_id  # reference作品全episode共通
document_id        # project draft等の単独document
```

Term rowはstable identityであり、再解析のたびに推論属性を上書きしない。

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

## 4. 推論属性はAnnotation

`novelty` と `exact_match_safe` はTerm identityではなくAnalyzer出力なので `style_annotations` に保存する。

### novelty

```text
annotation_type = term.novelty
subject_type = term
subject_id = term_id
value_json = {"value": "work_specific"}
confidence
analysis_run_id
```

value:

```text
work_specific
specialized_real_world
common_real_world
uncertain
```

### exact match safety

```text
annotation_type = term.exact_match_safe
subject_type = term
subject_id = term_id
value_json = {"value": true}
confidence
analysis_run_id
```

Effective Viewは10のManualOverride/confirmed/latest eligible inference順で解決する。再解析で旧Annotationをupdateしない。

## 5. TermMention

```text
id
term_id
scene_id
block_id
start_cp
end_cp
surface
analysis_run_id
```

`occurrence_index` は保存しない。初出/N回目はcurrent effective StructureRevision群のMentionを `episode.order_index, start_cp` でsortして計算する。

同一surfaceの決定論的補完はeffective `term.exact_match_safe=true` のTermだけ行う。

## 6. 候補抽出

Scene単位でモデルへ渡す。

- Scene text
- Block ID/span
- 同scopeの既存Term + effective label/alias
- Entity一覧

出力例:

```json
{
  "terms": [
    {
      "surface": "統合国家知性機構",
      "block_id": 4,
      "start_in_block": 8,
      "end_in_block": 17,
      "canonical_label": "統合国家知性機構",
      "term_type": "institution",
      "novelty": "work_specific",
      "exact_match_safe": true,
      "confidence": 0.94
    }
  ]
}
```

新Term作成時はidentity row + 同じrun由来のnovelty/exact-match Annotationを作る。既存Termへ解決した場合は新しいAnnotationを追加し、Term rowを更新しない。

span validationは04共通utility。

## 7. Term resolution

自動統合:

- effective canonical label完全一致
- confirmed/manual alias一致
- model同一判定 >= `AnalysisPolicy.term_resolution_auto_merge`

初期0.90。

短縮形が一般語と衝突する場合、effective `exact_match_safe=false` とする。

## 8. Alias

`style_term_aliases`:

```text
id
term_id
alias
origin = inferred | manual
analysis_run_id nullable
created_at
```

自動aliasは生成runを記録する。再解析で既存aliasをupdateしない。

## 9. NoveltyとMetric

`term.new_per_1000_chars` のeligible:

```text
work_specific
specialized_real_world
```

`common_real_world` / `uncertain` は除外。

unknown/uncertainを理由にReviewItemを自動生成しない。Semantics/Term画面でfilter可能にする。

## 10. 初出

### reference work

各ReferenceEpisodeのcurrent effective StructureRevisionに属するeffective TermMentionを:

```text
reference_episode.order_index
-> start_cp
```

でsortし最初をfirst appearanceとする。

### project document

current StructureRevision内 `start_cp` 最小Mention。API fieldは `first_in_document`。

旧StructureRevision/旧AnalysisRun由来Mentionを混ぜない。

## 11. Term Explanation Annotation

説明候補はTermをsubjectにする。

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

`explanation_kind`:

```text
definition
paraphrase
example
contextual_clue
contrast
other
```

`completeness`: `partial | sufficient`。

初回windowは初出Blockの前2/後6。見つからなければ同Scene末尾まで。別Sceneへ自動拡張しない。

## 12. Effective sufficient explanation

Termごとの「Lint/Metricで使うsufficient explanation」は次で決める。

1. ManualOverride `term.sufficient_explanation_annotation_id` があればそのAnnotation。
2. clear overrideならなし。
3. confirmed sufficient explanation。
4. current effective runの `completeness=sufficient` かつ confidence >= `term_explanation_effective` のうち本文順最初。
5. それ以外なし。

ManualOverrideが指定するAnnotation IDは:

- `annotation_type=term_explanation`
- 同Term subject
- current effective Text/Structure lineageに属する

ことをserviceで検証する。

## 13. 説明遅延

```text
first sufficient explanation start_cp - first mention start_cp
```

同一episode内だけcode point差。

- 説明先行は負値可。
- sufficientなし/別episodeならNULL。

補助Metric `term.explained_same_scene_ratio`。

## 14. Entity link

```text
id
term_id
entity_id
origin = inferred | manual
confidence nullable
analysis_run_id nullable
created_at
```

scope一致必須。将来自動linkする場合threshold `term_entity_auto_link` 初期0.90、run provenance必須。v1はmanual linkだけでも要件を満たす。

## 15. Analyzer/version

```text
term-candidate-extractor v1
term-resolver v1
term-explanation-detector v1
```

Promptには一般語過剰抽出のnegative example。

## 16. AnalysisPolicy

```text
term_resolution_auto_merge = 0.90
term_entity_auto_link = 0.90
term_explanation_effective = 0.85
```

09が正本。

## 17. Test

- reference work episode跨ぎTerm統合
- Term identity再解析で不変
- novelty/exact-match per-run Annotation
- alias provenance
- project scope分離
- 初出即説明/数Block後/説明先行/説明なし
- abbreviation一般語衝突
- refresh/order変更でfirst appearance staleなし
- current Structureだけから初出算出
- sufficient explanation override set/clear
- override annotation lineage validation
- code point delay

## 18. Codex禁止事項

- Term identity rowへnovelty/exact_match_safeを戻さない。
- occurrence_indexを保存しない。
- MeCab/Sudachiを勝手に追加しない。
- NFKC等で表記破壊しない。
- 頻度だけで一般語をTerm昇格しない。
- 擬似説明生成しない。
- project world/canonへ自動登録しない。
- Term推論属性を再解析でupdateしない。