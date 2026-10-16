"""Business rules R1 - R5."""
from datetime import datetime, time, timedelta

from fastapi import HTTPException

from app.utils.constants import IST, PRESENCE
from app.utils.helpers import round_half_up


def is_overnight(emp):
    """22:00 - 06:00 is an overnight shift (end is not after start)."""
    return emp["shift_end"] <= emp["shift_start"]


def shift_start_time(emp, day):
    """The exact moment the shift starts on this day (IST)."""
    return datetime.combine(day, time.fromisoformat(emp["shift_start"]), tzinfo=IST)


def shift_end_time(emp, day):
    """The exact moment the shift ends. An overnight shift ends the next day."""
    end = datetime.combine(day, time.fromisoformat(emp["shift_end"]), tzinfo=IST)
    if is_overnight(emp):
        end = end + timedelta(days=1)
    return end


def get_attendance_date(emp, punch_in):
    """R1: the IST date of the punch-in.
    Overnight shift: a punch-in before the shift end (e.g. 02:00) belongs to yesterday's shift."""
    local = punch_in.astimezone(IST)
    day = local.date()
    if is_overnight(emp) and local.strftime("%H:%M:%S") < emp["shift_end"] + ":00":
        day = day - timedelta(days=1)
    return day


def calc_late_minutes(emp, day, punch_in):
    """R2: late only if MORE than 10 minutes after shift start. Then count from shift start."""
    seconds_late = (punch_in - shift_start_time(emp, day)).total_seconds()
    if seconds_late > 10 * 60:
        return int(seconds_late // 60)
    return 0


def calc_overtime_minutes(emp, day, punch_out):
    """R3: minutes after shift end, only if at least 30."""
    minutes = int((punch_out - shift_end_time(emp, day)).total_seconds() // 60)
    if minutes >= 30:
        return minutes
    return 0


def calc_work_hours(punch_in, punch_out):
    """R4: hours between punch-in and punch-out, 2 decimals."""
    seconds = (punch_out - punch_in).total_seconds()
    return round_half_up(seconds / 3600, 2)


def calc_derived_fields(emp, day, status, punch_in, punch_out):
    """The 4 numbers the API computes for every record."""
    late = 0
    hours = None
    overtime = 0
    half_day = False

    if status in PRESENCE and punch_in is not None:
        late = calc_late_minutes(emp, day, punch_in)
        if punch_out is not None:
            hours = calc_work_hours(punch_in, punch_out)
            overtime = calc_overtime_minutes(emp, day, punch_out)
            half_day = hours < 4.5  # R5

    return {"late_minutes": late, "work_hours": hours, "overtime_minutes": overtime, "half_day": half_day}


def check_punch_out(punch_in, punch_out):
    if punch_out <= punch_in:
        raise HTTPException(422, "punch_out must be after punch_in")
    if punch_out - punch_in > timedelta(hours=24):
        raise HTTPException(422, "punch_out must be within 24 hours of punch_in")
