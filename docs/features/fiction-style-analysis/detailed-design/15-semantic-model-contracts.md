# 15 Semantic Model Contracts 詳細設計

## 1. 目的

04〜06で使用するSemantic AnalyzerのModel Client、Prompt ID/Version、入力Payload、出力JSON、Resolver候補選択、本文Context Window、Validation、Retry/Repairを固定する。

本書はSemantic Model呼出契約の正本であり、CodexはPrompt形式、JSON形状、Provider通信方式、本文Context範囲を独自設計しない。

上位仕様は `../basic-design.md`。Runtime/Current Run/Fingerprintは09を正本とする。

## 2. 実装先

```text
CORE/src/novel_core/style_analysis/
  model_contracts.py
  model_prompts.py
  resolver_candidates.py

API/src/novel_api/style_analysis/
  model_client.py
```

COREは外部HTTP Library/Pydanticへ依存しない。Response Validationは標準Library + dataclass/明示Validatorで実装する。

API Runtime Dependencyとして:

```text
httpx>=0.28,<1.0
```

を`API/pyproject.toml [project].dependencies`へ追加する。OpenAI Python SDKは追加しない。

## 3. ModelRequest / ModelClient Protocol

CORE側:

```python
@dataclass(frozen=True, slots=True)
class ModelRequest:
    prompt_id: str
    prompt_version: int
    system_prompt: str
    user_payload: dict[str, object]


class ModelClient(Protocol):
    def complete_json(self, request: ModelRequest) -> dict[str, object]: ...
```

AnalyzerはHTTP/Base URL/API Keyを知らない。

ModelClientはJSON Objectを返す。Markdown Fenceや説明文をAnalyzerへ渡さない。

09の`complete_json(request: ModelRequest)`はこの定義を指す。

## 4. API Settings / Environment

既存`ApiSettings`へ次を追加する。

```text
style_model_provider: disabled | openai_compatible = disabled
style_model_base_url: str | None = None
style_model_id: str | None = None
style_model_api_key: str | None = None
style_model_timeout_seconds: float = 60.0
```

Environment:

```text
NOVEL_STYLE_MODEL_PROVIDER
NOVEL_STYLE_MODEL_BASE_URL
NOVEL_STYLE_MODEL_ID
NOVEL_STYLE_MODEL_API_KEY
NOVEL_STYLE_MODEL_TIMEOUT_SECONDS
```

Validation:

- provider=`disabled`: Base URL/Model ID不要。
- provider=`openai_compatible`: Base URL + Model ID必須。
- API Keyはoptional。Local ServerでKeyなしを許可する。
- Timeoutは`1 <= value <= 300`。
- Base URL末尾 `/` は除去して保持する。

API KeyはDB/Job Payload/AnalysisRun/通常Logへ保存しない。

## 5. OpenAI-compatible HTTP契約

Endpoint:

```text
POST {style_model_base_url}/chat/completions
```

Base URLは例として`http://127.0.0.1:1234/v1`または`https://api.openai.com/v1`を想定する。

Header:

```text
Content-Type: application/json
Authorization: Bearer <key>   # API Key設定時だけ
```

Request:

```json
{
  "model":"<style_model_id>",
  "messages":[
    {"role":"system","content":"<system prompt>"},
    {"role":"user","content":"<canonical JSON string>"}
  ],
  "temperature":0.0
}
```

User contentは09 `canonical_json_bytes(user_payload).decode("utf-8")`を使う。

Provider固有`response_format/tools/functions`はv1で使わない。最小Chat Completions互換だけを要求する。

Responseは`choices[0].message.content`がstringであることを必須とし、`json.loads()`後Top-level ObjectでなければResponse Invalid。

Streamingは使わない。

## 6. HTTP Retry / JSON Repair

### HTTP Retry

次だけ最大1回Retryする。

```text
Timeout
HTTP 429
HTTP 500
HTTP 502
HTTP 503
HTTP 504
```

Backoff:`1.0 sec`。

その他4xxはRetryしない。

### JSON/Contract Repair

初回Contentが:

- JSON parse failure。
- Top-level Objectでない。
- Analyzer Contract Validation failure。

