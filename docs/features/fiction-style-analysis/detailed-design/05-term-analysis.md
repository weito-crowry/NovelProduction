# 05 Term Analysis 詳細設計

## 1. 目的

作品固有の用語・固有概念・技術名・制度名などを抽出し、「初出」「繰り返し」「説明された位置」「説明までの距離」を計測可能にする。一般的な固有名詞抽出と、読者にとって新規の作品内概念抽出を区別する。

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

## 3. Termモデル

TermはEntityとは別管理する。

```text
id
reference_work_id nullable
document_id nullable
canonical_label
term_type
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

人物名はTermにしない。組織・場所等はEntityとTermの両方になり得るため、`style_term_entity_links` で関連付ける。

## 4. TermMention

本文中出現を `style_term_mentions` として保持する。

```text
term_id
scene_id
block_id
start_cp
end_cp
surface
occurrence_index
analysis_run_id
```

`occurrence_index` は同document内で1から順番。初出は `occurrence_index=1`。

同一surfaceの単純文字列一致はTerm確定後に決定論的再走査して補完する。ただしsurfaceが一般語でもある場合は誤検出するため `exact_match_safe` flagをTermに持つ。

## 5. 候補抽出

Scene単位のLLM抽出を基本とする。モデルへ以下を渡す。

- Scene本文
- Block ID/span
- 既存Term一覧
- 既存Entity一覧

モデルには「読者が作品固有の意味を学習する必要がある語」を抽出させる。単なる一般名詞、一般的な職業名、通常の動詞・形容詞は除外する。

出力:

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

span validationは04 Mentionと同じ方式を再利用する。

## 6. Term resolution

同一Term統合条件:

- canonical_label完全一致
- confirmed alias一致
- model同一判定 confidence >=0.90

表記揺れ用 `style_term_aliases` を持つ。

例:

```text
統合国家知性機構
国家知性機構
知性機構
```

短縮形が一般語と衝突する場合は `exact_match_safe=false` とし、単純文字列補完を行わない。

## 7. Novelty

Termの読者新規性は以下のenumで保持する。

```text
work_specific
specialized_real_world
common_real_world
uncertain
```

Style metricの `new_term_per_1000_chars` に数えるのは `work_specific` と `specialized_real_world` の初出のみ。`common_real_world` は除外する。

`uncertain` はreview対象で、確定までmetricから除外する。

## 8. 初出

初出はcanonical offset最小のTermMentionで決める。analysis run順やDB insertion順に依存しない。

Work全体でepisode順が確定しているreference workでは、`episode.order_index → start_cp` の順でfirst appearanceを決める。

project draft単体解析ではそのdocument内初出だけを計測し、作品全体初出とは呼ばない。API上のfield名を `first_in_document` とする。

## 9. 説明span

Term説明は `style_annotations` の `term_explanation` として保存する。

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

モデルはTerm初出の前後を解析する。初回windowは初出blockの前2block、後6block。見つからなければ同Scene末尾まで拡張する。別Sceneへ自動拡張しない。

## 10. 説明遅延

`term_explanation_delay` は以下で定義する。

```text
first sufficient explanation start_cp - first mention start_cp
```

同一episode内のみcode point差を計算する。

- 初出より前に十分な説明がある場合は負値を許可。
- sufficient explanationがない場合はNULL。
- partialだけの場合もNULL。

作品横断episode距離をcode pointで連結計算しない。

補助metricとして `term_explained_same_scene_ratio` を持つ。

## 11. 説明の重複

同Termに複数explanation spanを許可する。最初のsufficient explanationがdelay算出対象。

後続の再説明は `repeat_explanation` annotationとして記録可能だが、初期StyleProfile必須metricにはしない。

## 12. Entityとの関連

Termがorganization/location/technology等Entityと同じ実体を表す場合、linkを作る。

```text
term_id
entity_id
confidence
status
```

自動link confidence >=0.90。linkがなくてもTerm分析は成立する。

## 13. Analyzer/version

```text
term-candidate-extractor v1
term-resolver v1
term-explanation-detector v1
```

Term抽出promptには「一般的な日本語を大量に固有用語扱いしない」negative examplesを含める。

## 14. Review条件

ReviewQueueへ送る:

- novelty=uncertain
- resolver confidence <0.90で候補複数
- exact_match_safe判定が0.75未満
- first mention spanがvalidation失敗
- explanation sufficient判定が0.70〜0.849

0.70未満の説明候補はeffective explanationに採用しない。

## 15. テスト

fixtureに以下を含める。

- 初出時に即説明
- 用語→数block後説明
- 説明→後から名称提示
- 同じ略称が一般語と衝突
- 表記揺れ
- 作品固有語と一般語混在
- explanationなし
- episode内複数再説明

metric testではcode point delayを完全一致で検証する。

## 16. Codex実装時の禁止事項

- MeCab/Sudachi等の形態素解析器を勝手に追加しない。
- 大文字小文字・NFKC等でterm表記を破壊しない。
- 一般名詞を頻度だけで作品固有Termへ昇格しない。
- 説明がないTermへ擬似説明を生成しない。
- project world/canon DBへ抽出Termを自動登録しない。
