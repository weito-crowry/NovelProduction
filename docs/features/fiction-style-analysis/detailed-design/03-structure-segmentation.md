# 03 Structure Segmentation 詳細設計

## 1. 目的

Canonical Textを後段解析が参照できる安定構造へ分解する。本文文字列は変更せず、Automatic/Semantic/Manualの差は `StructureRevision` として履歴化する。

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

- Automatic: 決定論的Base構造
- Semantic: Boundary Analyzer結果をMaterialize
- Manual: User Split/Merge

既存RevisionはUpdateしない。Semantic/ManualはParent必須。Semantic生成元AnalysisRunは12 `style_structure_analysis_sources` で追跡する。

## 4. Current Structure Pointer

各 `style_documents` は `current_structure_revision_id nullable` を持つ。これは「Corpus集約や通常表示で現在採用するStructure」を明示するPointerであり、Latest RevisionをQueryで推測しない。

Pointer更新規則:

1. 新TextRevision作成時: `current_structure_revision_id=NULL`。
2. `analyze` でStructure未指定:
   - Deterministic: Final Automatic RevisionをCurrentに設定。
   - Full: Semantic境界が適用されればSemantic、適用なしならAutomaticをCurrentに設定。
3. `analyze` でStructureを明示指定: 解析対象として使うだけでCurrent Pointerは変更しない。
4. Current StructureからManual Split/Merge: 新Manual RevisionをCurrentに設定。
5. Userが既存Revisionを明示選択する `select current structure` 操作: 同DocumentのCurrent TextRevisionに属するRevisionだけ設定可能。
6. Reference Refresh / Project Draft CaptureでCurrent Textが変わった場合: Current StructureをNULLへClear。

Current PointerはLogical FKとして12/Serviceで所属整合を検証する。

## 5. Fingerprint

Automatic:

```text
hash(canonical_sha256, segmenter_id, segmenter_version, config)
```

Semantic:

```text
hash(parent fingerprint, boundary run fingerprint, sorted applied_after_block_ids, policy_version)
```

Manual:

```text
hash(parent fingerprint, operation, operation args)
```

## 6. 階層 / Order

```text
TextRevision
 -> StructureRevision
    -> Scene
       -> Block
          -> Sentence
```

- Scene Order: Revision内1..N
- Block Order: Revision全体Global 1..N
- Paragraph Index: Revision全体の元Paragraph順
- Sentence Order: Block内1..N
- 全SpanはCanonical `[start_cp,end_cp)`

## 7. Block Type

```text
dialogue
narration
monologue
heading
separator
unknown
```

Action/Description/Exposition/Psychology/Transitionは06 Semantic Annotation。

`「...」` はDialogue候補。Nested Quoteは外側を1Block。Unmatched QuoteはWarning付きで継続する。`『』` や括弧だけでDialogue/Monologueを断定しない。

## 8. Heading / Separator / Sentence

HeadingはAdapter Hintまたは明確な短い章節Pattern。短い文だけではHeadingにしない。

Separatorは独立した記号中心Paragraphを認識し `scene_id=NULL` で保持可能。

Sentence終端は `。！？!?`。終端直後の閉じ括弧を同Sentenceに含める。

## 9. Automatic Scene

Automatic Revisionでは明示境界だけを使う。

1. Separator
2. Adapter Scene-break Hint
3. 本文途中Heading

明示境界がなければEpisode全体1 Sceneでよい。

## 10. Scene Boundary Candidate

06 `scene-boundary-detector` はAutomatic Base Scene内のBlock境界だけを返す。

```text
annotation_type = scene_boundary_candidate
subject_type = block
subject_id = after_block_id
analysis_run_id = boundary run
confidence
value_json = {base_structure_revision_id, reasons}
```

任意Character Offsetは受けない。

## 11. Semantic Materialization

09 AnalysisPolicy `scene_boundary_auto_apply` 以上のCandidateだけを適用する。

1. Boundary RunがBase Automatic Revision入力か検証
2. 同RunのCandidateのみ読む
3. Threshold以上Block IDをSort/Dedupe
4. Invalid/既存境界重複を除外
5. 新規境界があればSemantic Revision生成
6. `style_structure_analysis_sources` へ生成元Run Link
7. Shape同一ならBaseをReuse

Materialize後、Structure未指定Full AnalysisならFinal RevisionをCurrent Pointerへ設定する。

## 12. Manual Split / Merge / Select

Split:

- Block境界だけ
- `after_block_id`
- Current StructureをParentに新Manual Revision

Merge:

- 隣接Sceneだけ
- Current StructureをParentに新Manual Revision

成功時は新Manual RevisionをCurrent Pointerへ設定する。

Select Current:

- Existing StructureRevision IDを指定
- 同DocumentかつDocumentのCurrent TextRevisionに所属すること
- Structure内容は変更せずPointerだけ更新
- Pointer変更後、Aggregate/Lint等のCurrent Structure依存結果は再計算対象

## 13. Validation

永続化前に:

- Scene/Block/Sentence Order連続
- SpanがText内
- Sibling Block非重複
- Block/Sentence Text == Canonical Slice
- Scene所属BlockがScene Span内
- Semantic Source Run整合
- Current Structure Pointerが同Document/Current Text Lineage

不一致は `STRUCTURE_INVARIANT_ERROR`。

## 14. Warning

```text
unclosed_dialogue_quote
unmatched_closing_quote
ambiguous_heading
empty_paragraph_hint
mapping_boundary_mismatch
semantic_boundary_invalid
```

Warningを全件ReviewItemへ送らない。

## 15. Test

- Narration/Dialogue混在
- Nested/Unmatched/Multiline Quote
- Separator/Heading/Sentence
- Emoji Offset
- Block Global Order
- Candidate Annotation
- Semantic Source Link/Fingerprint
- Threshold Materialization
- Manual Split/Merge
- New TextRevisionでCurrent Structure Clear
- Omitted AnalyzeでCurrent Structure設定
- Explicit Structure AnalyzeでCurrent Pointer不変
- Manual OperationでCurrent Pointer更新
- Select CurrentのLineage Validation
- Revision不変性

## 16. Codex禁止事項

- LLMから任意Character OffsetでScene Split
- Block TypeへSemantic分類混入
- Parent Revision Update
- Start/Endを本文検索で後付け推測
- Boundary Proposal全件Review化
- Current Structureを単純Latest Revisionで推測
- Explicit Structure AnalyzeだけでCurrent Pointerを勝手に変更
