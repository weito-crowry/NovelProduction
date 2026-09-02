# 14 Testing and Evaluation 詳細設計

## 1. 目的

Style Analysisの決定論的処理、DB整合性、Runtime/Job、API/WebUI、Semantic Model、Local Source Adapterを再現可能に検証する。CIはLive Site/Modelへ依存させず、同じInvariantを全Layerへ重複配置しない。

上位仕様は `../basic-design.md`。Semantic Model Contract Testは15を正本とする。

## 2. テスト層

```text
unit
integration
API/WebUI contract
manual dogfood/evaluation
```

- Deterministic Algorithm:Unit。
- DB/Migration/Repository/Worker:Integration。
- API:Contract/Revision/Job。
- WebUI:User Flow。
- Model品質:CI外Evaluation。

同じConstraintをUnit/API/E2Eへ機械的に重複させない。

## 3. Fixture方針

- 短い自作日本語Fixture。
- HTML/EPUB Fixtureは構造検証に必要な最小DOM/Packageのみ。
- 外部作品本文をRepositoryへコピーしない。
- Semantic Testは15 Fake Model Clientを使う。
- 巨大Snapshot Frameworkは追加しない。

## 4. Canonical Fingerprint

09共通UtilityをUnit Testする。

- Object key順が違っても同Hash。
- Unicodeを`ensure_ascii=False` UTF-8でHash。
- separators固定。
- Sort済みCollectionで順序再現性。
- Optional Fingerprint項目はMissing Keyではなく`null`。
- NaN/Infinity拒否。
- SHA-256 lowercase 64 hex。
- InputなしFingerprint列はNULL、空Object Hashを代用しない。

02/03/08/09/11が独自Serializerを実装していないことを確認する。

## 5. Normalization

- CRLF/BOM/NFC、NFKC非適用、全角空白保持。
- `\n\n` Paragraph、Single LF非分割。
- Control/TextMapping/Code Point。
- Scene Break Raw→Canonical Mapping。
- 同Raw+同Hint ->Reuse、同Raw+異Hint ->New Revision。
- Normalizer Version変更 ->New Revision。
- Current Text変更 ->Current Structure Clear。

## 6. Structure

- Scene/Block/Sentence Order/Span、Block Global Order。
- SentenceはDialogue/Narrationだけ。
- `monologue`なし。
- Non-text Hint exact Block Boundaryのみ。
- Revision Fingerprint Reuse Idempotency。
- Raw Boundary Candidate全Valid保存、Candidate Min変更でStructure不変。
- Current Manual/Semantic + Full ->保持/Boundaryなし。
- Current Automatic + deterministic ->保持。
- Current Automatic + Full ->Boundary実行/Semantic昇格可能。
- Historical Semantic存在時同fingerprint SemanticをReuse。
- 1 Boundary RunからAuto Apply値違いで複数Semantic Structure可。
- rebuild=true ->再生成。
- Explicit Structure + rebuild ->422。
- Historical TextでPointer不変。
- Auto Apply Policy変更だけでCurrent Pointer不変。

## 7. Local Source Import

Dependency/Parser:

- API Runtime `beautifulsoup4>=4.13,<5.0`。
- BeautifulSoup backend=`html.parser`。
- `lxml/html5lib/ebooklib`非依存。
- EPUB ZIP/XML=`zipfile + xml.etree.ElementTree`。

Network Import/Refresh Endpoint/Job不存在。

TXT:

- UTF-8/BOM strict。
- 1 File=1 Episode。
- SHA Identity。

HTML:

- Content Root Exactly-one article -> Exactly-one main -> body。
- body不存在Parse Error。
- 除外Element。
- DOM Text Node重複なし。
- Block Element -> Paragraph Boundary。
- `<br>` single LF。
- `<ruby>` rt/rp除外。
- `<hr>` Scene Hint。
- Paragraph Boundary縮約。

EPUB:

- Upload SHA Identity。
- container.xml/OPF/Manifest/Spine。
- Navigation/Cover除外。
- EPUB3 nav/EPUB2 NCX/fallback title。
- Selected Spine Entry uncompressed total上限。
- Path normalization。
- XHTMLはHTML共通Utility。

