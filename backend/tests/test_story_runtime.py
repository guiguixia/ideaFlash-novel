import asyncio
import json
import os
import threading
from unittest.mock import AsyncMock, patch

os.environ["NOVEL_DATABASE_URL"] = "sqlite:////tmp/ideaFlash-story-test.db"

from fastapi.testclient import TestClient
from main import app, run_experience_build_in_worker
from models import LLMConfig
from prompts.experience import render_experience_mood_protocol
from prompts.role_chat import mood_protocol
from services import _model_request_options


def test_known_provider_options_disable_thinking_mode():
    assert _model_request_options(LLMConfig(base_url="https://api.deepseek.com", model="deepseek-v4-pro")) == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert _model_request_options(LLMConfig(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen3-max")) == {"extra_body": {"enable_thinking": False}}
    assert _model_request_options(LLMConfig(base_url="https://open.bigmodel.cn/api/paas/v4", model="glm-4.7")) == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert _model_request_options(LLMConfig(base_url="https://api.example.com", model="example-chat")) == {}


def test_mood_protocol_only_contains_uploaded_states():
    states = [{"id": "taunting", "name": "嘲讽", "description": "轻蔑回应"}]
    private_prompt = mood_protocol(json.dumps(states, ensure_ascii=False))
    experience_prompt = render_experience_mood_protocol(states)
    assert "[mood:taunting]" in private_prompt
    assert "[mood:happy]" not in private_prompt
    assert "[mood:taunting]" in experience_prompt
    assert "[mood:thinking]" not in experience_prompt
    assert "当前角色形象状态" not in render_experience_mood_protocol([])


def test_community_qr_uses_backend_proxy():
    client = TestClient(app)
    with patch.dict(os.environ, {"NOVEL_COMMUNITY_QR_IMAGE_URL": "https://cdn.example.com/community-qr.png"}):
        current = client.get("/api/community-qr")
    assert current.json()["data"]["imageUrl"] == "/api/community-qr/image"


def test_community_qr_proxy_disables_cache():
    client = TestClient(app)
    upstream = type("Upstream", (), {
        "content": b"png-content",
        "headers": {"content-type": "image/png"},
        "raise_for_status": lambda self: None,
    })()
    with patch.dict(os.environ, {"NOVEL_COMMUNITY_QR_IMAGE_URL": "https://cdn.example.com/community-qr.png"}), patch("main.httpx.get", return_value=upstream) as get:
        response = client.get("/api/community-qr/image")
    assert response.status_code == 200
    assert response.content == b"png-content"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert get.call_args.args[0].startswith("https://cdn.example.com/community-qr.png?_=")


def test_original_story_can_run_private_experience():
    client = TestClient(app)
    headers = {}
    work = client.post("/api/works", headers=headers, json={"title": "测试世界", "opening_scene": "钟声在空港响起。"}).json()["data"]
    script = client.post(f"/api/works/{work['id']}/scripts", headers=headers, json={}).json()["data"]
    session = client.post(f"/api/works/{work['id']}/scripts/{script['id']}/sessions", headers=headers, json={}).json()["data"]
    result = client.post(f"/api/works/{work['id']}/sessions/{session['id']}/turn", headers=headers, json={"message": "我看向钟楼"})
    assert result.status_code == 200
    assert "event: chunk" in result.text
    assert "event: done" in result.text
    reset = client.post(f"/api/works/{work['id']}/sessions/{session['id']}/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["data"]["turn"] == 0
    assert len(reset.json()["data"]["history"]) == 1
    renamed = client.patch(f"/api/works/{work['id']}/sessions/{session['id']}", headers=headers, json={"title": "萧炎的第一条支线"})
    assert renamed.status_code == 200
    assert renamed.json()["data"]["title"] == "萧炎的第一条支线"


def test_turn_keeps_user_message_when_generation_fails():
    client = TestClient(app)
    work = client.post("/api/works", json={"title": "持久化体验"}).json()["data"]
    script = client.post(f"/api/works/{work['id']}/scripts", json={}).json()["data"]

    async def opening(*_args, **_kwargs):
        return "开场", "test-model"

    async def failed_stream(*_args, **_kwargs):
        raise RuntimeError("模型暂时不可用")
        yield ""

    with patch("main.narrate", new=AsyncMock(side_effect=opening)), patch("main.narrate_stream", new=failed_stream):
        session = client.post(f"/api/works/{work['id']}/scripts/{script['id']}/sessions", json={}).json()["data"]
        response = client.post(f"/api/works/{work['id']}/sessions/{session['id']}/turn", json={"message": "我先观察四周"})

    assert "event: error" in response.text
    stored = client.get(f"/api/works/{work['id']}/sessions/{session['id']}").json()["data"]
    assert stored["history"][-2] == {"role": "user", "content": "我先观察四周"}
    assert stored["history"][-1]["status"] == "failed"


def test_experience_turn_strips_mood_tag_and_emits_mood_event():
    client = TestClient(app)
    work = client.post("/api/works", json={"title": "情绪体验"}).json()["data"]
    script = client.post(f"/api/works/{work['id']}/scripts", json={"player_identity": "测试角色"}).json()["data"]
    card = client.post(
        f"/api/works/{work['id']}/scripts/{script['id']}/role-cards",
        json={"name": "测试角色", "identity": "", "personality": "", "appearance": "", "background": "", "current_state": ""},
    ).json()["data"]
    uploaded = client.post(
        f"/api/works/{work['id']}/scripts/{script['id']}/role-cards/{card['id']}/image?slot=happy",
        files={"file": ("happy.png", b"test-image", "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["data"]["availableEmotions"] == [{"id": "happy", "name": "开心", "description": "神情放松，流露轻快与愉悦"}]

    async def opening(*_args, **_kwargs):
        return "开场", "test-model"

    async def mood_stream(*_args, **_kwargs):
        yield "[mood:happy]\n", "test-model"
        yield "场景因你的到来而明亮起来。\n[choices]\n- 向同伴道谢\n- 观察四周变化\n[/choices]", "test-model"

    with patch("main.narrate", new=AsyncMock(side_effect=opening)), patch("main.narrate_stream", new=mood_stream):
        session = client.post(f"/api/works/{work['id']}/scripts/{script['id']}/sessions", json={"player_identity": "测试角色"}).json()["data"]
        response = client.post(f"/api/works/{work['id']}/sessions/{session['id']}/turn", json={"message": "我轻轻点头"})

    assert "event: mood" in response.text
    assert '"mood": "happy"' in response.text
    stored = client.get(f"/api/works/{work['id']}/sessions/{session['id']}").json()["data"]
    assert stored["history"][-1]["content"] == "场景因你的到来而明亮起来。"
    assert stored["history"][-1]["mood"] == "happy"
    assert stored["history"][-1]["suggestions"] == ["向同伴道谢", "观察四周变化"]
    assert "[mood:" not in stored["history"][-1]["content"]
    assert "[choices]" not in stored["history"][-1]["content"]


def test_work_can_be_deleted_with_its_related_records():
    client = TestClient(app)
    work = client.post("/api/works", json={"title": "待删除的作品"}).json()["data"]

    deleted = client.delete(f"/api/works/{work['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["data"]["id"] == work["id"]
    assert client.get(f"/api/works/{work['id']}").status_code == 404
    works = client.get("/api/works").json()["list"]
    assert work["id"] not in {item["id"] for item in works}


def test_experience_build_runs_in_its_own_worker_queue():
    worker_thread_id = None

    async def build(_run_id: str):
        nonlocal worker_thread_id
        worker_thread_id = threading.get_ident()

    with patch("main.run_experience_build", new=build):
        api_thread_id = threading.get_ident()
        asyncio.run(run_experience_build_in_worker("build-in-worker"))

    assert worker_thread_id is not None
    assert worker_thread_id != api_thread_id


def test_imported_source_segments_are_paginated_outside_work_detail():
    client = TestClient(app)
    headers = {}
    source = "\n".join(f"第{i}章 标题{i}\n正文{i}" for i in range(1, 52))
    work = client.post(
        "/api/works/import",
        headers=headers,
        data={"work_type": "imported_novel", "title": "分页资料"},
        files={"file": ("book.txt", source.encode(), "text/plain")},
    ).json()["data"]

    detail = client.get(f"/api/works/{work['id']}", headers=headers).json()["data"]
    page = client.get(f"/api/works/{work['id']}/segments?page=2&page_size=20", headers=headers).json()["data"]

    assert "segments" not in detail
    assert detail["sourceSegmentCount"] == 51
    assert len(page["items"]) == 20
    assert page["page"] == 2
    assert page["totalPages"] == 3


def test_imported_script_extracts_character_names_for_later_session_selection():
    client = TestClient(app)
    headers = {}
    work = client.post(
        "/api/works/import",
        headers=headers,
        data={"work_type": "imported_novel", "title": "角色抽取"},
        files={"file": ("book.txt", "第1章 初遇\n萧炎：老师，我准备好了。\n药老说道：那就出发。".encode(), "text/plain")},
    ).json()["data"]

    async def model_result(_db, prompt, temperature=.1, stage=""):
        if "局部副本结构抽取器" in prompt:
            return {"characters":[{"name":"萧炎","appearance":"","attributes":{"identity":"萧家子弟"},"importance":3},{"name":"药老","appearance":"","attributes":{"identity":"戒中灵魂"},"importance":2}],"factions":[],"locations":[],"entities":[],"events":[],"relations":[],"conflicts":[]}
        return {"scenario":{},"confirmed_preload":[],"historical_questions":[]}
    with patch("services._json_completion",new=AsyncMock(side_effect=model_result)):
        created = client.post(
            f"/api/works/{work['id']}/scripts",
            headers=headers,
            json={"start_sequence": 1, "end_sequence": 1},
        ).json()["data"]
    result = client.get(f"/api/works/{work['id']}", headers=headers).json()["data"]["scripts"][0]

    assert created["status"] == "queued"
    assert result["status"] == "ready"
    assert "萧炎" in result["characters"]
    cards = client.get(f"/api/works/{work['id']}/scripts/{result['id']}/role-cards", headers=headers)
    assert cards.status_code == 200
    assert any(card["name"] == "萧炎" and card["roleMode"] == "replacement" for card in cards.json()["data"])
    session = client.post(
        f"/api/works/{work['id']}/scripts/{result['id']}/sessions",
        headers=headers,
        json={"player_identity": "萧炎"},
    )
    assert session.status_code == 200


def test_imported_script_reuses_cached_chapter_extraction():
    client = TestClient(app)
    headers = {}
    work = client.post(
        "/api/works/import", headers=headers, data={"work_type": "imported_novel", "title": "章节缓存"},
        files={"file": ("book.txt", "第1章 缓存\n萧炎说道：我会继续修炼。".encode(), "text/plain")},
    ).json()["data"]

    async def model_result(_db, prompt, temperature=.1, stage=""):
        if "局部副本结构抽取器" in prompt:
            return {"characters":[{"name":"萧炎","appearance":"","attributes":{},"importance":3}],"factions":[],"locations":[],"entities":[],"events":[],"relations":[],"conflicts":[]}
        return {"scenario":{},"confirmed_preload":[],"historical_questions":[]}

    with patch("services._json_completion", new=AsyncMock(side_effect=model_result)) as completion:
        client.post(f"/api/works/{work['id']}/scripts", headers=headers, json={"start_sequence": 1, "end_sequence": 1})
        client.post(f"/api/works/{work['id']}/scripts", headers=headers, json={"start_sequence": 1, "end_sequence": 1})

    extraction_calls = [call for call in completion.await_args_list if "局部副本结构抽取器" in call.args[1]]
    assert len(extraction_calls) == 1


def test_imported_script_fails_instead_of_guessing_character_names_when_model_fails():
    client = TestClient(app)
    headers = {}
    work = client.post(
        "/api/works/import", headers=headers, data={"work_type": "imported_novel", "title": "失败不猜人名"},
        files={"file": ("book.txt", "第1章\n萧炎苦笑道：我会继续修炼。".encode(), "text/plain")},
    ).json()["data"]
    with patch("services._json_completion",new=AsyncMock(side_effect=RuntimeError("大模型调用失败（deepseek-flash）：404 Not Found"))):
        created = client.post(f"/api/works/{work['id']}/scripts", headers=headers, json={"start_sequence": 1, "end_sequence": 1}).json()["data"]
    script = client.get(f"/api/works/{work['id']}", headers=headers).json()["data"]["scripts"][0]
    assert created["status"] == "queued"
    assert script["status"] == "failed"
    assert script["characters"] == []
    assert "404 Not Found" in script["build"]["error"]