の場合、同Modelへ最大1回だけRepair Callする。

Repair System Prompt:

```text
直前の出力は指定JSON契約に違反しています。
入力本文やIDを変更・追加せず、検証エラーだけを修正してください。
JSONオブジェクト以外を出力しないでください。
```

Repair User Payload:

```json
{
  "original_request": {...},
  "invalid_response": "...",
  "validation_errors": ["..."]
}
```

Repairも失敗したら対象Analyzer SubjectをContract Failureとして扱う。3回目以降の試行、別ModelへのEscalationはしない。

## 7. 共通System Prompt

全Semantic Promptは次を先頭に使用する。

```text
あなたはNovelProductionの小説本文構造化分析器です。
入力JSONに含まれる本文、ID、候補情報だけを根拠にしてください。
入力に存在しないID、人物、用語、出来事を作らないでください。
不明な場合は推測で埋めず、各契約のunresolved・unknown・unclear・nullを使用してください。
本文の書き換え、続きの生成、批評、助言は行わないでください。
confidenceは0.0以上1.0以下の有限数にしてください。
出力は各Prompt Contractで指定されたJSONオブジェクトだけにし、Markdownや説明文を付けないでください。
```

Analyzer固有InstructionはSection 11〜20をこの共通Promptへ追記する。

## 8. Prompt Registry

| Analyzer | prompt_id | version |
|---|---|---:|
| scene-boundary-detector | `style.scene_boundary` | 1 |
| entity-mention-extractor | `style.entity_mentions` | 1 |
| entity-resolver | `style.entity_resolution` | 1 |
| speaker-attribution | `style.speaker_attribution` | 1 |
| term-candidate-extractor | `style.term_candidates` | 1 |
| term-resolver | `style.term_resolution` | 1 |
| term-explanation-detector | `style.term_explanation` | 1 |
| scene-semantic-classifier | `style.scene_semantics` | 1 |
| block-semantic-classifier | `style.block_semantic` | 1 |
| pov-classifier | `style.pov` | 1 |

Prompt wording、Payload Shape、Output Shape、Reduction規則の結果互換性を変えたらPrompt Versionを上げる。

AnalysisRun `prompt_id/prompt_version`はこのRegistry値を保存する。

v1.1 External Task は Prompt ID だけから validator shape を推測しない。
`model_output_contracts.py` の11 Response Contract IDを Task に保存し、Internal
と External が同じ repairable validator、consumer validation、reducer を使う。
External Task の本文 payload は untrusted analysis data であり、本文内の命令は
解析対象として扱う。Security の最終境界はこの文言ではなく CORE validator と
domain allowlist である。

## 9. 共通Validation

全Model Outputへ適用する。

- Top-level/Item Objectの未知Keyは拒否する。
- Required Key欠落は拒否する。
- boolをint/floatとして受理しない。
- confidenceはfinite `0.0..1.0`。
- IDは正整数かnullable契約に従う。
- Output IDはRequest内Allowlistに存在するものだけ。
- Enumは各設計のKnown Valueだけ。
- Modelが任意のDB IDを生成しない。
- Block-relative Spanは`0 <= start < end <= len(block_text)`。
- Surfaceを伴うSpanはBlock Sliceと完全一致必須。04/05の一意再探索規則を適用してよい。
- Invalid ItemだけDrop可能なList ContractではWarningを残し、他Valid Itemを継続する。
- Top-level Shape自体InvalidならSection 6 Repair対象。

Persist前にItemを設計書指定Keyで安定Sortする。

## 10. 共通Context Window Builder

Resolver/Speaker向け本文ContextはCOREの共通Utilityで構築し、Analyzerごとに独自実装しない。

Block列は指定StructureRevision内のDocument Orderを使う。Contextは必ず対象と同じScene内に限定し、Separatorなど`scene_id=NULL`のBlockは含めない。

### Entity Resolver

対象Mentionの所属Blockを中心に:

```text
previous_blocks = 直前最大2 Block
subject_block   = Mention所属Block 1件
next_blocks     = 直後最大2 Block
```

合計最大5 Block。対象BlockはExactly 1回含める。Scene端では存在する側だけを使う。

