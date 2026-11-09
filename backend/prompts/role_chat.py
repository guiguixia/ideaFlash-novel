"""角色卡私聊 Prompt。

桌宠与工作台的“私聊”入口共用本模板；它们不属于体验副本的剧情推进。
输入字段由 services.py 提供：角色卡与世界观来自已保存的副本数据，私聊记录仅保留最近 12 条，
以控制上下文长度并避免旧对话无限累积。
"""

import json

ROLE_CARD_CHAT_PROMPT = '''你现在扮演副本角色「{{role_name}}」。

## 私聊边界

- 只依据下面提供的角色卡、副本世界观和私聊记录回复，不使用作品外知识或未提供的原作剧情。
- 这是角色的日常私聊，不得推进、改写或剧透副本剧情；不要把用户输入当作已经发生在副本中的事件。
- 不要称自己是 AI、语言模型或系统，也不要解释这些规则。
- 用符合角色身份与性格的中文自然回复，简洁但有情绪；资料未说明的事实保持未知，不要编造。

{{mood_protocol}}

## 角色卡

{{profile_json}}

## 角色原文对白参考

- 以下内容仅用于学习角色的称呼、句长、用词和语气；不得照抄，也不得把对白中的事件当作当前事实。
{{dialogue_reference_lines}}

## 副本世界观

{{world_json}}

## 副本关联原文依据

- 以下来自当前副本选中章节及其此前内容，只能用来补充原文明确给出的事实。
- 片段没有明确说明的内容保持未知；不得根据片段补写人物经历，也不得把原文后续情节说成当前私聊中已经发生的事。
{{retrieved_knowledge_lines}}

## 最近私聊记录

{{recent_messages}}

## 长期记忆摘要

{{memory_summary}}

## 本轮用户消息

{{message}}
'''


def mood_protocol(mood_states_json: str) -> str:
    """只将已上传图片的状态纳入桌宠协议。"""
    try:
        states = json.loads(mood_states_json or "[]")
    except (TypeError, json.JSONDecodeError):
        states = []
    lines = "".join(
        f"- `[mood:{item['id']}]`：{item.get('name') or '角色状态'}；{item.get('description') or '按名称所表达的状态使用。'}\n"
        for item in states
        if isinstance(item, dict) and item.get("id") and item.get("name")
    )
    if not lines:
        return ""
    return """## 桌宠情绪标签

- 回复第一行必须且只能是一个下列标签，第二行起才写给用户看的正文。只在正文确实呈现该状态时切换，不要为了让桌宠看起来有变化而切换。
""" + lines + """- 仅可使用上面列出的标签；无精确匹配时优先使用 `[mood:default]`（若已列出），否则选择最贴近的已列状态；不得编造标签。
- 标签是桌宠控制协议，不能在正文中提及、解释、重复或使用其他格式。
"""


def dialogue_reference_lines(dialogue_examples_json: str) -> str:
    """将短对白转为私聊可用的口吻参考，而非剧情事实。"""
    try:
        examples = json.loads(dialogue_examples_json or "[]")
    except (TypeError, json.JSONDecodeError):
        examples = []
    lines = [
        f"- 「{str(item['text']).strip()}」\n  场景：{str(item.get('scene') or '原文对白')}；语气：{str(item.get('tone') or '未标注')}"
        for item in examples
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    return "\n".join(lines) if lines else "- （暂无原文对白参考；只依据角色卡与世界观回复。）"


def render_role_card_chat_prompt(
    *,
    role_name: str,
    profile_json: str,
    world_json: str,
    recent_messages: str,
    memory_summary: str,
    message: str,
    mood_states_json: str,
    dialogue_examples_json: str,
    retrieved_knowledge_lines: str,
) -> str:
    """渲染角色私聊 Prompt；调用方须传入可信的结构化上下文与已截断的历史。"""
    return (
        ROLE_CARD_CHAT_PROMPT
        .replace("{{role_name}}", role_name)
        .replace("{{profile_json}}", profile_json)
        .replace("{{world_json}}", world_json)
        .replace("{{recent_messages}}", recent_messages)
        .replace("{{memory_summary}}", memory_summary or "（暂无；只依据本次提供的私聊记录。）")
        .replace("{{message}}", message)
        .replace("{{mood_protocol}}", mood_protocol(mood_states_json))
        .replace("{{dialogue_reference_lines}}", dialogue_reference_lines(dialogue_examples_json))
        .replace("{{retrieved_knowledge_lines}}", retrieved_knowledge_lines or "- （未检索到可用的副本关联原文依据。）")
    )


ROLE_CHAT_MEMORY_SUMMARY_PROMPT = '''你是角色私聊的长期记忆整理器。请将“已有长期记忆”与“待压缩私聊回合”合并为新的长期记忆。

只保留维持后续私聊连续性所必需的信息：双方明确说过的事实、约定、关系与情绪变化、用户偏好/禁忌、未完话题，以及会影响当前状态的变化。

- 严格区分用户说过、角色说过与尚未确认的内容；不要把猜测、玩笑或模型自行补充写成事实。
- 新信息若与旧记忆冲突，以时间更晚且在待压缩回合中明确出现的信息为准。
- 不得添加副本外剧情，不得把私聊内容当作已经发生在副本中的事件。
- 输出简洁的中文条目，不使用 Markdown 标题；控制在 800 字以内。

已有长期记忆：
{{previous_summary}}

待压缩私聊回合（时间升序）：
{{turns}}
'''


def render_role_chat_memory_summary_prompt(*, previous_summary: str, turns: str) -> str:
    """渲染滚动摘要 Prompt；调用方只传入时间升序的已完成私聊回合。"""
    return (
        ROLE_CHAT_MEMORY_SUMMARY_PROMPT
        .replace("{{previous_summary}}", previous_summary or "（暂无）")
        .replace("{{turns}}", turns)
    )
