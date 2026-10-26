from datetime import date

import pytest

from bot import keyboards as kb
from bot.handlers.admin import parse_day
from bot.handlers.client import normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+79001234567", "+79001234567"),
        ("89001234567", "+79001234567"),
        ("8 (900) 123-45-67", "+79001234567"),
        ("79001234567", "+79001234567"),
        ("12345", None),
        ("позвоните мне", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_parse_day():
    today = date(2030, 11, 15)
    assert parse_day("20.11", today) == date(2030, 11, 20)
    assert parse_day("10.01", today) == date(2031, 1, 10)  # прошедшая дата → следующий год
    assert parse_day("2030-12-31", today) == date(2030, 12, 31)
    assert parse_day("31.02", today) is None
    assert parse_day(None, today) is None


def test_callback_data_fits_telegram_limit():
    # Telegram ограничивает callback_data 64 байтами
    for cb in (
        kb.ServiceCb(id="a" * 40),
        kb.DayCb(day="2030-12-31"),
        kb.CancelCb(id=10**9, sure=True),
        kb.AdminCancelCb(id=10**9, sure=True),
    ):
        assert len(cb.pack().encode()) <= 64