### Term Resolver

対象Term Candidate所属Blockを中心にEntity Resolverと同じ:

```text
previous最大2 + subject 1 + next最大2
```

合計最大5 Block。

### Speaker Attribution

対象Dialogue Blockを中心に:

```text
previous_blocks = 直前最大4 Block
subject_block   = 対象Dialogue 1件
next_blocks     = 直後最大4 Block
```

合計最大9 Block。対象Dialogue本文を必ず`subject_block`として渡す。

同Scene Current Effective Mentionから得たEnabled Person集合を`entity_id`昇順で`people`へ渡す。

Context Block Objectは共通で:

```json
{"block_id":53,"block_type":"narration","text":"..."}
```

とする。

## 11. Scene Boundary Contract

Prompt Instruction:

```text
入力Scene内で、時間・場所・POV・文脈が明確に切り替わるBlock境界だけを候補にしてください。
細かな話題転換や段落改行だけでは境界にしないでください。
after_block_idは入力blocksに存在するIDだけを使用してください。
```

Request:

```json
{
  "base_structure_revision_id":10,
  "scene_id":3,
  "blocks":[
    {"block_id":40,"block_type":"narration","text":"..."}
  ]
}
```

Response:

```json
{
  "boundaries":[
    {
      "after_block_id":55,
      "reasons":["time_shift","location_shift"],
      "confidence":0.88
    }
  ]
}
```

Reason:`time_shift|location_shift|pov_shift|context_reset`。Reason 1件以上、重複除去。

同`after_block_id`複数返却時はconfidence最大Itemを採用し、同confidenceならreasonsの和集合をSortして1件化する。

03のExisting Boundary/Scene末尾ValidationはModel後に行う。

## 12. Entity Mention Contract

Prompt Instruction:

```text
本文中に文字として現れている人物・組織・場所・技術・概念・製品・出来事のMentionだけを抽出してください。
省略主語や本文にない名前を補完しないでください。
人物の呼称・役職・代名詞も明示Surfaceがある場合だけ抽出してください。
```

Request:

```json
{
  "scene_id":3,
  "previous_context_blocks":[{"block_id":38,"text":"..."}],
  "blocks":[{"block_id":40,"block_type":"narration","text":"..."}]
}
```

`previous_context_blocks`は04どおり前Scene末尾最大3 Block。Current Sceneの本文Blockは`blocks`へDocument Orderで渡す。

Response:

```json
{
  "mentions":[
    {
      "block_id":40,
      "surface":"田中",
      "start_in_block":4,
      "end_in_block":6,
      "mention_type":"proper_name",
      "entity_type_candidate":"person",
      "canonical_name_candidate":"田中",
      "confidence":0.93
    }
  ]
}
```

Enumsは04を正本とする。

Dedup Key:`(block_id,start_in_block,end_in_block,mention_type)`。Duplicateはconfidence最大を採用する。

## 13. Entity Resolver Candidate Shortlist / Contract

Deterministic Exact Canonical/Confirmed Alias解決は04を先に実行する。Model Resolverは未解決Mentionだけ対象。

Comparison Key:

```python
"".join(ch for ch in unicodedata.normalize("NFC", value).casefold() if not ch.isspace())
```

Candidate ScoreはMention `surface`と`canonical_name_candidate`の各Comparison Keyを、Entity Effective Canonical Name + Confirmed/Manual Alias各Keyと`difflib.SequenceMatcher(...).ratio()`比較した最大値。

Candidate Pool:

1. Disabled Entity除外。
2. `entity_type_candidate != other`なら同Entity Typeだけ。`other`ならType Filterなし。
3. 同Sceneで既にEffective Mention Entityとして登場するCandidateを優先。
4. `(-same_scene, -score, entity_id)`でSort。
5. 最大20件。

`pronoun|role_title` Mentionは同SceneCandidateだけをModelへ渡し、`new` Decisionを許可しない。

Request:

