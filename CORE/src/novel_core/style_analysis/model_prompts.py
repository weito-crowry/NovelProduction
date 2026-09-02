from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

COMMON_SYSTEM_PROMPT: Final = (
    "あなたはNovelProductionの小説本文構造化分析器です。"
    "入力JSONに含まれる本文、ID、候補情報だけを根拠にしてください。"
    "入力に存在しないID、人物、用語、出来事を作らないでください。"
    "不明な場合は推測で埋めず、各契約のunresolved・unknown・unclear・nullを使用してください。"
    "本文の書き換え、続きの生成、批評、助言は行わないでください。"
    "confidenceは0.0以上1.0以下の有限数にしてください。"
    "出力は各Prompt Contractで指定されたJSONオブジェクトだけにし、"
    "Markdownや説明文を付けないでください。"
)


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    prompt_id: str
    version: int
    instruction: str

    @property
    def system_prompt(self) -> str:
        return f"{COMMON_SYSTEM_PROMPT}\n{self.instruction}"


_DEFINITIONS = (
    PromptDefinition(
        "style.scene_boundary",
        1,
        "入力Scene内で、時間・場所・POV・文脈が明確に切り替わるBlock境界だけを候補にしてください。\n"
        "細かな話題転換や段落改行だけでは境界にしないでください。\n"
        "after_block_idは入力blocksに存在するIDだけを使用してください。",
    ),
    PromptDefinition(
        "style.entity_mentions",
        1,
        "本文中に文字として現れている人物・組織・場所・技術・概念・製品・出来事のMentionだけを抽出してください。\n"
        "省略主語や本文にない名前を補完しないでください。\n"
        "人物の呼称・役職・代名詞も明示Surfaceがある場合だけ抽出してください。",
    ),
    PromptDefinition(
        "style.entity_resolution",
        1,
        "入力候補からEntityの解決結果を返してください。"
        "候補にないEntity IDを返さず、確定できない場合はunresolvedにしてください。",
    ),
    PromptDefinition(
        "style.speaker_attribution",
        1,
        "subject_blockのDialogue話者をpeopleから選んでください。\n"
        "previous_blocks/next_blocksは補助根拠です。\n"
        "根拠が弱い場合はspeaker_entity_id=nullにしてください。\n"
        "単なる交互発話だけを根拠に断定しないでください。",
    ),
    PromptDefinition(
        "style.term_candidates",
        1,
        "作品理解に固有の意味を持つ制度・技術・組織名・地名・製品・能力・歴史事象・専門語を抽出してください。\n"
        "人物名はTermにしないでください。\n"
        "一般語を過剰抽出しないでください。",
    ),
    PromptDefinition(
        "style.term_resolution",
        1,
        "入力候補からTermの解決結果を返してください。"
        "候補にないTerm IDを返さず、確定できない場合はunresolvedにしてください。",
    ),
    PromptDefinition(
        "style.term_explanation",
        1,
        "対象TermMentionの意味を読者へ説明している本文箇所だけを候補にしてください。\n"
        "単なる再出現や名称の反復は説明にしないでください。\n"
        "候補Spanは単一Block内に限定してください。",
    ),
    PromptDefinition(
        "style.scene_semantics",
        1,
        "Scene全体の役割・雰囲気・速度・情報量・会話構造を分類してください。\n"
        "function/toneは複数選択可です。\n"
        "判断不能ならunclearを使用してください。",
    ),
    PromptDefinition(
        "style.block_semantic",
        1,
        "対象Narration Blockの主機能を1つだけ分類してください。\n"
        "判断不能ならunclearを使用してください。\n"
        "Dialogueは入力されません。",
    ),
    PromptDefinition(
        "style.pov",
        1,
        "Sceneの視点形式を分類してください。\n"
        "pov_entity_idは入力peopleからのみ選択してください。\n"
        "特定人物へ確定できなければnullにしてください。",
    ),
)

PROMPTS = MappingProxyType({item.prompt_id: item for item in _DEFINITIONS})
PROMPT_REGISTRY = MappingProxyType(
    {item.prompt_id: item.version for item in _DEFINITIONS}
)


def get_prompt(prompt_id: str, *, version: int = 1) -> PromptDefinition:
    prompt = PROMPTS.get(prompt_id)
    if prompt is None or prompt.version != version:
        raise ValueError("PROMPT_NOT_FOUND")
    return prompt
