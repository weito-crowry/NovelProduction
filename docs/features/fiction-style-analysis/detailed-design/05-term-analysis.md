# 05 Term Analysis 詳細設計

## 1. 目的

作品固有の用語・概念・技術名・制度名等を抽出し、「初出」「説明された位置」「説明までの距離」を計測可能にする。人物名抽出とは分離する。

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

## 3. Term scope

TermもEntityと同様に次のどちらか一方へ所属する。

```text
reference_work_id  # reference作品全episode共通
document_id        # project draft等の単独document
```

両方NULL/両方非NULLは禁止する。

reference作品ではepisodeを跨いで同じ用語を1 Termとして扱う。

## 4. Termモデル

```text
id
reference_work_id nullable
document_id nullable
canonical_label
term_type
novelty
exact_match_safe
status
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

人物名はTermにしない。Entityと同一実体を指す場合は `style_term_entity_links` で関連付ける。

## 5. TermMention

本文中出現:

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

`occurrence_index` は永続化しない。refreshやepisode挿入で番号がstaleになるためである。初出・N回目はcurrent effective revision群を `episode.order_index, start_cp` でsortして都度算出する。

同一surfaceの決定論的補完は `exact_match_safe=true` のTermだけ行う。

## 6. 候補抽出

Scene単位でモデルへ渡す。

- Scene text
- Block ID/span
- 同scopeの既存Term
- Entity一覧

「読者が作品内で意味を学習する必要がある語」を候補化し、通常の一般名詞を大量抽出しない。

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

span validationは04と同じutilityを使う。

## 7. Term resolution

自動統合条件:

- canonical_label完全一致
- confirmed/manual alias一致
- model同一判定 >= `AnalysisPolicy.term_resolution_auto_merge`

初期default `0.90`。

表記揺れは `style_term_aliases` へ保存する。

短縮形が一般語と衝突する場合 `exact_match_safe=false`。

## 8. Novelty

```text
work_specific
specialized_real_world
common_real_world
uncertain
```

`term.new_per_1000_chars` に数えるのは `work_specific` と `specialized_real_world`。

`uncertain` はeffective metricから除外するが、ReviewItemを必須生成しない。Term一覧のfilterから人手確認できる。

## 9. 初出

### reference work

current effective TextRevisionを対象に:

```text
reference_episode.order_index
-> mention.start_cp
```

の最小値をfirst appearanceとする。

### project document

同document内の `start_cp` 最小Mention。API fieldは `first_in_document`。

DB insertion順・AnalysisRun順には依存しない。

## 10. 説明Annotation

Term説明は `style_annotations` の `term_explanation`。

```json
{
  "term_id": 42,
  "explanation_kind": "definition",
  "completeness": "partial"
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

`completeness`:

```text
partial
sufficient
```

初回windowは初出Blockの前2Block・後6Block。見つからなければ同Scene末尾まで拡張する。別Sceneは自動拡張しない。

## 11. 説明遅延

```text
first sufficient explanation start_cp - first mention start_cp
```

同一episode内だけcode point差を計算する。

- 説明が名称より先なら負値可。
- sufficientなしはNULL。
- partialだけもNULL。

補助metric `term.explained_same_scene_ratio` を持つ。

## 12. 説明重複

1 Termに複数説明spanを許可。最初のsufficientだけdelay対象。

後続再説明は保存可能だがv1必須metricにはしない。

## 13. Entity link

TermとEntityが同じ実体ならlink可能。

```text
term_id
entity_id
confidence
status
```

scopeが異なるEntity/Termはlink不可。auto link thresholdは09 AnalysisPolicy `term_entity_auto_link`、初期0.90。

## 14. Analyzer/version

```text
term-candidate-extractor v1
term-resolver v1
term-explanation-detector v1
```

Promptには一般語を過剰抽出しないnegative exampleを含める。

## 15. Confidence policy

閾値の正本は09 AnalysisPolicy。

初期default:

```text
term_resolution_auto_merge = 0.90
term_entity_auto_link = 0.90
term_explanation_effective = 0.85
```

threshold未満はraw推論として保持し、無理にeffective化しない。低confidenceごとのReviewItem自動生成はしない。

## 16. テスト

- reference work episode跨ぎTerm統合
- project document scope分離
- 初出即説明
- 数Block後説明
- 説明→名称
- 略称と一般語衝突
- 表記揺れ
- explanationなし
- refresh/episode order変更後もfirst appearanceがstale indexに依存しない
- code point delay

## 17. Codex実装時の禁止事項

- MeCab/Sudachi等を勝手に追加しない。
- NFKC等で表記を破壊しない。
- 頻度だけで一般語をTermへ昇格しない。
- 説明がないTermへ擬似説明を生成しない。
- project world/canonへ自動登録しない。
- occurrence_indexのようなrefreshでstaleになる派生順序を保存しない。