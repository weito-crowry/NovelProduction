# 03 Structure Segmentation 詳細設計

## 1. 目的

Canonical Textを、後段の意味解析・文体計測が参照できる安定構造へ分解する。本文文字列は変更せず、Scene境界の改善は新しい `StructureRevision` として表現する。

上位仕様は `../basic-design.md`。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  structure_models.py
  segmentation.py
  sentence_splitter.py
  structure_repository.py
  structure_service.py
```

## 3. StructureRevision

```text
id
text_revision_id
revision_no
segmenter_id
segmenter_version
source_kind = automatic | semantic | manual
parent_structure_revision_id nullable
fingerprint
created_at
```

- `automatic`: 決定論的parserによるbase構造。
- `semantic`: 06/09のScene Boundary Analyzer結果をmaterializeした構造。
- `manual`: ユーザーsplit/mergeを反映した構造。

既存revisionはupdateしない。semantic/manual revisionはparentを必ず持つ。

semantic revisionの生成元AnalysisRunは12の `style_structure_analysis_sources` で1対1に記録する。StructureRevision自身へ循環FKを追加しない。

## 4. Fingerprint

### automatic

```text
hash(
  text_revision.canonical_sha256,
  segmenter_id,
  segmenter_version,
  deterministic config
)
```

### semantic

```text
hash(
  parent_structure.fingerprint,
  boundary_analysis_run.fingerprint,
  sorted(applied_after_block_ids),
  policy_version
)
```

confidence値そのものはStructure形状を変えないためfingerprintへ入れない。適用されたBlock境界集合を正本とする。

### manual

```text
hash(
  parent_structure.fingerprint,
  operation,
  operation arguments
)
```

splitなら `after_block_id`、mergeならleft/right scene IDsをoperation argumentsへ含める。

## 5. 階層

```text
TextRevision
  └─ StructureRevision
      ├─ Scene
      │   └─ Block
      │       └─ Sentence
      └─ Scene外Separator Block
