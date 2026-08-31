# 03 Structure Segmentation 詳細設計

## 1. 目的

Canonical Textを後段解析が参照できる安定構造へ分解する。本文文字列は変更せず、Automatic/Semantic/Manualの差を`StructureRevision`として履歴化する。Manual/Semantic Structureを通常解析で不用意に置換せず、Automatic CurrentだけはFull解析でSemanticへ昇格可能にする。

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

- Automatic: 決定論的Base構造。
- Semantic: Boundary Analyzer結果をMaterialize。
- Manual: User Split/Merge。

Existing RevisionはUpdateしない。Semantic/ManualはParent必須。

Semantic生成元Boundary AnalysisRunは12 `style_structure_analysis_sources`で追跡する。

## 4. Current Structure Pointer

`style_documents.current_structure_revision_id`は通常表示・Corpus集約・既定Analyzeで現在採用するStructure。

1. Current Textが変わった -> NULL。
2. Current Pointerは同Document Current Text所属必須。
3. Manual Split/Merge成功 -> 新ManualをCurrent。
4. Select Current -> 同Document Current Text所属Revisionだけ設定可能。
5. Historical Structure閲覧/明示解析ではPointerを変えない。

最大Revision NoをCurrentと推測しない。

## 5. Analyze時のStructure選択

Public Analyze:

```text
text_revision_id required
structure_revision_id nullable
preset = deterministic | full
rebuild_structure boolean default false
```

### A. `structure_revision_id` 明示

- 指定Structureが指定TextRevision所属であることを検証。
- Exact StructureをFinalとして使用。
- Boundary Analyzerを実行しない。
- `rebuild_structure=true`との同時指定は422。
- Current Pointer変更なし。

### B. Structure省略 + `rebuild_structure=false` + Current Structureあり

指定TextRevisionがDocument Current Textである場合、Current `source_kind`とpresetで分岐する。

#### Current = manual

`deterministic|full`ともCurrent ManualをFinalとして再利用。Boundaryを実行しない。

#### Current = semantic

`deterministic|full`ともCurrent SemanticをFinalとして再利用。Boundaryを実行しない。

#### Current = automatic

- `deterministic`: Current AutomaticをFinalとして再利用。Boundaryなし。
- `full`: Current AutomaticをBaseとして再利用しScene Boundary Analyzerを実行。Auto Apply CandidateがあればSemantic RevisionをMaterialize/ReuseしてFinalとする。適用境界がなければCurrent AutomaticをFinalとしてReuse。

### C. Current Structureなし、またはHistorical TextRevision

指定TextRevisionからAutomatic StructureをBuild/Reuseする。

- `deterministic`: AutomaticをFinal。
- `full`: Automatic Base -> Boundary -> optional SemanticをFinal。

Historical TextRevisionではDocument Current Pointerを変更しない。

### D. `rebuild_structure=true`

- Current Structureの種類に関係なく指定TextRevisionからAutomatic BaseをBuild/Reuse。
- `deterministic`: AutomaticをFinal。
- `full`: Automatic -> Boundary -> optional SemanticをFinal。
- Job終了時に指定TextRevisionがまだDocument Current TextならFinalをCurrentへ設定。

Explicit Structureとの併用不可。

## 6. Current Pointer更新

AnalyzeがCurrent Structureを更新できるのは次だけ。

1. Current AutomaticをFull解析し、新Semantic RevisionがMaterialize/Reuseされた。
2. Current StructureなしからFinal Structureを確立した。
3. `rebuild_structure=true`でFinal Structureを確立した。

いずれもJob終了時にRequest TextがDocument Current Textと一致する場合だけ更新する。

Current Manual/Semantic再利用、Explicit Structure、Historical TextではPointer不変。

## 7. Fingerprint / Revision Reuse

Automatic:

```text
hash(canonical_sha256, segmenter_id, segmenter_version, config, structure_hints)
```

02 `scene_break_offsets_cp`を含める。

Semantic:

```text
hash(
  parent_fingerprint,
  boundary_run_fingerprint,
  sorted_applied_after_block_ids,
  {"scene_boundary_auto_apply": current_value}
)
```

`scene_boundary_candidate_min`は含めない。

Manual:

```text
hash(parent_fingerprint, operation, canonical_operation_args)
```

同TextRevisionで同fingerprintのRevisionが既に存在する場合は既存RevisionをReuseし、新RowをInsertしない。

Semantic RevisionをReuseする場合、`style_structure_analysis_sources`に同Structureと同Boundary Runの組合せが存在することを確認し、なければ追加する。1 Boundary RunからAuto Apply値違いの複数Semantic Structureが生成され得るため、Boundary Run ID自体はUNIQUEにしない。

Policy値変更だけではCurrent Structure Pointerを自動Clear/Rebuildしない。

## 8. 階層 / Order / Span

```text
TextRevision
 -> StructureRevision
    -> Scene
       -> Block
          -> Sentence
```

- Scene Order: Revision内1..N。
- Block Order: Revision全体Global 1..N。
- Paragraph Index: Revision全体1..N。
- Sentence Order: Block内1..N。
- Span: Canonical Code Point`[start_cp,end_cp)`。

## 9. Paragraph / Block Type

Paragraphは02どおりCanonical`\n\n`で分割。単一LFは同Paragraph。

Block Type:

```text
dialogue
narration
heading
separator
unknown
```

