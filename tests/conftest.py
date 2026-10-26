from datetime import time
from zoneinfo import ZoneInfo

import pytest

from bot.config import Config, Service
from bot.db import Database


@pytest.fixture
def cfg() -> Config:
    return Config(
        bot_token="42:TEST",
        admin_ids=frozenset({999}),
        business_name="Тестовый салон",
        address="ул. Тестовая, 1",
        phone="+7 900 000-00-00",
        tz=ZoneInfo("Europe/Moscow"),
        work_start=time(10, 0),
        work_end=time(20, 0),
        workdays=frozenset({1, 2, 3, 4, 5, 6, 7}),
        slot_step=30,
        days_ahead=14,
        min_lead=60,
        remind_before=120,
        services=(
            Service("haircut", "Стрижка", 1500, 60),
            Service("beard", "Борода", 900, 30),
        ),
        db_path=":memory:",
    )


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()