```

すべてCanonical Textの `[start_cp,end_cp)` spanを持つ。

### order_index

- `Scene.order_index`: StructureRevision内1..N。
- `Block.order_index`: **StructureRevision全体**で本文順1..N。
- `Block.paragraph_index`: StructureRevision全体で元paragraph順1..N。同paragraphを複数Blockへ分割しても同値。
- `Sentence.order_index`: Block内1..N。

## 6. Block type

```text
dialogue
narration
monologue
heading
separator
unknown
```

`action / description / exposition / psychology / transition` は06 semantic annotation。

Blockは原則paragraph単位。ただし同paragraph中に明確な会話括弧と地の文が混在する場合は分割する。

## 7. Quote scanner

stack based scanner。

主会話括弧: `「 」`。
補助括弧: `『 』`, `（ ）`, `( )`。

- `「...」` はdialogue候補。
- `『...』` 単独は会話と断定しない。
- `（...）` を自動monologueにしない。
- unmatched `「` はparagraph末までdialogue候補 + warning。
- nested quoteは外側を1dialogue Block。
- multiline dialogueは閉じ括弧まで1Block可。

## 8. Monologue

source metadataで明示された場合だけ `monologue`。その他はnarrationとして構造化し、06 `psychology` へ渡す。

## 9. Heading

- adapter heading hint
- 独立行40 code points以下かつ `第...章/話/節` 等pattern
- 数字/漢数字 + 短いtitleの明確な形式

短い文というだけではheadingにしない。

## 10. Separator

初期pattern:

```text
***
＊＊＊＊＊
＊ ＊ ＊
---
――――
◇
◆
◇◇◇
◆◆◆
†
```

独立paragraph、記号中心、32 code points以下。adapter hintがあればpattern外も可。

## 11. Sentence split

終端: `。！？!?`。
終端後の `」』）)]】` は同Sentence。
`……` / `――` は単独終端にしない。

残り文字列も最後のSentenceとする。

## 12. Automatic Scene

base `automatic` revisionでは明示境界のみ。

1. separator Block
2. adapter scene-break hint
3. 本文途中heading

明示境界なしならepisode全体1 Sceneでよい。Semantic Boundary Analyzerの安定入力用baseであり、最終粒度ではない。

separatorは `scene_id=NULL`。

## 13. Scene Boundary Candidate契約

06 `scene-boundary-detector` の出力は `style_annotations` へ次の形で保存する。

```text
annotation_type = scene_boundary_candidate
subject_type = block
subject_id = after_block_id
analysis_run_id = boundary run
confidence = candidate confidence
value_json = {
  "base_structure_revision_id": 7,
  "reasons": ["time_shift", "location_shift"]
}
```

candidateの `subject_id` は「このBlockの直後で切る」という意味。任意offsetは受けない。

## 14. Semantic Scene materialization

09 `AnalysisPolicy.scene_boundary_auto_apply` 以上のcandidateだけを対象に新 `semantic` StructureRevisionを作る。

materialize手順:

1. boundary AnalysisRunがbase StructureRevisionを入力にしていることを検証。
2. 同Runの `scene_boundary_candidate` annotationだけを読む。
3. threshold以上の `after_block_id` を抽出。
4. 存在しないBlock、既存明示境界と重なるcandidateを除外しwarning。
5. Block IDを本文順にsort・dedupe。
6. 1件以上新規境界があればsemantic revision生成。
7. `style_structure_analysis_sources` へ `(new_structure_revision_id, boundary_analysis_run_id)` を保存。
8. applied Block IDsをfingerprintへ含める。
9. shapeがbaseと同一ならsemantic revisionを作らずbaseをreuse。

LLMはStructure rowを直接書き込まない。

`scene_boundary_candidate_min` 以上/auto apply未満はproposalとして残る。ReviewQueueへの自動投入はしない。

## 15. Scene最小条件

- analyzable Block >=1。
- empty Sceneなし。
- 連続separatorは1境界。
- headingだけのSceneは作らず次Scene先頭。

## 16. Manual split/merge

現在のeffective StructureRevisionをparentに新 `manual` revisionを作る。

### split

- Block境界だけ。
- `after_block_id` 指定。

### merge

- 隣接Sceneだけ。
- 間separatorはBlockとして残す。
- merged Scene spanはseparatorを跨いでよい。

Manual revisionを明示してfull analysisした場合、09はScene Boundary Analyzerを再適用しない。

## 17. Warning

```text
unclosed_dialogue_quote
unmatched_closing_quote
ambiguous_heading
empty_paragraph_hint
mapping_boundary_mismatch
semantic_boundary_invalid
```

warningは診断情報。全件ReviewItemへ送らない。

## 18. Validation

- Scene order 1..N。
- Block global order 1..N。
- Sentence order Block内1..N。
- span `start < end`。
- Canonical Text長内。
- sibling Block非重複。
- Block/Sentence text == canonical slice。
- Scene所属Block spanはScene span内。
- semantic source linkのAnalysisRunは `scene-boundary-detector` かつparent StructureRevision入力。

不一致は `STRUCTURE_INVARIANT_ERROR` でrollback。

## 19. Version

```text
segmenter_id = japanese-fiction-structure
segmenter_version = 1
```

quote/heading/separator/sentence rule変更はversion更新。Boundary threshold変更はAnalysisPolicy versionで表現する。

## 20. Test

- narration/dialogue混在
- nested/unmatched/multiline quote
- separator/heading
- sentence終端/emoji offset
- Block global order + scene_id NULL
- candidate Annotation contract
- semantic source AnalysisRun link
- semantic fingerprint applied IDs依存
- threshold以上materialize
- threshold未満proposal
- manual split/merge
- manual full analysisでBoundary skip
- revision不変性

## 21. Codex禁止事項

- LLMから任意character offsetでSceneを切らない。
- Block typeへsemantic分類を混ぜない。
- parent StructureRevisionをupdateしない。
- `start/end` を本文検索で後付け推定しない。
- boundary proposalを全件ReviewItem化しない。
- semantic Structureの生成元AnalysisRun provenanceを省略しない。