```json
{
  "mention":{
    "mention_id":71,
    "surface":"田中",
    "mention_type":"proper_name",
    "entity_type_candidate":"person",
    "canonical_name_candidate":"田中"
  },
  "previous_blocks":[{"block_id":39,"block_type":"narration","text":"..."}],
  "subject_block":{"block_id":40,"block_type":"narration","text":"...田中..."},
  "next_blocks":[{"block_id":41,"block_type":"dialogue","text":"..."}],
  "candidates":[
    {
      "entity_id":5,
      "entity_type":"person",
      "canonical_name":"田中修司",
      "aliases":["修司"],
      "same_scene":true
    }
  ]
}
```

`previous_blocks/subject_block/next_blocks`はSection 10をそのまま使う。

Response:

```json
{
  "decision":"existing",
  "entity_id":5,
  "new_entity_type":null,
  "new_canonical_name":null,
  "confidence":0.94
}
```

Decision:`existing|new|unresolved`。

Validation:

- existing: `entity_id`はCandidate ID、new fields NULL。
- new: entity_id NULL、`proper_name|alias`だけ、new type/name必須。
- unresolved: entity_id/new fields全NULL。
- existing/newを採用するにはconfidence >= 09 `entity_resolution_auto_merge`。
- Threshold未満はunresolved扱い。

## 14. Speaker Attribution Contract

Prompt Instruction:

```text
subject_blockのDialogue話者をpeopleから選んでください。
previous_blocks/next_blocksは補助根拠です。
根拠が弱い場合はspeaker_entity_id=nullにしてください。
単なる交互発話だけを根拠に断定しないでください。
```

Request:

```json
{
  "previous_blocks":[
    {"block_id":53,"block_type":"narration","text":"田中が振り返った。"}
  ],
  "subject_block":{"block_id":55,"block_type":"dialogue","text":"「行こう」"},
  "next_blocks":[
    {"block_id":56,"block_type":"narration","text":"彼は歩き出した。"}
  ],
  "people":[{"entity_id":5,"canonical_name":"田中修司"}]
}
```

WindowはSection 10どおり前4/対象1/後4、同Sceneのみ。

Response:

```json
{
  "speaker_entity_id":5,
  "confidence":0.87,
  "evidence_block_ids":[53,55],
  "reason_code":"explicit_speech_tag"
}
```

`speaker_entity_id`はpeople IDまたはNULL。Evidence IDsは`previous_blocks + subject_block + next_blocks`のBlock IDだけ。Reasonは04 Enum。

## 15. Term Candidate Contract

Prompt Instruction:

```text
作品理解に固有の意味を持つ制度・技術・組織名・地名・製品・能力・歴史事象・専門語を抽出してください。
人物名はTermにしないでください。
一般語を過剰抽出しないでください。
```

Request:

```json
{
  "scene_id":3,
  "blocks":[{"block_id":60,"block_type":"narration","text":"..."}]
}
```

Response:

```json
{
  "terms":[
    {
      "block_id":60,
      "surface":"統合国家知性機構",
      "start_in_block":8,
      "end_in_block":17,
      "canonical_label_candidate":"統合国家知性機構",
      "term_type_candidate":"institution",
      "novelty_candidate":"work_specific",
      "confidence":0.94
    }
  ]
}
```

Enumは05を正本とする。Dedup Key:`(block_id,start_in_block,end_in_block)`、Duplicateはconfidence最大。

## 16. Term Resolver Candidate Shortlist / Contract

Exact Canonical/Confirmed Alias解決を05どおり先行する。

Comparison Key/SequenceMatcherはSection 13と同じ。

Candidate Pool:

1. Disabled Term除外。
2. `term_type_candidate != other`なら同Term Typeだけ。
3. 同Sceneで既にResolvedされたTermを優先。
4. `(-same_scene, -score, term_id)`でSort。
5. 最大20件。

Request:

```json
{
  "candidate":{
    "surface":"国家知性機構",
    "canonical_label_candidate":"統合国家知性機構",
    "term_type_candidate":"institution"
  },
  "previous_blocks":[{"block_id":59,"block_type":"narration","text":"..."}],
  "subject_block":{"block_id":60,"block_type":"narration","text":"...国家知性機構..."},
  "next_blocks":[{"block_id":61,"block_type":"narration","text":"..."}],
  "candidates":[
    {
      "term_id":9,
      "term_type":"institution",
      "canonical_label":"統合国家知性機構",
      "aliases":[],
      "same_scene":true
    }
  ]
}
```

