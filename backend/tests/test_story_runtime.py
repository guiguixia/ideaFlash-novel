import os
from unittest.mock import AsyncMock, patch

os.environ["NOVEL_DATABASE_URL"] = "sqlite:////tmp/ideaFlash-story-test.db"

from fastapi.testclient import TestClient
from main import app


def test_original_story_can_run_private_experience():
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "ideaFlash", "password": "ideaFlash"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
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


def test_imported_source_segments_are_paginated_outside_work_detail():
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "ideaFlash", "password": "ideaFlash"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
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
    token = client.post("/api/auth/login", json={"username": "ideaFlash", "password": "ideaFlash"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
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
    token = client.post("/api/auth/login", json={"username": "ideaFlash", "password": "ideaFlash"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
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
    token = client.post("/api/auth/login", json={"username": "ideaFlash", "password": "ideaFlash"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
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
