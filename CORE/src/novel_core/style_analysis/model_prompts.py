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
        "style.scene_boundary", 1, "Sceneの明確な境界候補だけを返してください。"
    ),
    PromptDefinition(
        "style.entity_mentions",
        1,
        "本文に明示されたEntity Mentionだけを抽出してください。",
    ),
    PromptDefinition(
        "style.entity_resolution", 1, "入力候補からEntityの解決結果を返してください。"
    ),
    PromptDefinition(
        "style.speaker_attribution",
        1,
        "subject_blockのDialogue話者をpeopleから選んでください。",
    ),
    PromptDefinition(
        "style.term_candidates", 1, "作品理解に固有のTerm候補だけを抽出してください。"
    ),
    PromptDefinition(
        "style.term_resolution", 1, "入力候補からTermの解決結果を返してください。"
    ),
    PromptDefinition(
        "style.term_explanation",
        1,
        "Termを説明している単一Blockの本文箇所だけを返してください。",
    ),
    PromptDefinition(
        "style.scene_semantics",
        1,
        "Sceneのfunction、tone、pace、information_load、interactionを分類してください。",
    ),
    PromptDefinition(
        "style.block_semantic", 1, "Narration Blockの主機能を1つだけ分類してください。"
    ),
    PromptDefinition("style.pov", 1, "Sceneの視点形式を分類してください。"),
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
