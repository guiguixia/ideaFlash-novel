"""角色形象状态的可用性规则。

状态可预置，但只有上传了图片的状态才会参与模型选择与运行时展示。
"""

FIXED_EMOTION_SLOTS = ("default", "thinking", "puzzled", "happy", "low", "taunting")
FIXED_EMOTION_META = {
    "default": ("默认", "角色的默认外貌与日常神态"),
    "thinking": ("思考", "目光沉静，像在斟酌或推演"),
    "puzzled": ("疑惑", "微微蹙眉，带着不解与迟疑"),
    "happy": ("开心", "神情放松，流露轻快与愉悦"),
    "low": ("低落", "目光低垂，情绪低落或压抑"),
    "taunting": ("嘲讽", "唇角微扬，带着轻蔑、戏谑或挑衅"),
}


def configured_emotion_states(card) -> list[dict]:
    """仅返回有对应图片的固定或自定义状态。"""
    images = dict(card.emotion_images or {})
    if card.image_path:
        images["default"] = card.image_path
    descriptions = dict(card.emotion_descriptions or {})
    states = [
        {"id": slot, "name": FIXED_EMOTION_META[slot][0], "description": str(descriptions.get(slot) or FIXED_EMOTION_META[slot][1])}
        for slot in FIXED_EMOTION_SLOTS
        if images.get(slot)
    ]
    for item in card.custom_emotions or []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("image_path"):
            continue
        states.append({"id": str(item["id"]), "name": str(item.get("name") or "自定义状态"), "description": str(item.get("description") or "按名称所表达的状态使用。")})
    return states


def configured_mood_ids(card) -> set[str]:
    return {str(item["id"]) for item in configured_emotion_states(card)}


def valid_configured_mood(card, value: str) -> str:
    ids = configured_mood_ids(card)
    if value in ids:
        return value
    return "default" if "default" in ids else ""
