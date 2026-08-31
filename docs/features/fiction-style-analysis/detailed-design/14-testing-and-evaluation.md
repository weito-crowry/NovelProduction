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

責務:

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

## 4. Normalization

必須:

- CRLF/BOM/NFC。
- NFKC非適用。
- 全角空白保持。
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

## 5. Structure

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
- `rebuild_structure=true` -> Automaticから再生成。
- Explicit Structure + rebuild ->422。
- Historical TextでPointer不変。
- Auto Apply Policy変更だけでCurrent Pointer不変。

## 6. Local Source Import

TXT:

- UTF-8/BOM。
- 1 File=1 Episode。
- SHA Identity。

HTML:

- Block Paragraph Serialization。
- `<br>` Single LF。
- Ruby Surface。
- `<hr>` Raw Scene Hint。
- Script/Style除外。

EPUB:

- Upload SHA Identity。
- Spine Order。
- Navigation/Cover除外。
- Metadata/Title fallback。
- 複数Episodeが同Snapshot参照。

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

## 7. Migration / Storage Gate

- Fresh001→008。
- Existing005→008。
- Existing001〜005 Migration Checksum不変。
- `PRAGMA foreign_key_check`。
- `PRAGMA integrity_check`。
- Job Typeが4種だけ。
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
- Term Novelty Singleton Index。
- Term Explanation subject=TermMention。
- ManualOverride Scope/Purge/Append-only Repository。
- Project Character Link Document uniqueness。
- Measurement Unique。
- AggregatePolicy Version/Input Fingerprint/Measurement Link。
- Rule enabled時min/max必須、preferred範囲、target_scope/source_kind。
- Rule Aggregate Source preferred/min/max 3 Role。
- Lint scene_id/Input Fingerprint。
- `analysis_stale`等永続bool不存在。

Integrity Checkを各Scenarioへ重複追加しない。

## 8. Entity / Speaker Regression

- Mention Extractor Registry非依存。
- Candidate Type/Name Persist。
- Mention RowにEntity IDなし。
- Resolver Candidate Fields利用。
- Resolver Cache不可。
- Partial Mention Run成功SubjectだけResolve。
- Registry Input Fingerprint。
- Registry自然成長だけで過去Resolver非Stale。
- Manual Registry変更でResolver Stale。
- Work Episode跨ぎResolution。
- Same Name複数で強制選択なし。
- Manual Entity/Alias。
- Disabled Entity除外。
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
- Authoring Character自動更新なし。

## 9. Term Regression

- Candidate Extractor Registry非依存。
- Candidate Block/Span Persist。
- Resolver Partial Candidate入力。
- Resolver Cache不可。
- Registry自然成長だけで過去Resolver非Stale。
- Manual Term/Alias。
- Work Episode跨ぎResolution。
- Novelty Reduce Agreement/Conflict。
- Reference Prefix全Succeeded -> First Appearance Complete。
- 前方Text/Structure欠落 -> Incomplete。
- 前方Resolver Partial -> Incomplete。
- Project Resolver Succeeded -> Complete。
- Project Resolver Partial -> Incomplete。
- Target In-flight Context使用。
- 前方Revision変更でState変更。
- Explanation subject=TermMention。
- Same Scene説明前/後/なし。
- 別Sceneへ探索しない。
- Delay負/正。
- Incomplete時First Appearance Metricなし。

## 10. Scene / Block Semantic

- Function/Tone Multi-select。
- Taxonomy `unclear`とEffective `unknown`を区別。
- No Current Run -> source unknown/value null。
- Rejected Currentだけ -> unknown。
- Low Confidence Current -> unclear/inferred。
- Confirmed InferenceはThreshold未満でもValidation後採用。
- Scene Classifier Entity/Term/Speaker非依存。
- POV mention_resolution State/threshold/Disabled Entity。
- Block PrimaryはNarrationだけ。
- Secondary/Dialog Function不存在。
- Candidate Min未満Raw保存。
- Auto ApplyだけStructure影響。
- Scene Axis OverrideでSemantic Metric非Stale。
- Block Primary OverrideでMetric Stale。

## 11. Metric Unit

