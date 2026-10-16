"""Values used everywhere."""
from datetime import datetime, timedelta, timezone
from typing import Literal

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

PRESENCE = ["PRESENT", "WFH", "ON_DUTY"]  # these statuses count as "present"
ALL_STATUSES = Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]

MIN_MS = 100_000_000_000  # smaller numbers look like seconds, not milliseconds
MAX_MS = 4_102_444_800_000  # year 2100
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"  # "2026-07"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"  # "09:30"
