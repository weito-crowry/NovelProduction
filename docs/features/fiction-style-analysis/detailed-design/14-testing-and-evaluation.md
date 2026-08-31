# 14 Testing and Evaluation 詳細設計

## 1. 目的

Style Analysisの決定論的処理、DB整合性、Runtime/Job、API/WebUI、Semantic Model、Local Source Adapterを再現可能に検証する。CIはLive Site/Modelへ依存させず、同じInvariantを全Layerへ重複配置しない。

上位仕様は `../basic-design.md`。

## 2. テスト層

```text
unit
integration
API/WebUI contract
manual dogfood/evaluation
```

- Deterministic Algorithm: Unit。
- DB/Migration/Repository/Worker: Integration。
- API: Contract/Revision/Job。
- WebUI: User Flow。
- Model品質: CI外Evaluation。

同じConstraintをUnit/API/E2Eへ機械的に重複させない。

## 3. Fixture方針

- 短い自作日本語Fixture。
- HTML/EPUB Fixtureは構造検証に必要な最小DOM/Packageのみ。
- 外部作品本文をRepositoryへコピーしない。
- Semantic TestはFake Model Responseを使う。
- 巨大Snapshot Frameworkは追加しない。

## 4. Canonical Fingerprint

09共通UtilityをUnit Testする。

- Object key順が違っても同Hash。
- JSON whitespace概念をHash入力へ持ち込まない。
- Unicodeを`ensure_ascii=False` UTF-8でHash。
- Sort済みCollectionで順序再現性。
- Optional Fingerprint項目はMissing Keyではなく`null`。
- NaN/Infinity拒否。
- SHA-256 lowercase 64 hex。
- InputなしFingerprint列はNULL、空Object Hashを代用しない。

02/03/08/09/11が独自Serializerを実装していないことをCode Review/Testで確認する。

## 5. Normalization

- CRLF/BOM/NFC、NFKC非適用、全角空白保持。
- TAB/Trailing Space。
- `\n\n` Paragraph、Single LF非分割。
- Control Character。
- Unicode Code Point Span。
- TextMapping Identity/Replace/Delete/Collapse。
- Scene Break Raw→Canonical Mapping成功/Drop。
- 同Raw+同Hint -> Revision Reuse。
- 同Raw+異Hint -> New Revision。
- Normalizer Version変更 -> New Revision。
- Current Text変更 -> Current Structure Clear。

## 6. Structure

- Scene/Block/Sentence Order/Span。
- Block Global Order。
- SentenceはDialogue/Narrationだけ。
- Block Typeに`monologue`なし。
- PsychologyはSemantic側。
- Separator `scene_id=NULL`可。
- Non-text Scene Break HintはExact Block Boundaryのみ。
- Automatic/Semantic/Manual Revision。
- Fingerprint Reuse Idempotency。
- Raw Boundary Candidate全Valid保存。
- Candidate Min変更でStructure不変。
- Current Manual/Semantic + Full ->保持/Boundaryなし。
- Current Automatic + deterministic ->保持。
- Current Automatic + Full ->Boundary実行/Semantic昇格可能。
- Historical Semantic存在時同fingerprint SemanticをReuse。
- 1 Boundary RunからAuto Apply値違いで複数Semantic Structure可。
- `rebuild_structure=true` ->Automaticから再生成。
- Explicit Structure + rebuild ->422。
- Historical TextでPointer不変。
- Auto Apply Policy変更だけでCurrent Pointer不変。

## 7. Local Source Import

TXT:

- UTF-8/BOM。
- 1 File=1 Episode。
- SHA Identity。

HTML:

- Content Root選択はExactly-one `article` -> Exactly-one `main` -> `body`。
- body不存在はParse Error。
- script/style/noscript/template/svg/canvas/nav/header/footer/aside/form除外。
- DOM Text Nodeを1回だけWalkし重複出力なし。
- Block Element境界 -> Paragraph Boundary。
- `<br>` -> Single LF。
- `<ruby>` -> rt/rp除外でSurfaceのみ。
- `<hr>` ->文字を出さずRaw Scene Hint。
- Paragraph Boundary連続は1つへ縮約。

EPUB:

- Upload SHA Identity。
- Spine Order。
- Navigation/Cover除外。
- Work Metadata/Title fallback。
- Episode Title Navigation -> Heading -> fallback。
- 複数Episodeが同Snapshot参照。
- XHTML本文はHTML共通Utilityを使用。