- Metric Name/Version/Scope。
- Char Count/Percentile。
- Sentence/Block/Paragraph対象集合。
- Dialogue0件 Count/Ratio。
- Utterance外括弧除外。
- Conversation Bridge40/41。
- Narration Run。
- Character対象はCurrent Mention/SpeakerありEntityだけ。
- 非登場Reference EntityへCharacter Rowなし。
- Mentionのみ人物 -> utterance_count=0、他Speaker Metricなし。
- Semantic Composition source=unknownでRowなし。
- Narration0/DialogueありでComposition=0。
- Speaker Streak/Question Ratio。
- Resolver DependencyでDisabled Entity/Term除外。
- First Appearance Complete/Incomplete。
- Eligible Term0件new_per_1000=0。
- 説明なしTermはSame Scene Ratio分母、Delay sample外。
- `sample_count`定義。
- Scene Axis変更でMetric State不変。

## 12. Runtime Integration

Fake Model + Temp SQLite。

- DAG/Cycle Detection。
- Dependency Edge Mode。
- Complete vs Subject Partial Allowed。
- Independent Branch継続。
- Resolver Cache不可。
- Relevant Policy Input subsetだけCurrent条件。
- Policy Version Upでも参照Key同値ならCurrent維持。
- Registry自然成長だけで過去Resolver非Stale。
- Manual Registry State変更でResolver Stale。
- Mention Resolution Review変更でSpeaker/POV Stale。
- Provider disabled後も保存済みRun表示可。
- Model設定変更だけでHistorical Consumption無効化なし。
- New Model ExecutionはCache Key分離。
- Current Manual/Semantic Full保持。
- Current Automatic Full Semantic昇格。
- Boundary FailureでAutomatic継続 + Full Job partial。
- rebuild/Explicit/Historical Pointer。
- metrics presetはSemantic Analyzer再実行なし。
- Document Job Succeeded/Partial/Failed。
- Work Jobが子Jobを作らずinline処理。
- Work Job Order/Progress/Partial/Revision Change。

## 13. Worker Integration

- Worker Thread 1本。
- Request DB Connection非再利用。
- Notify/FIFO/Project公平Requeue。
- Startup Active Project Scan。
- Running -> `WORKER_INTERRUPTED` Failed。
- Queued Recovery。
- 1 Project Failureでも継続。
- Retry = New Job Row。
- Cancel Queued/Running Safe Point。
- Job Type4種のみ。
- Local File/Profile生成はWorker不使用。
- `run_lint` Job Resultにlint_run_id。

## 14. Aggregate / Corpus

Membership:

- include_all=true + exclude。
- include_all=false + include。
- MembershipなしEpisode Override拒否。
- Work Membership削除でOverride削除。

Aggregate:

- Container `reference_work|corpus`。
- Target `document|scene`。
- Character Aggregateなし。
- Measurement Row等重み。
- `sample_count`をWeightにしない。
- Count4種分離。
- Current Text/Structure/Runだけ使用。
- Current Metric Run partial allowed。
- Scene Filter AND/OR。
- Required Axis unknown -> skipped + state hash。
- Effective unclearは通常Filter可能。
- Axis Available Non-matchはSkippedへ数えない。
- Source Episode IDs/Input Measurement IDs/StatisticをFingerprintへ含める。
- Aggregate→Measurement Link。
- AggregatePolicy Version変更でStale。
- Aggregate 0 Input時は新Rowなし。

## 15. Profile

- ProfileGenerationPolicyはAnalysisPolicy/AggregatePolicyと独立。
- Corpus ProfileはExact median/p25/p75 Aggregate IDs。
- 3 AggregateのCorpus/Target/Filter/Metric/Version/AggregatePolicy一致Validation。
- Stale Aggregate明示利用はWarningのみ。
- Scene Aggregate `filter_json.scene` -> Rule Selector wrapper除去。
- Rule→Aggregate Source3 Role。
- Document/Scene target_scope Mapping。
- Character RuleはAuto生成しない。
- Manual Character Rule。
- Enabled Ruleはmin/max両方必須。
- preferred指定時min<=preferred<=max。
- min=maxはMetric tolerance必須。
- Exact Duplicate Enabled Rule拒否。
- Profile Import/Export不存在。
- Manual Profile/New Versionは同期、Jobなし。
- New VersionでActive不変。
- Edited Versionはsource_kind=manual、旧Aggregate Provenance非継承。

## 16. Review / Status

- Manual > Confirmed > Inferred。
- Append-only Set/Clear/Revert。
- Existing Override Row Update/Deleteなし。
- Revert後Inference fallback。
- TermMention Explanation Override Lineage。
- Metric-only4分類だけ -> internal metrics preset。
- Mention Resolution Review -> Semantic Reanalysis Required。
- Entity/Term Enabled -> Semantic Reanalysis Required。
- Scene Axis Correction -> Metric Jobなし。
- Deterministicのみ -> Basic current/Semantic not_analyzed。
- New Text/Manual Structure + old history -> stale。
- Registry Correction + 他Branch current -> Semantic stale優先。
- Current Execution Partialのみ -> partial。
- 全Current + 古い履歴 -> current。
- 永続stale boolなし。
- Low-confidence自動Reviewなし。

