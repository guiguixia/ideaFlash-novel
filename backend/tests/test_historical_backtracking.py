from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import (  # noqa: E402
    EXPERIENCE_BACKTRACK_MAX_ROUNDS,
    _apply_historical_question_result,
    _backtrack_historical_question_states,
    _initialize_historical_question_states,
)


def _question(question_id: str = "q1") -> dict:
    return {
        "id": question_id,
        "characters": ["角色A"],
        "type": "motivation",
        "question": "角色A为什么已在此处行动？",
        "completion_criteria": "确认直接行动原因即可。",
    }


class HistoricalBacktrackingTest(unittest.TestCase):
    def test_unresolved_without_evidence_stays_unresolved(self) -> None:
        state = _initialize_historical_question_states([_question()])[0]

        changed = _apply_historical_question_result(
            state,
            {"id": "q1", "status": "unresolved", "answer_delta": "", "remaining_need": "仍需确认直接行动原因。", "evidence": []},
            chapter_number=249,
        )

        self.assertFalse(changed)
        self.assertEqual(state["status"], "unresolved")
        self.assertEqual(state["accumulated_answer"], "")
        self.assertEqual(state["evidence_chapters"], [])

    def test_unresolved_with_partial_evidence_becomes_partial(self) -> None:
        state = _initialize_historical_question_states([_question()])[0]

        changed = _apply_historical_question_result(
            state,
            {"id": "q1", "status": "partial", "answer_delta": "角色A收到命令后赶往此处。", "remaining_need": "仍需确认该命令与当前行动的直接关系。", "evidence": [{"fact": "正文写明角色A收到命令。"}]},
            chapter_number=249,
        )

        self.assertTrue(changed)
        self.assertEqual(state["status"], "partial")
        self.assertEqual(state["accumulated_answer"], "角色A收到命令后赶往此处。")
        self.assertEqual(state["evidence_chapters"], [249])

    def test_partial_without_evidence_remains_partial(self) -> None:
        state = _initialize_historical_question_states([_question()])[0]
        _apply_historical_question_result(
            state,
            {"id": "q1", "status": "partial", "answer_delta": "角色A收到命令后赶往此处。", "remaining_need": "仍需确认直接关系。", "evidence": []},
            chapter_number=249,
        )

        changed = _apply_historical_question_result(
            state,
            {"id": "q1", "status": "unresolved", "answer_delta": "", "remaining_need": "仍需确认直接关系。", "evidence": []},
            chapter_number=248,
        )

        self.assertFalse(changed)
        self.assertEqual(state["status"], "partial")
        self.assertEqual(state["evidence_chapters"], [249])

    def test_partial_with_completion_becomes_resolved(self) -> None:
        state = _initialize_historical_question_states([_question()])[0]
        _apply_historical_question_result(
            state,
            {"id": "q1", "status": "partial", "answer_delta": "角色A收到命令后赶往此处。", "remaining_need": "仍需确认直接关系。", "evidence": []},
            chapter_number=249,
        )

        _apply_historical_question_result(
            state,
            {"id": "q1", "status": "resolved", "answer_delta": "命令要求角色A在此处保护角色B。", "remaining_need": "", "evidence": [{"fact": "命令内容要求保护角色B。"}]},
            chapter_number=248,
        )

        self.assertEqual(state["status"], "resolved")
        self.assertEqual(state["remaining_need"], "")
        self.assertEqual(state["evidence_chapters"], [249, 248])

    def test_all_resolved_stops_before_older_chapter(self) -> None:
        calls: list[int] = []

        async def resolve(questions: list[dict], chapter_number: int, _body: str) -> dict:
            calls.append(chapter_number)
            return {"question_results": [{"id": questions[0]["id"], "status": "resolved", "answer_delta": "已确认。", "remaining_need": "", "evidence": []}]}

        result = asyncio.run(_backtrack_historical_question_states(
            _initialize_historical_question_states([_question()]),
            [{"number": 249, "body": "第一章"}, {"number": 248, "body": "更早章节"}],
            resolve,
        ))

        self.assertEqual(calls, [249])
        self.assertEqual(result["rounds_processed"], 1)
        self.assertEqual(result["questions"][0]["status"], "resolved")

    def test_max_rounds_is_three_and_preserves_unresolved_question(self) -> None:
        calls: list[int] = []

        async def resolve(_questions: list[dict], chapter_number: int, _body: str) -> dict:
            calls.append(chapter_number)
            return {"question_results": []}

        result = asyncio.run(_backtrack_historical_question_states(
            _initialize_historical_question_states([_question()]),
            [{"number": 249, "body": ""}, {"number": 248, "body": ""}, {"number": 247, "body": ""}, {"number": 246, "body": ""}],
            resolve,
        ))

        self.assertEqual(EXPERIENCE_BACKTRACK_MAX_ROUNDS, 3)
        self.assertEqual(calls, [249, 248, 247])
        self.assertEqual(result["rounds_processed"], 3)
        self.assertEqual(result["questions"][0]["status"], "unresolved")

    def test_illegal_status_regression_is_rejected(self) -> None:
        state = _initialize_historical_question_states([_question()])[0]
        _apply_historical_question_result(
            state,
            {"id": "q1", "status": "partial", "answer_delta": "部分证据。", "remaining_need": "仍需补充。", "evidence": []},
            chapter_number=249,
        )

        changed = _apply_historical_question_result(
            state,
            {"id": "q1", "status": "unresolved", "answer_delta": "", "remaining_need": "错误回退。", "evidence": []},
            chapter_number=248,
        )

        self.assertFalse(changed)
        self.assertEqual(state["status"], "partial")
        self.assertEqual(state["remaining_need"], "仍需补充。")

    def test_unknown_question_id_is_ignored(self) -> None:
        async def resolve(_questions: list[dict], _chapter_number: int, _body: str) -> dict:
            return {"question_results": [{"id": "missing", "status": "resolved", "answer_delta": "不应写入。", "remaining_need": "", "evidence": []}]}

        result = asyncio.run(_backtrack_historical_question_states(
            _initialize_historical_question_states([_question()]),
            [{"number": 249, "body": ""}],
            resolve,
        ))

        self.assertEqual(result["questions"][0]["status"], "unresolved")
        self.assertEqual(result["questions"][0]["accumulated_answer"], "")
