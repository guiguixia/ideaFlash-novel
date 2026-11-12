#!/usr/bin/env python3
"""角色正视主立绘文生图实验：仅写入本目录 output，不触碰业务数据库或接口。"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import mimetypes
import os
import time
import zlib
from datetime import datetime
from pathlib import Path

import httpx


LAB_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = LAB_DIR / "output"
VIEWS = (("front", "正面"),)


def aliyun_api_key() -> str:
    """优先允许命令行或环境覆盖；默认只读取本机未纳管的实验常量。"""
    constants = LAB_DIR.parents[1] / ".experiment-private" / "aliyun_constants.py"
    if not constants.is_file():
        return ""
    spec = importlib.util.spec_from_file_location("aliyun_experiment_constants", constants)
    if not spec or not spec.loader:
        return ""
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(getattr(module, "ALIYUN_API_KEY", ""))
SCENES = {
    "A": {
        "title": "后山初遇药老",
        "prompt": """Use case: illustration-story
Asset type: 剧情体验中的关键剧情场景图
Input image: 参考图中的少年角色；必须作为画面中唯一清晰的人物主体。
Scene/backdrop: 乌坦城后山的悬崖边，傍晚，山雾缭绕，远处是幽暗辽阔的魔兽山脉。
Subject: 少年刚承受退婚羞辱，独自站在岩石边，微微低头看向右手佩戴的一枚黑色古朴戒指；戒指旁只有一缕极淡、神秘的苍老灵魂光雾，不要完整出现第二个人物。
Style/medium: 高质量中国动漫游戏剧情插画，细腻赛璐璐上色。
Composition/framing: 16:9 横向中景，人物完整可见，人物置于画面右侧，左侧留出山雾与远山。
Lighting/mood: 月前暮色与戒指微光，悲愤、孤独又神秘。
Constraints: 严格保持参考图中的同一人物脸型、发型、发色、服装主色、年龄和动漫画风；不要文字、标志、水印、对话框；不要额外清晰人物。""",
    },
    "B": {
        "title": "测试广场的陨落天才",
        "prompt": """Use case: illustration-story
Asset type: 剧情体验中的关键剧情场景图
Input image: 参考图中的少年角色；必须作为画面中心的唯一清晰人物主体。
Scene/backdrop: 古风玄幻家族的年度测试广场，巨大的黑色测试石碑矗立在少年身后，石砖地面与高台，周围围着模糊的族人剪影。
Subject: 少年将手从测试石碑收回，神情克制而倔强，四周人群在远处窃窃私语、嘲笑，但不得出现可读文字。
Style/medium: 高质量中国动漫游戏剧情插画，细腻赛璐璐上色。
Composition/framing: 16:9 横向全身中景，少年居中偏右，石碑清晰但无任何文字，围观者仅作景深背景。
Lighting/mood: 阴天散射光，压抑、被审视、仍不服输。
Constraints: 严格保持参考图中的同一人物脸型、发型、发色、服装主色、年龄和动漫画风；不要文字、标志、水印、对话框；不要把围观者画成清晰主要角色。""",
    },
    "C": {
        "title": "大厅立下三年之约",
        "prompt": """Use case: illustration-story
Asset type: 剧情体验中的关键剧情场景图
Input image: 参考图中的少年角色；必须作为画面中最清晰、最重要的人物主体。
Scene/backdrop: 古风玄幻家族的迎客大厅，石柱、木质高台、打开的大门，空间庄严开阔。
Subject: 少年面对大厅另一侧的一位模糊年轻女子与两位模糊长者，攥紧拳头、昂首站立，像是在郑重立下未来之约。对方只作为远景剪影与服饰色块，不抢主体。
Style/medium: 高质量中国动漫游戏剧情插画，细腻赛璐璐上色。
Composition/framing: 16:9 横向中景，少年在画面左前方且最清晰，对方位于右后方，形成强烈对峙关系。
Lighting/mood: 门外阳光斜照，克制、屈辱、决绝与热血。
Constraints: 严格保持参考图中的同一人物脸型、发型、发色、服装主色、年龄和动漫画风；不要文字、标志、水印、对话框；不要让其他角色比少年更清晰或更醒目。""",
    },
}


def load_character(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not str(data.get("name")) or not str(data.get("appearance")):
        raise ValueError("角色 JSON 至少需要 name 与 appearance")
    return data


def prompt_for(character: dict, view_name: str) -> str:
    details = [
        f"角色名：{character['name']}",
        f"身份与气质：{character.get('identity') or character.get('personality') or '未提供'}",
        f"外貌与服饰：{character['appearance']}",
        f"当前状态：{character.get('currentState') or '平静站立'}",
        f"画风：{character.get('visualStyle') or '高质量中国动漫游戏角色设定图，细腻赛璐璐上色'}",
        f"构图：全身人物 {view_name}，正交角色设定图，纯净浅色背景，人物完整可见，保持服装、发型、年龄和配色一致。",
        "画面中不要文字、标签、签名、对话框、边框、水印；不要额外人物。",
    ]
    return "\n".join(details)


def portrait_prompt(user_prompt: str, reference_count: int) -> str:
    reference_list = "、".join(f"图 {index}" for index in range(1, reference_count + 1))
    return f"""Use case: character-asset
