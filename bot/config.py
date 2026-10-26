import json
import os
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    price: int
    duration: int  # минуты


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    business_name: str
    address: str
    phone: str
    tz: ZoneInfo
    work_start: time
    work_end: time
    workdays: frozenset[int]
    slot_step: int
    days_ahead: int
    min_lead: int
    remind_before: int
    services: tuple[Service, ...]
    db_path: str

    def service(self, service_id: str) -> Service | None:
        return next((s for s in self.services if s.id == service_id), None)

    def now(self) -> datetime:
        """Текущее время в часовом поясе бизнеса (без tzinfo — так хранится в БД)."""
        return datetime.now(self.tz).replace(tzinfo=None, second=0, microsecond=0)


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _parse_ints(value: str) -> frozenset[int]:
    return frozenset(int(x) for x in value.replace(" ", "").split(",") if x)


def load_services(path: Path) -> tuple[Service, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Service(**item) for item in data)


def load_config(env_file: str = ".env") -> Config:
    load_dotenv(env_file)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN не задан: скопируйте .env.example в .env и заполните")

    env = os.getenv
    return Config(
        bot_token=token,
        admin_ids=_parse_ints(env("ADMIN_IDS", "")),
        business_name=env("BUSINESS_NAME", "Наш салон"),
        address=env("ADDRESS", ""),
        phone=env("PHONE", ""),
        tz=ZoneInfo(env("TIMEZONE", "Europe/Moscow")),
        work_start=_parse_time(env("WORK_START", "10:00")),
        work_end=_parse_time(env("WORK_END", "20:00")),
        workdays=_parse_ints(env("WORKDAYS", "1,2,3,4,5,6")),
        slot_step=int(env("SLOT_STEP", "30")),
        days_ahead=int(env("DAYS_AHEAD", "14")),
        min_lead=int(env("MIN_LEAD", "60")),
        remind_before=int(env("REMIND_BEFORE", "120")),
        services=load_services(Path(env("SERVICES_FILE", "services.json"))),
        db_path=env("DB_PATH", "bookings.db"),
    )
