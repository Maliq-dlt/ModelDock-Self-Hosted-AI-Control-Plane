import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.db import session_factory
from app.services.evaluations import process_next_evaluation

async def run(once: bool, interval: float) -> None:
    while True:
        try:
            async with session_factory() as session:
                evaluation = await process_next_evaluation(session)
        except SQLAlchemyError as exc:
            if once:
                raise
            print(f"evaluation worker database error: {exc}", file=sys.stderr)
            evaluation = None
        if evaluation:
            print({"id": evaluation.id, "status": evaluation.status, "score": evaluation.score})
        if once:
            return
        await asyncio.sleep(0 if evaluation else interval)

def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued ModelDock evaluations")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(run(args.once, max(0.1, args.interval)))

if __name__ == "__main__":
    main()