Asset type: 可复用于桌宠、角色卡与剧情插画参考的单角色正面立绘。
Input images: {reference_list} 为同一角色的参考资料。综合保留其中可识别的脸型、发型、发色、年龄感、服装款式、配色、饰品与画风；不要把多张图中的人物合成多个角色。
Character brief: {user_prompt.strip()}
Primary request: 只生成一名角色，完整全身，正面朝向镜头，站立姿势自然且对称，双手和双脚完整可见，人物居中；服装和人物本体是唯一内容。
Background: 必须输出真正的透明背景（带 Alpha 通道），不画场景、家具、地面、天空、光晕、投影或装饰边框；人物边缘清晰，便于直接叠加在其他剧情背景上。
Style/medium: 保持参考图的动漫角色设定画风，细腻赛璐璐上色，高质量角色立绘。
Strict output rule: 成图只能包含“单个人物 + 其服装、发型、饰品”，除这一个角色外画面中必须没有任何可识别内容。
Constraints: 禁止所有文字（包括标题、姓名、标签、签名、标志、水印）、对话框、边框；禁止额外人物、宠物、武器、特效、背景道具；不要裁切、残缺肢体、侧身、背身、夸张透视。"""


def png_has_transparent_pixels(content: bytes, content_type: str) -> bool:
    """检查 PNG 是否含实际透明像素，而不是只检查是否声明了 Alpha 通道。"""
    if "png" not in content_type.lower() or content[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset + 12 <= len(content):
        length = int.from_bytes(content[offset:offset + 4], "big")
        kind = content[offset + 4:offset + 8]
        chunk = content[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR" and len(chunk) == 13:
            width, height = int.from_bytes(chunk[:4], "big"), int.from_bytes(chunk[4:8], "big")
            bit_depth, color_type, interlace = chunk[8], chunk[9], chunk[12]
        elif kind == b"IDAT":
            compressed.extend(chunk)
        elif kind == b"IEND":
            break
    if not width or not height or bit_depth != 8 or color_type not in {4, 6} or interlace != 0:
        return False
    channels = 2 if color_type == 4 else 4
    row_size = width * channels
    try:
        raw = zlib.decompress(compressed)
    except zlib.error:
        return False
    previous = bytearray(row_size)
    position = 0
    for _ in range(height):
        if position + row_size + 1 > len(raw):
            return False
        filter_type, encoded = raw[position], raw[position + 1:position + row_size + 1]
        position += row_size + 1
        row = bytearray(encoded)
        for index, value in enumerate(row):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + up) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                p = left + up - upper_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                row[index] = (value + predictor) & 0xFF
            elif filter_type != 0:
                return False
        alpha_index = 1 if channels == 2 else 3
        if any(row[index] < 255 for index in range(alpha_index, row_size, channels)):
            return True
        previous = row
    return False


def dashscope_generate(client: httpx.Client, base_url: str, api_key: str, model: str, prompt: str, size: str, negative_prompt: str) -> tuple[bytes, str]:
    submitted = client.post(
        base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}", "X-DashScope-Async": "enable"},
        json={"model": model, "input": {"prompt": prompt, "negative_prompt": negative_prompt}, "parameters": {"size": size, "n": 1, "watermark": False}},
    )
    submitted.raise_for_status()
    task_id = submitted.json().get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"百炼未返回 task_id：{submitted.text[:500]}")
    task_url = base_url.rstrip("/").rsplit("/services/", 1)[0] + f"/tasks/{task_id}"
    for _ in range(90):
        status = client.get(task_url, headers={"Authorization": f"Bearer {api_key}"})
        status.raise_for_status()
        output = status.json().get("output", {})
        state = output.get("task_status")
        if state == "SUCCEEDED":
            url = (output.get("results") or [{}])[0].get("url")
            if not url:
                raise RuntimeError("百炼任务成功但未返回图片 URL")
            image = client.get(url)
            image.raise_for_status()
            return image.content, image.headers.get("content-type", "image/png").split(";", 1)[0]
        if state in {"FAILED", "CANCELED"}:
            raise RuntimeError(f"百炼任务失败：{output.get('message') or output}")
        time.sleep(2)
    raise TimeoutError("百炼文生图超过 180 秒仍未完成")


def image_url_from_response(data: dict) -> str:
    output = data.get("output") or data
    for choice in output.get("choices") or []:
        for part in choice.get("message", {}).get("content") or []:
            if part.get("type") == "image" and part.get("image"):
                return str(part["image"])
    raise RuntimeError(f"百炼任务成功但未返回图片 URL：{str(data)[:500]}")


def dashscope_edit(client: httpx.Client, base_url: str, api_key: str, model: str, prompt: str, source: Path | list[Path], negative_prompt: str, size: str = "1K") -> tuple[bytes, str]:
    sources = source if isinstance(source, list) else [source]
    references = []
    for item in sources:
        mime_type = mimetypes.guess_type(item.name)[0] or "image/png"
        references.append({"image": f"data:{mime_type};base64,{base64.b64encode(item.read_bytes()).decode('ascii')}"})
    parameters = {"watermark": False, "n": 1, "size": size}
    if model.startswith("wan2.6-"):
        parameters.update({"negative_prompt": negative_prompt, "prompt_extend": True, "enable_interleave": False})
    submitted = client.post(
        base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}", "X-DashScope-Async": "enable"},
        json={"model": model, "input": {"messages": [{"role": "user", "content": [{"text": prompt}, *references]}]}, "parameters": parameters},
    )
    submitted.raise_for_status()
    task_id = submitted.json().get("output", {}).get("task_id") or submitted.json().get("task_id")
    if not task_id:
        return download_image(client, image_url_from_response(submitted.json()))
    task_url = base_url.rstrip("/").rsplit("/services/", 1)[0] + f"/tasks/{task_id}"
    for _ in range(90):
        status = client.get(task_url, headers={"Authorization": f"Bearer {api_key}"})
        status.raise_for_status()
        data = status.json(); output = data.get("output") or data; state = output.get("task_status") or data.get("status")
        if state == "SUCCEEDED":
            return download_image(client, image_url_from_response(data))
        if state in {"FAILED", "CANCELED"}:
            raise RuntimeError(f"百炼图像编辑失败：{output.get('message') or data.get('message') or output}")
        time.sleep(2)
    raise TimeoutError("百炼图像编辑超过 180 秒仍未完成")


def download_image(client: httpx.Client, url: str) -> tuple[bytes, str]:
    image = client.get(url)
    image.raise_for_status()
    return image.content, image.headers.get("content-type", "image/png").split(";", 1)[0]


def gemini_generate(client: httpx.Client, base_url: str, api_key: str, model: str, prompt: str, aspect_ratio: str) -> tuple[bytes, str]:
    response = client.post(
        f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key},
        json={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect_ratio}}},
    )
    response.raise_for_status()
    for candidate in response.json().get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            data = part.get("inlineData") or part.get("inline_data")
            if data and data.get("data"):
                return base64.b64decode(data["data"]), data.get("mimeType") or data.get("mime_type") or "image/png"
    raise RuntimeError(f"Gemini 未返回图片：{response.text[:500]}")


def provider_config(args) -> tuple[str, str, str]:
    if args.provider == "dashscope":
        return args.base_url or os.getenv("IMAGE_LAB_DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"), args.api_key or os.getenv("IMAGE_LAB_DASHSCOPE_API_KEY", "") or aliyun_api_key(), args.model or "wan2.2-t2i-flash"
    return args.base_url or os.getenv("IMAGE_LAB_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"), args.api_key or os.getenv("IMAGE_LAB_GEMINI_API_KEY", ""), args.model or "gemini-3.1-flash-image"


def run(args) -> None:
    base_url, api_key, model = provider_config(args)
    if args.portrait_source:
        if args.provider != "dashscope":
            raise ValueError("当前多参考图角色形象实验仅接入百炼 wan2.7-image")
        sources = [Path(value) for value in args.portrait_source]
        if not 1 <= len(sources) <= 3 or not all(source.is_file() for source in sources):
            raise ValueError("--portrait-source 需要传入 1–3 张存在的本地参考图")
        if not args.portrait_prompt or not args.portrait_prompt.strip():
            raise ValueError("多参考图角色形象实验需要 --portrait-prompt 说明人物与服装设定")
        base_url = args.base_url or os.getenv(
            "IMAGE_LAB_DASHSCOPE_EDIT_BASE_URL",
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation",
        )
        model = args.model or "wan2.7-image"
        prompt = portrait_prompt(args.portrait_prompt, len(sources))
        print(json.dumps({
            "provider": args.provider,
            "baseUrl": base_url,
            "model": model,
            "mode": "portrait_references",
            "sources": [str(source) for source in sources],
            "transparentBackgroundRequested": True,
        }, ensure_ascii=False, indent=2))
        if args.dry_run:
            print(f"\n--- portrait prompt ---\n{prompt}")
            return
        if not api_key:
            raise RuntimeError("缺少 API Key；请通过 IMAGE_LAB_DASHSCOPE_API_KEY 环境变量传入")
        run_dir = OUTPUT_DIR / datetime.now().strftime("portrait-%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "request.json").write_text(json.dumps({
            "provider": args.provider,
            "baseUrl": base_url,
            "model": model,
            "sources": [str(source) for source in sources],
            "prompt": prompt,
            "transparentBackgroundRequested": True,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        negative = "场景，背景，地面，天空，室内，投影，光晕，文字，水印，签名，边框，额外人物，宠物，道具，裁切，残缺肢体，侧脸，背影，夸张透视，低清晰度"
        with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
            content, content_type = dashscope_edit(client, base_url, api_key, model, prompt, sources, negative, args.portrait_size)
        suffix = ".jpg" if "jpeg" in content_type else ".png"
        output_path = run_dir / f"front-portrait{suffix}"
        output_path.write_bytes(content)
        has_alpha = png_has_transparent_pixels(content, content_type)
        (run_dir / "result.json").write_text(json.dumps({
            "image": output_path.name,
            "contentType": content_type,
            "transparentBackgroundRequested": True,
            "transparentBackgroundVerified": has_alpha,
            "note": "模型未返回实际透明像素时，图片仍可作为剧情参考；用于桌宠叠加前需要再做一次抠图。" if not has_alpha else "已检测到实际透明像素。",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"完成：{run_dir}")
        print("透明背景：已检测到实际透明像素" if has_alpha else "透明背景：模型未返回实际透明像素，已在 result.json 标记")
        return
    character = load_character(Path(args.character))
    if args.scene_trio:
        if args.provider != "dashscope":
            raise ValueError("当前三角色剧情图实验仅接入百炼 wan2.7-image")
        sources = [Path(value) for value in args.scene_trio]
        if len(sources) != 3 or not all(source.is_file() for source in sources):
            raise ValueError("--scene-trio 需要按顺序传入三张存在的参考图：萧炎图 薰儿图 纳兰嫣然图")
        base_url = args.base_url or os.getenv("IMAGE_LAB_DASHSCOPE_EDIT_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation")
        model = args.model or "wan2.7-image"
        prompt = """Use case: illustration-story
