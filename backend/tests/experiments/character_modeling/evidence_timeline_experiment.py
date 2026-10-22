"""显式 Evidence Timeline 回归入口；仅检查召回/压缩，不调用建模写链。"""
from __future__ import annotations

import argparse
import json

from database import SessionLocal
from models import Chapter, Character
from services import character_evidence_batches, character_evidence_windows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("novel_id")
    parser.add_argument("character_name")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        character = db.query(Character).filter_by(novel_id=args.novel_id, name=args.character_name).one()
        chapters = db.query(Chapter).filter_by(novel_id=args.novel_id).order_by(Chapter.source_segment_order).all()
        names = [character.name, *(character.aliases or [])]
        windows = character_evidence_windows(chapters, names)
        batches = character_evidence_batches(windows)
        print(json.dumps({
            "character": character.name,
            "matchedSegments": [item["order"] for item in windows],
            "evidenceWindowCount": len(windows),
            "batchCount": len(batches),
            "batchChars": [sum(len(item["text"]) for item in batch) for batch in batches],
        }, ensure_ascii=False, indent=2))
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