Import Contract:

- New -> 201同期、Jobなし。
- Duplicate -> 200、Parse/Persistなし。
- Duplicate Race -> Existing Reuse。
- Upload Limit/Encoding/Parse/Normalization Error。
- Adapter Parse後CORE Normalization。
- 1 Episode失敗でNew Work部分保存なし。
- Same Normalization InputでTextRevision Reuse。
- Purge Cascade。
- Network Import/Refresh Endpoint/Job不存在。

## 8. Migration / Storage Gate

- Fresh001→008。
- Existing005→008。
- Existing001〜005 Migration Checksum不変。
- `PRAGMA foreign_key_check`。
- `PRAGMA integrity_check`。
- Job Type4種のみ。
- `style_imports`/Upload Staging Tableなし。
- Source Identity/1 Source=1 Work。
- Reference Episode Snapshot同Source Validation。
- Project StyleDocument Composite Episode FK。
- Current Pointer Logical FK Service Validation。
- TextRevision `normalization_input_fingerprint` Unique。
- Snapshot Delete/PurgeでTextRevision CHECK違反なし。
- Structure fingerprint Unique/Reuse。
- Boundary Source LinkはBoundary Run非Unique。
- Run Output CASCADE vs Stable Identity `created_by_run_id SET NULL`。
- Mention Entity IDなし。
- Relation/Term-Link Tableなし。
- Term Novelty Unique/Explanation TermMention Subject。
- ManualOverride Scope/Purge/Append-only Repository。
- ReviewItemは10契約 + Scope Pair。
- Project Character Link Document uniqueness。
- Measurement Unique。
- AggregatePolicy Version/Input Fingerprint/Measurement Link。
- Aggregate `value_real`はCount Metric統計でも丸めない。
- Rule target_scope/source_kind/enabled min-max/preferred/Aggregate Source3 Role。
- StyleRule numeric columnsはREALでCount Metric Ruleの小数値を許可。
- Lint scene_id/Input Fingerprint。
- `analysis_stale`等永続bool不存在。

同じIntegrity Checkを全Scenarioへ重複追加しない。

## 9. Entity / Speaker Regression

- Mention Extractor Registry非依存、Candidate Persist。
- Resolver Cache不可/Partial Mention成功Subjectのみ。
- Registry自然成長だけで過去Resolver非Stale。
- Manual Registry変更でResolver Stale。
- Work跨ぎResolution/Same Name複数強制選択なし。
- Manual Entity/Alias/Disabled Entity。
- Inferred AliasだけでMergeなし。
- Resolution Confirm/RejectでEffective Mention変更。
- Resolution Review変更でSpeaker/POV Stale。
- Speaker Explicit/Adjacent。
- turn_taking単独はThreshold以上でもAuto Effectiveなし。
- turn_taking ConfirmでEffective。
- Speaker Manual CorrectionでRaw Speaker Run非Stale。
- `speaker_effective`変更でRaw Speaker Run非Stale。
- Project Character Manual Link。
- Relation Analyzer不存在。

## 10. Term Regression

- Candidate Registry非依存/Block Span Persist。
- Resolver Cache不可/Partial Candidate成功Subjectのみ。
- Work跨ぎResolution/Manual Term/Alias/Novelty Reduce。
- Reference Prefix Complete/Incomplete。
- Project Resolver Succeeded Complete/Partial Incomplete。
- Target In-flight Context。
- Explanation subject=TermMention、同Scene前後/なし、別Scene探索なし。
- Delay負/正。

## 11. Scene / Block Semantic

- Function/Tone Multi-select。
- unclear vs source unknown。
- Rejected Currentだけ -> unknown。
- Confirmed InferenceはThreshold未満でもValidation後採用。
- Scene Classifier Entity/Term/Speaker非依存。
- POV mention_resolution State/threshold/Disabled Entity。
- Block Primary Narrationのみ、Secondary/Dialog Functionなし。
- Candidate Min未満Raw保存、Auto ApplyだけStructure影響。
- Scene Axis OverrideでSemantic Metric非Stale。

## 12. Metric Registry / Calculation

07 v1 Metric RegistryをTable-driven Testの正本にする。