`monologue`は持たない。内面文はNarration + 06 `psychology`。

同Paragraph内でもDialogue/Narration Surface境界があれば複数Blockへ分け、同じ`paragraph_index`を付ける。

`「...」`はDialogue候補。Nested Quoteは外側を1Block。Unmatched QuoteはWarning付き継続。`『』`等だけでDialogueを断定しない。

## 10. Heading / Separator / Sentence

Headingは明確な章節Patternだけ。短文だけではHeadingにしない。

Text Separatorは独立した記号中心Paragraphを`separator` Blockとして保持し`scene_id=NULL`可。

Sentence Rowは`dialogue|narration` Blockだけに作る。Heading/Separator/Unknownには作らない。

Sentence終端は`。！？!?`。終端直後の閉じ括弧を同Sentenceへ含める。終端記号なしの残りTextは最後のSentenceとして保存する。

## 11. Non-text Scene Break Hint

02 `metadata_json.structure_hints.scene_break_offsets_cp`をAutomatic Segmentationで使用する。

Hintは本文へ架空Separator文字を追加しない。

Block生成後、各Hint Offsetについて:

1. `block.end_cp == hint_offset`となるBlockを探す。
2. Exactly 1件かつ後続本文Blockあり -> `after_block_id`明示Scene Boundary。
3. 0件/複数件 -> Drop + `scene_break_hint_not_on_block_boundary` Warning。

Hint位置でBlock途中Splitしない。

## 12. Automatic Scene

Automatic Revisionの明示境界:

1. Non-text Scene Break Hint。
2. Text Separator Block。
3. 本文途中Heading。

明示境界がなければEpisode全体1 Sceneでよい。Separator Block自体はSceneに所属させない。

## 13. LLM Boundary Candidate

06 `scene-boundary-detector`はAutomatic Base Scene内のBlock境界だけを返す。

```text
annotation_type = scene_boundary_candidate
subject_type = block
subject_id = after_block_id
confidence
analysis_run_id
value_json = {base_structure_revision_id,reasons}
```

全Valid Candidateを保存する。Candidate Min未満もRaw履歴として残す。任意Character Offsetは受けない。

## 14. Semantic Materialization

09 `AnalysisPolicy.scene_boundary_auto_apply`以上だけ適用する。

1. Boundary RunがParent Automatic入力か検証。
2. 同Run Candidateのみ読む。
3. Auto Apply以上Block IDをSort/Dedupe。
4. Invalid/既存境界重複除外。
5. 適用後Semantic fingerprintを計算。
6. 同fingerprintのSemantic Revisionが既にあればReuse。
7. 未存在なら新Semantic Revisionを生成。
8. `style_structure_analysis_sources`へ `(structure_revision_id,boundary_analysis_run_id)` Linkを保存。
9. 適用境界0件/Shape同一ならParent AutomaticをFinalとしてReuse。

Candidate MinはMaterializationに使わない。

## 15. Manual Split / Merge / Select

Split:

- Current Structureのみ。
- Existing Block境界`after_block_id`。
- CurrentをParentに新Manual Revision。

Merge:

- Current Structureの隣接Sceneのみ。
- CurrentをParentに新Manual Revision。

同fingerprint Manual Revisionが既にあればReuseする。成功時Final ManualをCurrentへ設定。

Select Current:

- Existing Revision ID。
- 同Document + Current TextRevision所属。
- 内容変更なし、Pointerのみ。

## 16. Validation

- Scene/Block/Sentence Order連続。
- Span Text内。
- Sibling Block非重複。
- Block/Sentence Text == Canonical Slice。
- Scene所属BlockがScene Span内。
- Semantic Source Run/Parent整合。
- Current StructureがCurrent Text Lineage。

不一致は`STRUCTURE_INVARIANT_ERROR`。

## 17. Test

- Paragraph空行/Single LF。
- Narration/Dialogue混在。
- `monologue` Block不存在。
- Separator/Heading/Sentence対象Block。
- Non-text Hint exact/mismatch。
- Automatic FingerprintへHint含有。
- Revision Fingerprint Reuse idempotent。
- Historical Semantic存在 + Automatic Current + Full -> Semantic Reuse。
- Raw Boundary Candidate全Valid保存。
- Candidate Min変更でStructure不変。
- Current Manual + full default -> Manual再利用/Boundaryなし。
- Current Semantic + full default -> Semantic再利用/Boundaryなし。
- Current Automatic + deterministic -> Automatic再利用/Boundaryなし。
- Current Automatic + full -> Boundary実行/Semantic昇格可能。
- rebuild=true ->再生成。
- Explicit Structure + rebuild ->422。
- Historical TextでPointer不変。
- Auto Apply Policy変更だけでCurrent Pointer不変。

## 18. Codex禁止事項

- `monologue` Block Type追加。
- Non-text Hint位置でBlock途中Split。
- `<hr>`相当を架空Text Separatorへ変換。
- LLMから任意Character Offset Split。
- Block TypeへSemantic分類混入。
- Parent Revision Update。
- 同fingerprint Structureを重複Insert。
- Candidate Min未満Raw Candidate破棄。
- Current Manual/Semanticをdefault Full Analyzeで置換。
- Current AutomaticのFull AnalyzeでBoundaryを常にSkip。
- Policy変更だけでCurrent Structureを自動Clear/Rebuild。
- Current Structureを最大Revision Noで推測。
