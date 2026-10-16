"""Small helper functions: time conversion, rounding, JSON output."""
import calendar
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException

from app.db.connection import employees
from app.utils.constants import EPOCH, UTC


def ms_to_datetime(ms):
    """1783312500123 (milliseconds) -> datetime in UTC, without the milliseconds."""
    return EPOCH + timedelta(seconds=ms // 1000)


def datetime_to_ms(value):
    """datetime -> milliseconds. None stays None."""
    if value is None:
        return None
    return (value - EPOCH) // timedelta(milliseconds=1)


def now():
    """Current time in UTC, without the microseconds."""
    return datetime.now(UTC).replace(microsecond=0)


def round_half_up(value, places):
    """School rounding: 2.675 -> 2.68. (Python's round() gives 2.67.) None stays None."""
    if value is None:
        return None
    step = Decimal("0.01") if places == 2 else Decimal("0.0001")
    return float(Decimal(str(value)).quantize(step, rounding=ROUND_HALF_UP))


def month_first_and_last_day(month):
    """"2026-07" -> (2026-07-01, 2026-07-31)"""
    year = int(month[:4])
    mon = int(month[5:])
    last_day = calendar.monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last_day)


def count_working_days(first, last):
    """How many Monday-Friday days are between first and last (both included)."""
    count = 0
    day = first
    while day <= last:
        if day.weekday() < 5:  # 0 = Monday ... 4 = Friday
            count += 1
        day += timedelta(days=1)
    return count


def get_employee(emp_code):
    emp = employees.find_one({"emp_code": emp_code})
    if emp is None:
        raise HTTPException(404, "employee not found")
    return emp


def employee_to_json(emp):
    return {
        "emp_code": emp["emp_code"],
        "name": emp["name"],
        "email": emp["email"],
        "department": emp["department"],
        "shift_start": emp["shift_start"],
        "shift_end": emp["shift_end"],
        "joined_on": emp["joined_on"],
        "created_at": datetime_to_ms(emp.get("created_at")),
    }


def record_to_json(record):
    """Attendance record from MongoDB -> JSON for the API.
    Old records may not have half_day / history, so we use defaults."""
    history = []
    for entry in record.get("history") or []:
        changes = {}
        for field, change in entry["changes"].items():
            old_value = change["from"]
            new_value = change["to"]
            if field in ("punch_in", "punch_out"):  # dates -> milliseconds
                old_value = datetime_to_ms(old_value)
                new_value = datetime_to_ms(new_value)
            changes[field] = {"from": old_value, "to": new_value}
        history.append({
            "at": datetime_to_ms(entry["at"]),
            "by": entry["by"],
            "reason": entry["reason"],
            "changes": changes,
        })

    return {
        "emp_code": record["emp_code"],
        "date": record["date"],
        "status": record["status"],
        "punch_in": datetime_to_ms(record.get("punch_in")),
        "punch_out": datetime_to_ms(record.get("punch_out")),
        "work_hours": record.get("work_hours"),
        "late_minutes": record.get("late_minutes") or 0,
        "overtime_minutes": record.get("overtime_minutes") or 0,
        "half_day": record.get("half_day") or False,
        "history": history,
    }