- Metric NameがExactly 29件で重複なし。
- 各DefinitionのGroup/Unit/Value Type/Scope/Tolerance完全一致。
- `zero_width_tolerance > 0`。
- Percentile Metricはすべて`value_type=float`。
- Scalar Count/Char Countだけ指定されたMetricが`int`。
- MissingはMeasurement Row不存在。
- Profile ValidationがMetricDefinition.scope_types/unit/toleranceを利用。
- Sentence/Block/Paragraph対象集合。
- Dialogue0件Count/Ratio、Utterance/Bridge40-41/Narration Run。
- Character TargetはCurrent Mention/SpeakerありEntityだけ。
- 非登場Reference EntityへCharacter Rowなし。
- Mentionのみ人物 -> utterance_count=0、他Speaker Metricなし。
- Semantic Composition unknownでなし/Narration0で0。
- Speaker Streak/Question Ratio。
- First Appearance Complete/Incomplete、Project Partialなし。
- Scene Scope Term MetricはFirst Appearance Sceneだけへ計上。
- Eligible Term0件new_per_1000=0。
- 説明なしTermはRatio分母/Delay外。
- sample_count。

## 13. Runtime / Worker Integration

- DAG/Dependency Edge Mode/Independent Branch。
- Scene Semantic非依存Semantic Metric。
- Resolver Cache不可。
- Relevant Policy KeyだけStale。
- Registry自然成長だけで過去Resolver非Stale。
- Manual Registry State変更でResolver Stale。
- Mention Resolution Review変更でSpeaker/POV Stale。
- Provider Disable後も過去Run表示。
- Current Manual/Semantic Full保持。
- Current Automatic Full Semantic昇格。
- Boundary FailureでAutomatic継続 + Full Job partial。
- metrics preset Analyzer非再実行。
- Work Jobが子Jobを作らずinline処理。
- Worker Thread1/FIFO/Recovery/Retry/Cancel。
- analyze_document/analyze_reference_workだけ`partial`可。
- recompute_aggregate 0 Input -> succeeded、Persistence Failure -> failed、partialなし。
- run_lint Missing Metric/Selector -> succeeded、Invariant Failure -> failed、partialなし。
- Local File/Profile生成はWorker不使用。
- `build_profile` Job不存在。
- run_lint Job payload/result lint_run_id。

## 14. Aggregate / Corpus

- Membership include/exclude。
- AggregatePolicy Version persist/fingerprint/stale。
- Container reference_work|corpus / Target document|scene。
- Measurement Row等重み。
- Source Episode IDs Fingerprint。
- Document missing skipped、Scene StructureなしWarning/架空Countなし。
- Scene Filter Match/Non-match/Unknown、unclear通常値。
- FingerprintにStatistic/Target/Input IDs。
- Aggregate→Measurement Link。
- Current Input/Policy変更でStale。
- Count Measurement統計もfloat結果をそのまま`value_real`保存。

## 15. Profile

- ProfileGenerationPolicy独立。
- Exact median/p25/p75 Aggregate IDs + AggregatePolicy Version一致。
- Stale Aggregate明示利用はWarningのみ。
- Scene Aggregate `filter_json.scene` -> Rule Selector wrapper除去。
- Rule Source3 Link。
- Manual Profileは同期Version1、Aggregate Linkなし。
- New Versionはparent + Full Snapshot、同期、Jobなし。
- 編集Versionはsource_kind=manual、旧Aggregate Provenance非継承。
- Count Metric Manual Ruleへ小数Range可。
- Rule bool/NaN/Infinity拒否。
- Enabled Ruleはmin/max両方必須。
- preferred指定時min<=preferred<=max。
- Character Rule Auto生成なし。
- Import/Export不存在。
- Active不変。

## 16. Review / Status

- Append-only Set/Clear/Revert、Existing Row Updateなし。
- Inference Reviewは`confirmed|rejected`、ReviewItemと独立。
- Manual ReviewItem Create -> item_type=manual_review/reason=user_marked/status=open/version1。
- ReviewItem priority default normal、normal/highのみ。
- ReviewItem Resolve/Ignore expected_version、resolution_note、version increment。
- Closed ReviewItem再更新409。
- ReviewItem resolveでDomain Correctionを暗黙実行しない。
- Low-confidence自動Reviewなし。
- TermMention Explanation Lineage。
- Metric-only4分類だけmetrics preset。
- Mention Resolution Review/Entity/Term Enabled ->Semantic Reanalysis Required。
- Scene Axis ->Metric Jobなし。
- Deterministicのみ ->Basic current/Semantic not_analyzed。
- New Text/Manual Structure + old history ->stale。
- Registry Correction + 他Branch current ->Semantic stale優先。
- Current Execution Partialのみ ->partial。
- 全Current + 古い履歴 ->current。
- 永続stale boolなし。