Import:

- New201同期、Duplicate200、Jobなし。
- Duplicate Race Existing Reuse。
- Upload Limit/Encoding/Parse Error。
- Adapter Parse後CORE Normalization。
- 1 Episode失敗でNew Work部分保存なし。
- Same Normalization InputでTextRevision Reuse。
- Purge Cascade。

## 8. Migration / Storage Gate

- Fresh001→008 / Existing005→008。
- Existing001〜005 Checksum不変。
- `PRAGMA foreign_key_check` / `integrity_check`。
- Job Type4種のみ。
- `style_imports`/Upload Stagingなし。
- Source Identity/1 Source=1 Work。
- Snapshot Delete/PurgeでTextRevision CHECK違反なし。
- Project Document Composite Episode FK。
- Current Pointer Logical FK。
- TextRevision normalization_input_fingerprint Unique。
- Structure fingerprint Unique/Reuse。
- Boundary Source Link Run非Unique。
- Run Output CASCADE vs Stable Identity SET NULL。
- Mention Entity IDなし、Relation/Term-Linkなし。
- `term_explanation` 1 Run×1 TermMention Unique。
- ReviewItem Subject Registry/Scope/State/Version。
- InferenceReview Registry/Alias Parent Scope。
- ManualOverride Append-only/Scope。
- Project Character Link。
- Measurement Unique/07 Registry型整合。
- AggregatePolicy Version/Input Fingerprint/Measurement Link/REAL値。
- Rule REAL/target_scope/source_kind/min-max/Source Aggregate3 Role。
- Lint scene_id/Input Fingerprint。
- `analysis_stale`等永続bool不存在。

同じIntegrity Checkを全Scenarioへ重複追加しない。

## 9. Entity / Speaker Regression

- Mention Extractor Registry非依存、Candidate Persist。
- Resolver Cache不可/Partial Mention成功Subjectのみ。
- Work跨ぎResolution/Same Name複数強制選択なし。
- 15 Entity Candidate Shortlist max20/order/type/same-scene。
- Resolver threshold未満unresolved。
- pronoun/role_title new禁止。
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
- 15 Term Candidate Shortlist max20/order/type/same-scene。
- Resolver threshold未満unresolved。
- Work跨ぎResolution/Manual Term/Alias/Novelty Reduce。
- Reference Prefix Complete/Incomplete。
- Project Resolver Succeeded Complete/Partial Incomplete。
- Target In-flight Context。
- Term Explanation Candidate 0件/複数Reduction。
- 1 Run×1 TermMention最大1 Annotation。
- Explanation単一Block、別Scene探索なし。
- Confirmed partialをsufficient扱いしない。
- Delay負/正。

## 11. Scene / Block Semantic

- Function/Tone Multi-select。
- unclear vs source unknown。
- Rejected Currentだけ ->unknown。
- Confirmed InferenceはThreshold未満でもValidation後採用。
- Scene Classifier Entity/Term/Speaker非依存。
- POV threshold/Disabled Entity/Mention State。
- Block Primary Narrationのみ、Secondary/Dialog Functionなし。
- Candidate Min未満Raw保存、Auto ApplyだけStructure影響。
- Scene Axis OverrideでSemantic Metric非Stale。
- 15 Scene classify/reduce Contract。
- 15 POV classify/reduce Contract。

## 12. Semantic Model Contract

15をTable-driven Testの正本にする。

- `ModelRequest`/`ModelClient.complete_json(request)`。
- API Runtime `httpx>=0.28,<1.0`、OpenAI SDK非依存。
- ApiSettings Environment名/default/validation。
- provider disabled/openai_compatible。
- API KeyなしLocal Provider許可。
- `/chat/completions` + temperature=0.0。
- AuthorizationはKey設定時だけ。
- `choices[0].message.content` JSON Object Parse。
- HTTP Retry対象/非対象/最大1。
- Contract Repair最大1、別Model Escalationなし。
- 共通Prompt、Prompt ID/Version Registry Exactly 10件。
- Unknown Key/Invalid Enum/bool-as-number/Foreign ID拒否。
- Block-relative Span Validation。
- List Item Drop + Warning、Top-level Invalid Repair。
- >30k Entity Mention/Term Candidate/Boundary Chunk overlap/dedup。
- AnalysisRun prompt_id/version保存。

