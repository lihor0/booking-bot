from dataclasses import replace
from datetime import date, datetime

from bot.slots import candidate_days, free_slots

DAY = date(2030, 3, 4)  # понедельник
EARLY = datetime(2030, 3, 1, 9, 0)


def at(h: int, m: int = 0) -> datetime:
    return datetime(2030, 3, 4, h, m)


def test_full_day_grid(cfg):
    slots = free_slots(DAY, 60, [], EARLY, cfg)
    assert slots[0] == at(10)
    assert slots[-1] == at(19)  # 60-минутная услуга должна закончиться к 20:00
    assert len(slots) == 19


def test_busy_interval_excluded(cfg):
    slots = free_slots(DAY, 60, [(at(12), at(13))], EARLY, cfg)
    assert at(11) in slots  # 11:00–12:00 вплотную — можно
    assert at(11, 30) not in slots  # пересекается с 12:00
    assert at(12) not in slots
    assert at(12, 30) not in slots
    assert at(13) in slots


def test_min_lead_time(cfg):
    now = at(14, 10)
    slots = free_slots(DAY, 30, [], now, cfg)
    assert slots[0] == at(15, 30)  # 14:10 + 60 мин = 15:10 → ближайший слот 15:30


def test_candidate_days_skip_weekends_and_blocked(cfg):
    cfg = replace(cfg, workdays=frozenset({1, 2, 3, 4, 5}), days_ahead=7)
    days = candidate_days(datetime(2030, 3, 4, 9), cfg, blocked={date(2030, 3, 6)})
    assert days == [date(2030, 3, 4), date(2030, 3, 5), date(2030, 3, 7), date(2030, 3, 8)]