## 17. Lint

- Document Lint Document/Scene/Character Rule。
- Scene-only Scene Ruleだけ、enabled_rule_countもScene Ruleだけ。
- Selector Match/Non-match/Unknown。
- Unknown SpecificがGlobalを抑制しない。
- Character LinkなしNot Applicable/MeasurementなしMissing。
- Both-side Range内/上下、min=max Tolerance。
- Count Metricの小数RangeでもDeviationをそのまま計算。
- Preferred差だけFindingなし。
- Basic-onlyでSemantic Run変更Fingerprint不変。
- 未参照Axis変更不変/Unknown→Known変化。
- Coverage0 Succeeded。

## 18. API / WebUI

API:

- Local New201/Duplicate200/Jobなし。
- Network Import/Refresh Endpoint不存在。
- Work DetailとEpisode Detail責務分離。
- Work Full Provider unavailable 409。
- Basic/Semantic Status。
- Current Manual/Semantic保持、Automatic Full昇格、rebuild/Explicit validation。
- Job Type別Partial可否。
- Aggregate Recompute202/Stale/Policy Version。
- Profile from-corpus/manual/new-versionは同期でJobなし。
- Count Metric Rule小数Range可、invalid numeric拒否。
- Profile Import/Export不存在。
- ReviewItem Create/Resolve/IgnoreとInference Reviewの分離。
- Generic ReviewItem Confirm/Reject不存在。
- Lint POST202 + run_lint Job、Metric Run ID不要。

WebUI:

- Local Sync Import / Network Controlなし。
- Work/Episode表示責務分離。
- Status/Structure kind/Automatic昇格/Rebuild。
- Semantic Correction / Inference Review / ReviewItem管理分離。
- Manual ReviewItem作成/Resolve/Ignore。
- Aggregate Builder/Warning。
- Profile同期Save/Stale Warning/min-max必須/Count小数Range/Save vs Activate。
- Lint Job Polling/Coverage/Stale。

## 19. Gold / E2E / Dogfood

Goldは自作短文の小規模Curated Set。根拠の薄い固定Precision/F1 Release Gateなし。

CI外Evaluationはprovider/model/prompt/analyzer/relevant policy/dataset hash/precision-recall-F1 where meaningful/unknown/schema failure/latencyを記録する。

E2EはExternal Site/ModelをMock/Fake。代表Flow:

```text
Local Text Import
-> Deterministic Analyze
-> Full Analyze (Automatic -> optional Semantic)
-> Corpus/Aggregate
-> Profile synchronous build
-> Project Draft Capture
-> Lint job
```

Live DogfoodはCI外。ユーザーが用意した少数Episode相当ファイルから確認して広げる。毎回の権利確認UI不要。

## 20. CI / Completion

既存Ruff/Format/Mypy/Pytest/Coverage、WEBUI lint/typecheck/test/build/e2e、pre-commitを正本とする。MCPは変更しないが既存CI RegressionとしてPASSを要求する。

Coverage Gateを下げない。Coverageだけの低価値Testを大量追加しない。各SA Phaseは該当Scopeの検証だけ必須。未実施をPASS扱いしない。

## 21. Codex禁止事項

- Live Site/有料ModelをCIからCall。
- Flaky Test Skipで完了扱い。
- Coverage Threshold低下。
- 全Layerへ同じInvariant重複。
- 独自Fingerprint Serializer追加。
- Network Import/Refresh前提Test追加。
- Local File ImportをJob前提でTest。
- Metric Registry値を実装側で推測するTest。
- Count Aggregate/Profile値を整数へ丸めるTest。
- Generic ReviewItem confirm/rejectを期待するTest。
- ReviewItem CreateをInference Review扱いするTest。
- `build_profile` Jobを期待するTest。
- Aggregate/Lint Jobのpartialを正しいとTest。
- Profile作成をWorker前提にするTest。
- Raw HashだけのTextRevision Reuseを正しいとTest。
- Current Manual/Semantic通常Full置換を正しいとTest。
- Current Automatic Full Boundary Skipを正しいとTest。
- Registry自然成長だけで過去Resolver Staleを正しいとTest。
- Policy Version丸ごとの無関係Staleを正しいとTest。
- Analysis Status永続bool化。
- Profile Import/Export追加。
- Resolver Cache不可Test省略。
- Unrelated Test Refactor拡大。
