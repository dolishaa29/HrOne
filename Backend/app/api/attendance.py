"""Punch-in, punch-out, list and correct (PATCH) attendance records."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db.connection import logs
from app.models.schemas import PunchInIn, PunchOutIn, RegularizeIn
from app.utils.constants import ALL_STATUSES, PRESENCE
from app.utils.helpers import get_employee, ms_to_datetime, now, record_to_json
from app.utils.rules import calc_derived_fields, check_punch_out, get_attendance_date

router = APIRouter()


@router.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = get_employee(body.emp_code)

    if body.punched_at is None:
        punched_at = now()
    else:
        punched_at = ms_to_datetime(body.punched_at)

    day = get_attendance_date(emp, punched_at)
    derived = calc_derived_fields(emp, day, body.status, punched_at, None)

    record = {
        "emp_code": body.emp_code,
        "date": day.isoformat(),
        "status": body.status,
        "punch_in": punched_at,
        "punch_out": None,
        "work_hours": derived["work_hours"],
        "late_minutes": derived["late_minutes"],
        "overtime_minutes": derived["overtime_minutes"],
        "half_day": derived["half_day"],
        "history": [],
    }

    # The unique index (emp_code, date) makes MongoDB refuse a second punch-in for the same day,
    # even when two requests arrive at the same moment.
    try:
        logs.insert_one(record)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    return record_to_json(record)


@router.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = get_employee(body.emp_code)

    if body.punched_at is None:
        punched_at = now()
    else:
        punched_at = ms_to_datetime(body.punched_at)

    # the latest record that started before this punch-out (also works after midnight)
    record = logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": punched_at}},
        sort=[("punch_in", -1)],
    )
    if record is None:
        raise HTTPException(404, "no punch-in found")
    if record.get("punch_out") is not None:
        raise HTTPException(409, "already punched out")
    check_punch_out(record["punch_in"], punched_at)

    day = date.fromisoformat(record["date"])
    derived = calc_derived_fields(emp, day, record["status"], record["punch_in"], punched_at)

    # "punch_out": None in the filter -> if two punch-outs arrive together, only one can update
    updated = logs.find_one_and_update(
        {"_id": record["_id"], "punch_out": None},
        {"$set": {
            "punch_out": punched_at,
            "work_hours": derived["work_hours"],
            "overtime_minutes": derived["overtime_minutes"],
            "half_day": derived["half_day"],
        }},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(409, "already punched out")
    return record_to_json(updated)


def build_attendance_query(emp_code, date_from, date_to, status):
    """The filter for GET /attendance. Also used by the explain API."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")

    query = {}
    if emp_code:
        query["emp_code"] = emp_code
    if date_from or date_to:
        query["date"] = {}
    if date_from:
        query["date"]["$gte"] = date_from.isoformat()
    if date_to:
        query["date"]["$lte"] = date_to.isoformat()
    if status:
        query["status"] = status
    return query


ATTENDANCE_SORT = [("date", -1), ("emp_code", 1)]  # newest day first


@router.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[ALL_STATUSES] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = build_attendance_query(emp_code, date_from, date_to, status)
    skip = (page - 1) * page_size
    cursor = logs.find(query).sort(ATTENDANCE_SORT).skip(skip).limit(page_size)

    items = []
    for record in cursor:
        items.append(record_to_json(record))
    return {"items": items, "total": logs.count_documents(query), "page": page, "page_size": page_size}


@router.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code: str, body: RegularizeIn, date_text: str = Path(alias="date")):
    # --- 1. find the employee and the record ---
    try:
        day = date.fromisoformat(date_text)
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD")
    emp = get_employee(emp_code)
    record = logs.find_one({"emp_code": emp_code, "date": day.isoformat()})
    if record is None:
        raise HTTPException(404, "no record for this date")

    # --- 2. decide the new status and punch times ---
    new_status = body.status if body.status is not None else record["status"]

    if new_status in PRESENCE:
        if body.punch_in is not None:
            new_in = ms_to_datetime(body.punch_in)
        else:
            new_in = record.get("punch_in")
        if body.punch_out is not None:
            new_out = ms_to_datetime(body.punch_out)
        else:
            new_out = record.get("punch_out")

        if new_in is None:
            raise HTTPException(422, "a presence status needs a punch_in")
        if get_attendance_date(emp, new_in) != day:
            raise HTTPException(422, "punch_in must stay on the record's date")
        if new_out is not None:
            check_punch_out(new_in, new_out)
    else:
        # ABSENT or LEAVE: no punch times allowed
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(422, "ABSENT and LEAVE can not have punch times")
        new_in = None
        new_out = None

    # --- 3. new values vs old values ---
    derived = calc_derived_fields(emp, day, new_status, new_in, new_out)
    new_values = {
        "status": new_status,
        "punch_in": new_in,
        "punch_out": new_out,
        "work_hours": derived["work_hours"],
        "late_minutes": derived["late_minutes"],
        "overtime_minutes": derived["overtime_minutes"],
        "half_day": derived["half_day"],
    }
    old_values = {
        "status": record["status"],
        "punch_in": record.get("punch_in"),
        "punch_out": record.get("punch_out"),
        "work_hours": record.get("work_hours"),
        "late_minutes": record.get("late_minutes") or 0,
        "overtime_minutes": record.get("overtime_minutes") or 0,
        "half_day": record.get("half_day") or False,
    }

    changes = {}
    for field in new_values:
        if new_values[field] != old_values[field]:
            changes[field] = {"from": old_values[field], "to": new_values[field]}
    if not changes:
        raise HTTPException(422, "nothing to change")

    # --- 4. save + add one history entry ---
    history_entry = {"at": now(), "by": body.regularized_by, "reason": body.reason, "changes": changes}
    old_history_length = len(record.get("history") or [])

    # Only update if nobody changed the record since we read it
    # (same punch_out and same number of history entries). Otherwise 409.
    updated = logs.find_one_and_update(
        {
            "_id": record["_id"],
            "punch_out": record.get("punch_out"),
            "$expr": {"$eq": [{"$size": {"$ifNull": ["$history", []]}}, old_history_length]},
        },
        {"$set": new_values, "$push": {"history": history_entry}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(409, "record was changed by another request, try again")
    return record_to_json(updated)