CIは`httpx.MockTransport` + Fake Model Clientだけを使用し実Providerへ接続しない。

## 13. Metric Registry / Calculation

07 v1 RegistryをTable-driven Testの正本にする。

- Metric Name Exactly 29件、重複なし。
- Group/Unit/Value Type/Scope/Tolerance完全一致。
- `zero_width_tolerance > 0`。
- Percentile Metricはfloat。
- 指定Scalar Count/Char Countだけint。
- MissingはMeasurement Row不存在。
- Profile Validationがscope/unit/toleranceを利用。
- Sentence/Block/Paragraph対象集合。
- Dialogue0件Count/Ratio、Bridge40-41/Narration Run。
- Character TargetはCurrent Mention/SpeakerありEntityだけ。
- 非登場Reference EntityへCharacter Rowなし。
- Mentionのみ人物 ->utterance_count=0、他Speaker Metricなし。
- Semantic Composition unknownでなし/Narration0で0。
- Speaker Streak/Question Ratio。
- First Appearance Complete/Incomplete、Project Partialなし。
- Scene Scope Term MetricはFirst Appearance Sceneだけ。
- Eligible Term0件new_per_1000=0。
- 説明なしTermはRatio分母/Delay外。
- sample_count。

## 14. Runtime / Worker Integration

- DAG/Dependency Edge Mode/Independent Branch。
- Scene Semantic非依存Semantic Metric。
- Resolver Cache不可。
- Relevant Policy KeyだけStale。
- Provider Disable後も過去Run表示。
- Current Manual/Semantic Full保持。
- Current Automatic Full Semantic昇格。
- Boundary FailureでAutomatic継続 + Full Job partial。
- metrics preset Analyzer非再実行。
- Work Jobが子Jobを作らずinline処理。
- Worker Thread1/FIFO/Recovery/Retry/Cancel。
- analyze_document/analyze_reference_workだけ`partial`可。
- recompute_aggregate 0 Input ->succeeded、Persistence Failure ->failed、partialなし。
- run_lint Missing Metric/Selector ->succeeded、Invariant Failure ->failed、partialなし。
- Local File/Profile生成はWorker不使用。
- `build_profile` Job不存在。

## 15. Aggregate / Corpus

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
- Count Measurement統計もfloat結果を`value_real`へ丸めず保存。

## 16. Profile

- ProfileGenerationPolicy独立。
- Exact median/p25/p75 Aggregate IDs + AggregatePolicy Version一致。
- Stale Aggregate明示利用はWarningのみ。
- Scene Aggregate `filter_json.scene` -> Rule Selector wrapper除去。
- Rule Source3 Link。
- Manual Profile同期Version1、Aggregate Linkなし。
- New Version parent + Full Snapshot、同期、Jobなし。
- 編集Version source_kind=manual、旧Aggregate Provenance非継承。
- Count Metric Manual Ruleへ小数Range可。
- Rule bool/NaN/Infinity拒否。
- Enabled Rule min/max両方必須、preferred範囲。
- Character Rule Auto生成なし。
- PATCH Identity name/description only。
- Activate version_no、Archive、Historical Archived Lint可。
- Import/Export不存在。

## 17. Review / Status

- ReviewItem Subject Registry Exactly 7種。
- Manual ReviewItem create/priority/default/scope。
- Resolve/Ignore expected_version/resolution_note/version increment。
- Internal supersede。
- Inference Review Registry全組合せ + Registry外拒否。
- Alias Review Parent Scope/Run一致。
- ReviewItemとInferenceReview独立。
- Append-only Override Set/Clear/Revert。
- TermMention Explanation Lineage。
- Metric-only4分類だけmetrics preset。
- Mention Resolution/Alias Review、Entity/Term Enabled ->Semantic Reanalysis Required。
- Scene Axis ->Metric Jobなし。
- Deterministicのみ ->Basic current/Semantic not_analyzed。
- New Text/Manual Structure + old history ->stale。
- Registry Correction + 他Branch current ->Semantic stale優先。
- Current Execution Partialのみ ->partial。
- 全Current + 古い履歴 ->current。
- 永続stale boolなし。