ContextはSection 10どおり前2/対象1/後2、同Sceneのみ。

Response:

```json
{
  "decision":"existing",
  "term_id":9,
  "new_term_type":null,
  "new_canonical_label":null,
  "confidence":0.95
}
```

Decision:`existing|new|unresolved`。

- existing IDはCandidate内だけ。
- newはnew type/label必須。
- unresolvedはID/new fields NULL。
- existing/new採用にはconfidence >= `term_resolution_auto_merge`。
- Threshold未満はunresolved扱い。

## 17. Term Explanation Contract

Prompt Instruction:

```text
対象TermMentionの意味を読者へ説明している本文箇所だけを候補にしてください。
単なる再出現や名称の反復は説明にしないでください。
候補Spanは単一Block内に限定してください。
```

Request:

```json
{
  "term_mention_id":101,
  "term_label":"統合国家知性機構",
  "mention_block_id":60,
  "mention_start_in_block":8,
  "mention_end_in_block":17,
  "blocks":[{"block_id":58,"text":"..."},{"block_id":60,"text":"..."},{"block_id":61,"text":"..."}]
}
```

`blocks`の範囲は05を正本とする。Mention前2、後6、必要なら同Scene末尾まで。別Sceneへ拡張しない。

Response:

```json
{
  "explanations":[
    {
      "block_id":61,
      "start_in_block":2,
      "end_in_block":24,
      "explanation_kind":"definition",
      "completeness":"sufficient",
      "confidence":0.90
    }
  ]
}
```

0件可。複数Candidateは05のReductionで1件だけPersistenceする。

## 18. Scene Semantic Contract

Prompt Instruction:

```text
Scene全体の役割・雰囲気・速度・情報量・会話構造を分類してください。
function/toneは複数選択可です。
判断不能ならunclearを使用してください。
```

Request mode=`classify`:

```json
{
  "mode":"classify",
  "scene_id":3,
  "blocks":[{"block_id":40,"block_type":"narration","text":"..."}]
}
```

Response:

```json
{
  "function":[{"label":"daily","confidence":0.91}],
  "tone":[{"label":"calm","confidence":0.88}],
  "pace":{"label":"medium","confidence":0.82},
  "information_load":{"label":"low","confidence":0.80},
  "interaction":{"label":"dialogue","confidence":0.90}
}
```

Enumは06 Taxonomy。

Scene >30,000 Code PointsはBlock境界15,000 Code Points以下Chunkへ分割する。

Function/ToneはChunk結果をLabelごとmax confidenceでDeterministic Reduceする。

Pace/InformationLoad/Interactionは同Prompt IDのmode=`reduce` Callを1回行う。

Reduce Request:

```json
{
  "mode":"reduce",
  "chunks":[
    {
      "char_count":12000,
      "pace":{"label":"slow","confidence":0.8},
      "information_load":{"label":"high","confidence":0.7},
      "interaction":{"label":"dialogue","confidence":0.9}
    }
  ]
}
```

Reduce Responseは`pace/information_load/interaction`だけを同Shapeで返す。

同AnalysisRun内の全Callは同`style.scene_semantics` Prompt Versionを使用する。

## 19. Block Primary Semantic Contract

Prompt Instruction:

```text
対象Narration Blockの主機能を1つだけ分類してください。
判断不能ならunclearを使用してください。
Dialogueは入力されません。
```

Request:

```json
{
  "block_id":70,
  "text":"..."
}
```

Response:

```json
{
  "label":"exposition",
  "confidence":0.86
}
```

Enumは06 Primary Semantic。

## 20. POV Contract

Prompt Instruction:

```text
Sceneの視点形式を分類してください。
pov_entity_idは入力peopleからのみ選択してください。
特定人物へ確定できなければnullにしてください。
```

Request mode=`classify`:

```json
{
  "mode":"classify",
  "scene_id":3,
  "blocks":[{"block_id":40,"text":"..."}],
  "people":[{"entity_id":5,"canonical_name":"田中修司"}]
}
```

