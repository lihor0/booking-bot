"""Расчёт свободных дней и времени. Чистые функции — легко тестировать."""
from datetime import date, datetime, timedelta

from bot.config import Config

Interval = tuple[datetime, datetime]


def candidate_days(now: datetime, cfg: Config, blocked: set[date]) -> list[date]:
    """Рабочие, не закрытые администратором дни в пределах окна записи."""
    days = []
    for offset in range(cfg.days_ahead):
        day = now.date() + timedelta(days=offset)
        if day.isoweekday() in cfg.workdays and day not in blocked:
            days.append(day)
    return days


def free_slots(day: date, duration: int, busy: list[Interval], now: datetime, cfg: Config) -> list[datetime]:
    """Начала всех слотов дня, куда помещается услуга длительностью `duration` минут."""
    start = datetime.combine(day, cfg.work_start)
    end = datetime.combine(day, cfg.work_end)
    length = timedelta(minutes=duration)
    step = timedelta(minutes=cfg.slot_step)
    earliest = now + timedelta(minutes=cfg.min_lead)

    slots = []
    t = start
    while t + length <= end:
        overlaps = any(t < b_end and t + length > b_start for b_start, b_end in busy)
        if t >= earliest and not overlaps:
            slots.append(t)
        t += step
    return slots
