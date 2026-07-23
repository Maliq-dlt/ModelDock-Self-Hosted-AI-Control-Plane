import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import get_settings
from app.core.db import init_db, session_factory
from app.services.retention import purge_retained_data


async def main() -> None:
    await init_db()
    async with session_factory() as session:
        result = await purge_retained_data(session, get_settings().request_retention_days)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