## 18. Lint

- Document Lint Document/Scene/Character Rule。
- Scene-only Scene Ruleだけ、enabled countもScene Ruleだけ。
- Selector Match/Non-match/Unknown。
- Unknown SpecificがGlobalを抑制しない。
- Character LinkなしNot Applicable/MeasurementなしMissing。
- Both-side Range内/上下、min=max Tolerance。
- Count Metric小数RangeでもDeviation計算。
- Preferred差だけFindingなし。
- Basic-onlyでSemantic Run変更Fingerprint不変。
- 未参照Axis変更不変/Unknown→Known変化。
- Coverage0 Succeeded。

## 19. API / WebUI

API:

- Local New201/Duplicate200/Jobなし、Network Endpointなし。
- Work Detail/Episode Detail責務分離。
- Full Provider unavailable 409。
- Basic/Semantic Status。
- Current Manual/Semantic保持、Automatic Full昇格、rebuild/Explicit validation。
- Override Registry Request/Inference Review exact Field Path。
- ReviewItem Create/Resolve/Ignore、generic confirm/reject不存在。
- Aggregate Recompute exact Request/202。
- Profile Exact3 Aggregate Request/manual/new-version同期。
- PATCH Profile name/description only、Activate/Archive。
- Count Metric Rule小数Range可、invalid numeric拒否。
- Lint POST202 + run_lint Job。

WebUI:

- Local Sync Import / Network Controlなし。
- Status/Structure kind/Automatic昇格/Rebuild。
- Semantics Correction / Inference Review / ReviewItem管理分離。
- Aggregate Builder。
- Profile Sync Save/Stale Warning/min-max/Count小数/Activate/Archive。
- Lint Job Polling/Coverage/Stale。

## 20. Gold / E2E / Dogfood

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

## 21. CI / Completion

既存Ruff/Format/Mypy/Pytest/Coverage、WEBUI lint/typecheck/test/build/e2e、pre-commitを正本とする。MCPは変更しないが既存CI RegressionとしてPASSを要求する。

Coverage Gateを下げない。Coverageだけの低価値Testを大量追加しない。各SA Phaseは該当Scopeの検証だけ必須。未実施をPASS扱いしない。

## 22. Codex禁止事項

- Live Site/実ModelをCIからCall。
- Flaky Test Skipで完了扱い。
- Coverage Threshold低下。
- 全Layerへ同じInvariant重複。
- 独自Fingerprint Serializer追加。
- Network Import/Refresh前提Test追加。
- 01/15以外のParser/Model方式を勝手に採用。
- Local File ImportをJob前提でTest。
- Term Explanation複数Rowを正しいとTest。
- Inference Review Registry外Fieldを正しいとTest。
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
- Policy Version丸ごとの無関係Staleを正しいとTest。
- Analysis Status永続bool化。
- Profile Import/Export追加。
- Resolver Cache不可Test省略。
- Unrelated Test Refactor拡大。

## 23. v1.1 SA-I External Agent verification

SA-I は [16-external-agent-mcp.md](16-external-agent-mcp.md) を正本として、次を
追加検証する。

- Internal/External parity（10 model-backed Analyzer、Prompt/Contract/Run/Warning/Current Run）。
- Chunk restart/reduce、boundary merge、Term Explanation fallback、Entity/Term dynamic registry。
- Migration 001→009、001〜008 byte unchanged、JSON/foreign key/partial pending invariant。
- Session/Task restart、commit後 response loss の same-response idempotency、repair maximum two attempts。
- Runtime contract、saved AnalysisPolicy、executor model、human state drift の fail closed。
- Current Text/Structure CAS、Reference Episode revision drift、Worker recovery、Job retry/purge conflict。
- Provider disabled 外部 start/submit と server-side model HTTP request 0件。
- MCP existing59 unchanged、new6 exact、total65、project_id required、forbidden import 0。

Real ChatGPT connector dogfood は Luna の CI/test scope ではなく、commit/push と
ChatGPT GitHub review の後に実施する。