Asset type: 剧本刷剧情体验中的沉浸式关键剧情插画，彩色中国动漫漫画分镜风。
Input images: 图 1 是萧炎，图 2 是萧薰儿，图 3 是纳兰嫣然。三人必须分别严格保持各自的脸型、发型、发色、年龄感、服装款式与服装主色；三张图对应三个不同人物，绝不能混合身份或服装。
Scene/backdrop: 乌坦城萧家的迎客大厅，石柱、木质长桌、族人和长者只作为远处模糊剪影，金色斜阳从敞开的门扉照入。
Primary request: 重现退婚剧情的高潮。萧炎位于左前方、愤怒却克制地将一张无字的契约按在长桌上；纳兰嫣然位于右前方，震惊、倔强地与他相望；萧薰儿站在萧炎身后半步，神情清冷淡然、安静支持他。三人都是清晰可见的主要角色，萧炎与纳兰嫣然的对峙是视觉焦点，薰儿不能被遮挡或变成背景人物。
Style/medium: 高质量中国玄幻彩色漫画分镜，细腻赛璐璐上色、干净墨线、少量速度线与戏剧留白。
Composition/framing: 16:9 横向全身或膝上中景，萧炎在左、纳兰嫣然在右、薰儿在左后；三个人物均完整可见，视线张力在画面中央交汇。
Lighting/mood: 金色门光与厅内冷影形成对比，屈辱、决绝、克制守护与少年热血。
Strict output rule: 画面只出现三位指定主角与模糊无面孔的远景剪影；禁止一切可读文字，包括契约文字、标题、标签、签名、标志、水印、对话框。
Constraints: 不要血迹、伤口、暴力画面；不要额外清晰人物；不要改变三位参考角色的性别、服装或发色；不要让薰儿消失、被裁切或遮挡。"""
        print(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "mode": "scene_trio", "sources": [str(source) for source in sources]}, ensure_ascii=False, indent=2))
        if args.dry_run:
            print(f"\n--- 三角色退婚剧情 ---\n{prompt}")
            return
        if not api_key:
            raise RuntimeError("缺少 API Key；请通过 IMAGE_LAB_DASHSCOPE_API_KEY 环境变量传入")
        run_dir = OUTPUT_DIR / datetime.now().strftime("scene-trio-%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "request.json").write_text(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "sources": [str(source) for source in sources], "prompt": prompt}, ensure_ascii=False, indent=2), encoding="utf-8")
        with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
            content, content_type = dashscope_edit(client, base_url, api_key, model, prompt, sources, "", args.scene_size)
        suffix = ".jpg" if "jpeg" in content_type else ".png"
        (run_dir / f"retirement-trio-comic{suffix}").write_bytes(content)
        print(f"完成：{run_dir}")
        return
    if args.scene_duo:
        if args.provider != "dashscope":
            raise ValueError("当前双角色剧情图实验仅接入百炼 wan2.6-image")
        sources = [Path(value) for value in args.scene_duo]
        if len(sources) != 2 or not all(source.is_file() for source in sources):
            raise ValueError("--scene-duo 需要按顺序传入两张存在的参考图：萧炎图 纳兰嫣然图")
        base_url = args.base_url or os.getenv("IMAGE_LAB_DASHSCOPE_EDIT_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation")
        model = args.model or "wan2.6-image"
        prompt = """Use case: illustration-story