Response:

```json
{
  "pov_mode":"third_limited",
  "pov_entity_id":5,
  "confidence":0.84
}
```

Scene >30,000 Code PointsはScene Semanticと同Chunk境界を使う。

Chunk複数時は同Prompt ID mode=`reduce`を1回使用する。

Reduce Request:

```json
{
  "mode":"reduce",
  "people":[{"entity_id":5,"canonical_name":"田中修司"}],
  "chunks":[
    {"char_count":12000,"pov_mode":"third_limited","pov_entity_id":5,"confidence":0.84}
  ]
}
```

Responseは通常POV Responseと同Shape。

## 21. Model Call Chunking補足

- Scene Semantic/POVはSections 18/20を正本とする。
- SpeakerはSection 10固定Windowなので追加Chunkingなし。
- Entity/Term ResolverもSection 10固定Window + Candidate最大20なので追加Chunkingなし。
- Term Explanationは05 Window内だけなので追加Chunkingなし。
- Entity Mention/Term Candidate/Scene Boundaryで1 Scene Textが30,000 Code Pointsを超える場合、Block境界で最大15,000 Code Points Chunk + 前後2Block overlapを使う。
- Entity Mentionの前Scene末尾最大3Block Contextは最初のChunkだけへ付与する。
- Overlap由来Duplicateは各ContractのDedup Keyで統合する。
- Chunkingは永続Structureを変更しない。

## 22. Error / Warning

Model Client Error Code:

```text
ANALYZER_PROVIDER_UNAVAILABLE
MODEL_HTTP_ERROR
MODEL_TIMEOUT
MODEL_RESPONSE_INVALID
MODEL_CONTRACT_INVALID
```

Item Drop Warning例:

```text
MODEL_ITEM_ID_INVALID
MODEL_ITEM_SPAN_INVALID
MODEL_ITEM_ENUM_INVALID
MODEL_ITEM_DUPLICATE_REDUCED
```

Subject単位でValid Itemが残ればAnalyzer全体を即Failさせない。Run Statusは09/各Analyzer設計のPartial規則を使う。

## 23. Test

- ModelRequest/ModelClient Protocolが09と一致。
- ApiSettings default disabled/openai validation。
- API KeyなしOpenAI-compatible Local Server許可。
- Endpoint `/chat/completions`。
- Authorization HeaderはKey設定時だけ。
- temperature=0.0。
- response choices[0].message.content JSON object parse。
- HTTP Retry対象/非対象/最大1。
- Contract Repair最大1。
- Markdown/非JSON Response Repair。
- Unknown Key/Invalid Enum/Foreign ID拒否。
- Prompt Registry ID/Version固定10件。
- Entity Resolver Contextは同Scene previous<=2/subject/next<=2。
- Term Resolver Contextは同Scene previous<=2/subject/next<=2。
- Speaker Contextは同Scene previous<=4/subject Dialogue/next<=4、subject本文必須。
- Context Builderは対象BlockをExactly 1回含め、Scene境界を跨がない。
- Entity/Term Candidate Shortlist score/order/max20。
- Pronoun/Role Title new禁止。
- Resolver threshold未満unresolved。
- Term Explanation複数Candidateを05で1件Reduction。
- Scene Semantic classify/reduce同Prompt Version。
- POV classify/reduce同Prompt Version。
- >30k list-analyzer Chunk overlap/dedup。
- AnalysisRun prompt_id/version保存。

CIではFake Model Client/`httpx.MockTransport`を使い、実Providerへ接続しない。

## 24. Codex禁止事項

- OpenAI SDK追加。
- COREへhttpx/Pydantic依存追加。
- Provider固有Tools/Function Callingを独断利用。
- Prompt ID/Versionを独自命名。
- JSON ShapeをPromptごとに独自変更。
- Modelが入力外IDを返した時にそのままDB保存。
- Resolver/Speaker Context Windowを独自変更。
- Resolver候補20件上限/Sort規則を独自変更。
- Resolver Threshold未満Decisionを採用。
- Repairを1回超えて繰り返す。
- 別Modelへ自動Escalation。
- Model Callを並列化。
- CIから実Modelへ接続。