## 17. Lint

- Document Lint: Document/Scene/Character Rule。
- Scene-only Lint: Scene Ruleだけ。
- Scene-only enabled_rule_countはScene Ruleだけ。
- target_scope Target Enumeration。
- Scene Selector Available Match/Non-match。
- Required Axis unknown -> Applicable+Missing+Warning。
- Unavailable Specific RuleがGlobal Ruleを抑制しない。
- Effective unclearは通常Taxonomy値。
- Same Specificity複数Rule。
- Character LinkなしNot Applicable。
- LinkありMeasurementなしMissing。
- Both-side Range内/上下。
- min=max Tolerance。
- Preferred差だけFindingなし。
- Basic-onlyでSemantic Run変更Fingerprint不変。
- 未参照Scene Axis変更Fingerprint不変。
- Unknown→Known参照AxisでFingerprint変化。
- Coverage0 Succeeded。
- Finding Evidence/Review継承。

## 18. API Contract

- Local New201/Duplicate200/Jobなし。
- Network Import/Refresh Endpoint不存在。
- Basic/Semantic Status。
- Project Isolation。
- Job Lifecycle/Partial/Retry。
- Text/Structure explicit IDs。
- Select CurrentとHistorical Selector分離。
- Current Manual/Semantic保持、Automatic Full昇格、rebuild/Explicit validation。
- Manual Entity/Term/Alias/Character Link。
- Semantics Selected Run ID。
- Override Set/Clear/Revert。
- Aggregate Recompute202/Result IDs/Stale。
- Profile from Corpus/Manual/New Versionは同期、Jobなし。
- Profile Import/Export不存在。
- target_scope/Range Validation/Activation。
- Lint POST202、Metric Run ID不要。
- Selector Unavailable WarningはErrorでない。
- Purge。

## 19. WebUI

- Local Sync Import / Network Controlなし。
- Duplicate Existing Link。
- Work Analyze Progress/Partial。
- Revision Selector / Current Structure Badge。
- Basic/Semantic Status表示。
- Automatic Full昇格 / explicit rebuild。
- Manual Semantic Correction / Character Link。
- Aggregate Builder / skipped表示。
- Corpus Include/Exclude/Count。
- Profile Exact Aggregate Group選択。
- target_scope Editor / min-max必須。
- Save vs Activate。
- Lint Job Polling/Selector Warning/Coverage/Stale。

Pollingは`succeeded|partial|failed|cancelled`で停止する。

## 20. Gold / Model Evaluation

自作短文の小さなCurated Gold Setを使う。固定件数ノルマや根拠の薄い固定Precision/F1 Release Gateは置かない。

CI外Evaluation記録:

```text
provider/model
prompt/analyzer version
relevant policy values
dataset hash
precision/recall/F1 where meaningful
unknown rate
schema failure rate
latency summary
```

明確な実バグをRegression Fixtureへ追加する。

## 21. E2E / Dogfood

E2EはExternal Site/Modelへ接続しない。

代表Flow:

```text
Local Text Import
-> Deterministic Analyze
-> Full Analyze (Automatic -> optional Semantic)
-> Corpus/Aggregate
-> Profile synchronous build
-> Project Draft Capture
-> Lint job
```

Semantic FlowはFake Providerで別1本。

Live DogfoodはCI外。ユーザーが用意した少数Episode相当ファイルから確認し、問題なければWork全体へ広げる。

毎回の権利確認UIは不要。

## 22. CI / Completion

既存Ruff/Format/Mypy/Pytest/Coverage、WEBUI lint/typecheck/test/build/e2e、pre-commitを正本とする。

MCPは変更しないが既存CI RegressionとしてPASSを要求する。

Coverage Gateを下げない。ただしCoverageだけの低価値Testを大量追加しない。

各SA Phaseは該当Scopeの検証だけ必須。未実施検証をPASS扱いしない。

## 23. Codex禁止事項

- Live Site/有料ModelをCIからCall。
- Flaky Test Skipで完了扱い。
- Coverage Threshold低下。
- 全Layerへ同じInvariant重複。
- Network Import/Refresh前提Test追加。
- Local File ImportをJob前提でTest。
- `build_profile` Jobを期待するTest。
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