Asset type: 剧情体验中的关键剧情插画，彩色漫画分镜风。
Input images: 图 1 是萧炎，图 2 是纳兰嫣然；两人必须分别严格保持各自的脸型、发型、发色、服装主色和年龄特征。
Scene/backdrop: 古风玄幻家族的迎客大厅，石柱、木质高台与敞开的巨大门扉，金色斜阳自门外照入。
Primary request: 重现“大厅立下三年之约”的对峙瞬间。萧炎位于画面左前方，攥紧拳头、目光坚定；纳兰嫣然位于右前方，与他正面相望，神情克制而冷静。两人都是同等重要的画面主角。
Style/medium: 高质量中国玄幻彩色漫画分镜，粗细变化的墨线、网点阴影、少量速度线与对峙留白，电影感构图。
Composition/framing: 16:9 横向双人全身或膝上中景，二人各占画面一侧，视线与张力在画面中央交汇；背景只保留模糊长者剪影，不增加清晰第三主角。
Lighting/mood: 金色门光与厅内冷影形成反差，屈辱、决绝、热血的戏剧张力。
Constraints: 不要文字、对话框、标志、水印、血迹、伤口、暴力画面；不要改变两位参考角色的性别、服装或发色；不要把任何一方画成背景人物。"""
        print(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "mode": "scene_duo", "sources": [str(source) for source in sources]}, ensure_ascii=False, indent=2))
        if args.dry_run:
            print(f"\n--- C 双主角漫画分镜 ---\n{prompt}")
            return
        if not api_key:
            raise RuntimeError("缺少 API Key；请通过 IMAGE_LAB_DASHSCOPE_API_KEY 环境变量传入")
        run_dir = OUTPUT_DIR / datetime.now().strftime("scene-duo-%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "request.json").write_text(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "sources": [str(source) for source in sources], "prompt": prompt}, ensure_ascii=False, indent=2), encoding="utf-8")
        with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
            content, content_type = dashscope_edit(client, base_url, api_key, model, prompt, sources, "文字，水印，签名，血迹，伤口，暴力画面，额外清晰主角，裁切，残缺肢体，低清晰度", args.scene_size)
        suffix = ".jpg" if "jpeg" in content_type else ".png"
        (run_dir / f"C-duo-comic{suffix}").write_bytes(content)
        print(f"完成：{run_dir}")
        return
    if args.scene_batch:
        if args.provider != "dashscope":
            raise ValueError("当前剧情场景图实验仅接入百炼 wan2.6-image")
        if not args.scene_source:
            raise ValueError("至少提供一个 --scene-source 名称=参考图路径")
        sources = {}
        for value in args.scene_source:
            name, separator, raw_path = value.partition("=")
            source = Path(raw_path)
            if not separator or not name or not source.is_file():
                raise ValueError("--scene-source 格式应为 名称=/绝对或相对参考图路径，且图片必须存在")
            sources[name] = source
        base_url = args.base_url or os.getenv("IMAGE_LAB_DASHSCOPE_EDIT_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation")
        model = args.model or "wan2.6-image"
        selected = tuple(args.scene_batch)
        invalid = [key for key in selected if key not in SCENES]
        if invalid:
            raise ValueError(f"未知场景：{', '.join(invalid)}；可选 A、B、C")
        manifest = {key: {"title": SCENES[key]["title"], "prompt": SCENES[key]["prompt"]} for key in selected}
        print(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "mode": "scene_batch", "scenes": list(selected), "sources": {name: str(source) for name, source in sources.items()}}, ensure_ascii=False, indent=2))
        if args.dry_run:
            for key in selected:
                print(f"\n--- {key}: {SCENES[key]['title']} ---\n{SCENES[key]['prompt']}")
            return
        if not api_key:
            raise RuntimeError("缺少 API Key；请通过 IMAGE_LAB_DASHSCOPE_API_KEY 环境变量传入")
        run_dir = OUTPUT_DIR / datetime.now().strftime("scene-%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "request.json").write_text(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "scenes": manifest, "sources": {name: str(source) for name, source in sources.items()}}, ensure_ascii=False, indent=2), encoding="utf-8")
        negative = character.get("negativePrompt") or "文字，水印，签名，清晰的额外主角，裁切，残缺肢体，低清晰度"
        with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
            for scene_key in selected:
                for source_name, source in sources.items():
                    print(f"正在生成 {scene_key}-{source_name}…")
                    content, content_type = dashscope_edit(client, base_url, api_key, model, SCENES[scene_key]["prompt"], source, negative, args.scene_size)
                    suffix = ".jpg" if "jpeg" in content_type else ".png"
                    (run_dir / f"{scene_key}-{source_name}{suffix}").write_bytes(content)
        print(f"完成：{run_dir}")
        return
    if args.edit_source:
        if args.provider != "dashscope":
            raise ValueError("当前图像编辑实验仅接入百炼 wan2.6-image")
        source = Path(args.edit_source)
        if not source.is_file():
            raise FileNotFoundError(f"未找到参考图：{source}")
        base_url = args.base_url or os.getenv("IMAGE_LAB_DASHSCOPE_EDIT_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation")
        model = args.model or "wan2.6-image"
        prompt = args.edit_prompt or "严格保持参考图中的同一人物、脸型、发型、深蓝色服装、腰带、护腕、全身正面站姿和动漫设定图画风不变。只将神情修改为自然明朗的开心微笑，眼神温暖放松。不要改变人物身份、服装细节、构图、背景和比例。"
        print(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "mode": "image_edit", "source": str(source)}, ensure_ascii=False, indent=2))
        if args.dry_run:
            print(f"\n--- edit prompt ---\n{prompt}")
            return
        if not api_key:
            raise RuntimeError("缺少 API Key；请通过 IMAGE_LAB_DASHSCOPE_API_KEY 环境变量传入")
        run_dir = OUTPUT_DIR / datetime.now().strftime("edit-%Y%m%d-%H%M%S"); run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "request.json").write_text(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "source": str(source), "prompt": prompt}, ensure_ascii=False, indent=2), encoding="utf-8")
        negative = character.get("negativePrompt") or "文字，水印，签名，多余人物，裁切，残缺肢体，低清晰度"
        with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
            content, content_type = dashscope_edit(client, base_url, api_key, model, prompt, source, negative)
        suffix = ".jpg" if "jpeg" in content_type else ".png"; (run_dir / f"{source.stem}-happy{suffix}").write_bytes(content)
        print(f"完成：{run_dir}")
        return
    prompts = {key: prompt_for(character, title) for key, title in VIEWS}
    print(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "views": list(prompts)}, ensure_ascii=False, indent=2))
    if args.dry_run:
        for key, prompt in prompts.items():
            print(f"\n--- {key} ---\n{prompt}")
        return
    if not api_key:
        raise RuntimeError("缺少 API Key；请通过对应 IMAGE_LAB_*_API_KEY 环境变量传入，不要写入文件")
    run_dir = OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.json").write_text(json.dumps({"provider": args.provider, "baseUrl": base_url, "model": model, "character": character, "prompts": prompts}, ensure_ascii=False, indent=2), encoding="utf-8")
    negative = character.get("negativePrompt") or "文字，水印，签名，多余人物，裁切，残缺肢体，低清晰度"
    with httpx.Client(timeout=60, trust_env=False, follow_redirects=True) as client:
        for key, _ in VIEWS:
            print(f"正在生成 {key}…")
            if args.provider == "dashscope":
                content, content_type = dashscope_generate(client, base_url, api_key, model, prompts[key], args.size, negative)
            else:
                content, content_type = gemini_generate(client, base_url, api_key, model, prompts[key], args.aspect_ratio)
            suffix = ".jpg" if "jpeg" in content_type else ".png"
            (run_dir / f"{key}{suffix}").write_bytes(content)
    print(f"完成：{run_dir}")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="角色文本描述 → 正视主立绘实验（不接入业务代码）")
    command.add_argument("--provider", choices=("dashscope", "gemini"), default="dashscope")
    command.add_argument("--model", help="覆盖当前服务的图像模型名")
    command.add_argument("--base-url", help="覆盖当前服务的 API 根地址或完整百炼提交地址")
    command.add_argument("--api-key", help="仅本次运行使用；推荐改用环境变量")
    command.add_argument("--character", default=str(LAB_DIR / "character.example.json"))
    command.add_argument("--size", default="768*1024", help="百炼图片尺寸")
    command.add_argument("--aspect-ratio", default="3:4", help="Gemini 图片比例")
    command.add_argument("--portrait-source", nargs="+", metavar="参考图", help="传入 1–3 张角色参考图，生成单角色正面透明立绘")
    command.add_argument("--portrait-prompt", help="多参考图立绘的人物、服装与画风文字设定")
    command.add_argument("--portrait-size", default="960*1280", help="多参考图角色立绘的百炼图片尺寸")
    command.add_argument("--edit-source", help="以该本地正视图作为参考，运行百炼图像编辑")
    command.add_argument("--edit-prompt", help="覆盖默认的开心状态编辑描述")
    command.add_argument("--scene-batch", nargs="+", metavar="场景", help="以指定场景批量生成剧情图；可选 A B C")
    command.add_argument("--scene-source", action="append", default=[], metavar="名称=路径", help="剧情图参考图；可重复传入，例如 experiment=/tmp/front.png")
    command.add_argument("--scene-size", default="1280*720", help="剧情场景图的百炼图片尺寸")
    command.add_argument("--scene-duo", nargs=2, metavar=("萧炎图", "纳兰嫣然图"), help="用两张角色形象生成 C 双主角漫画场景图")
    command.add_argument("--scene-trio", nargs=3, metavar=("萧炎图", "薰儿图", "纳兰嫣然图"), help="用三张角色正视图生成退婚剧情漫画场景图")
    command.add_argument("--dry-run", action="store_true", help="仅检查配置与提示词，不调用模型")
    return command


if __name__ == "__main__":
    run(parser().parse_args())
