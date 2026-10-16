from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.connection import employees, logs
from app.utils.constants import MONTH_PATTERN, PRESENCE, UTC
from app.utils.helpers import count_working_days, get_employee, month_first_and_last_day, round_half_up

router = APIRouter()


LATE_MINUTES = {"$ifNull": ["$late_minutes", 0]}

ONE_IF_LATE = {"$cond": [{"$gt": [LATE_MINUTES, 0]}, 1, 0]}

ONE_IF_LEAVE = {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
ONE_IF_ON_DUTY = {"$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]}

IS_PRESENT = {"$in": ["$status", PRESENCE]}

PRESENT_VALUE = {"$cond": [IS_PRESENT, {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1]}, 0]}

IS_WEEKDAY = {"$lte": [{"$isoDayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, 5]}

PRESENT_VALUE_WEEKDAY = {"$cond": [IS_WEEKDAY, PRESENT_VALUE, 0]}


def monthly_pipeline(emp_code, month):
    first, last = month_first_and_last_day(month)
    return [
        {"$match": {"emp_code": emp_code, "date": {"$gte": first.isoformat(), "$lte": last.isoformat()}}},
        {"$group": {
            "_id": None,
            "present_days": {"$sum": PRESENT_VALUE_WEEKDAY},
            "leave_days": {"$sum": ONE_IF_LEAVE},
            "late_count": {"$sum": ONE_IF_LATE},
            "total_late_minutes": {"$sum": LATE_MINUTES},
            "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}},
        }},
    ]


@router.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str = Query(pattern=MONTH_PATTERN)):
    emp = get_employee(emp_code)

    first, last = month_first_and_last_day(month)
    joined_on = date.fromisoformat(emp["joined_on"])
    start = max(first, joined_on)
    working_days = count_working_days(start, last)

    results = list(logs.aggregate(monthly_pipeline(emp_code, month)))
    if results:
        stats = results[0]
    else:  
        stats = {"present_days": 0, "leave_days": 0, "late_count": 0,
                 "total_late_minutes": 0, "total_overtime_minutes": 0}

    attendance_pct = None
    if working_days > 0:
        attendance_pct = round_half_up(stats["present_days"] * 100 / working_days, 2)

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": round_half_up(stats["present_days"], 2),
        "leave_days": stats["leave_days"],
        "late_count": stats["late_count"],
        "total_late_minutes": stats["total_late_minutes"],
        "total_overtime_minutes": stats["total_overtime_minutes"],
        "attendance_pct": attendance_pct,
    }



def department_summary_pipeline(month, department):
    first, last = month_first_and_last_day(month)

    employee_filter = {"joined_on": {"$lte": last.isoformat()}}
    if department:
        employee_filter["department"] = department

    return [
        {"$match": employee_filter},
        {"$lookup": {
            "from": "attendance_logs",
            "localField": "emp_code",
            "foreignField": "emp_code",
            "pipeline": [{"$match": {"date": {"$gte": first.isoformat(), "$lte": last.isoformat()}}}],
            "as": "logs",
        }},
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "department": 1,
            "emp_code": 1,
            "date": "$logs.date",
            "status": "$logs.status",
            "half_day": "$logs.half_day",
            "late_minutes": "$logs.late_minutes",
            "work_hours": "$logs.work_hours",
        }},
        {"$group": {
            "_id": "$department",
            "people": {"$addToSet": "$emp_code"},  
            "present_days": {"$sum": PRESENT_VALUE_WEEKDAY},
            "avg_work_hours": {"$avg": {"$cond": [IS_PRESENT, "$work_hours", None]}},  
            "late_count": {"$sum": ONE_IF_LATE},
            "total_late_minutes": {"$sum": LATE_MINUTES},
            "leave_count": {"$sum": ONE_IF_LEAVE},
            "on_duty_count": {"$sum": ONE_IF_ON_DUTY},
        }},
        {"$sort": {"_id": 1}},
    ]


@router.get("/analytics/departments/summary")
def department_summary(month: str = Query(pattern=MONTH_PATTERN), department: Optional[str] = None):
    items = []
    for row in employees.aggregate(department_summary_pipeline(month, department)):
        items.append({
            "department": row["_id"],
            "headcount": len(row["people"]),
            "present_days": round_half_up(row["present_days"], 2),
            "avg_work_hours": round_half_up(row["avg_work_hours"], 2),
            "late_count": row["late_count"],
            "total_late_minutes": row["total_late_minutes"],
            "leave_count": row["leave_count"],
            "on_duty_count": row["on_duty_count"],
        })
    return {"month": month, "items": items}


def late_leaderboard_pipeline(month, limit, department):
    first, last = month_first_and_last_day(month)
    pipeline = [
        {"$match": {"date": {"$gte": first.isoformat(), "$lte": last.isoformat()}}},
        {"$group": {"_id": "$emp_code", "total_late_minutes": {"$sum": LATE_MINUTES}, "late_count": {"$sum": ONE_IF_LATE}}},
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {"$lookup": {"from": "employees", "localField": "_id", "foreignField": "emp_code", "as": "emp"}},
        {"$unwind": "$emp"},
    ]
    if department:
        pipeline.append({"$match": {"emp.department": department}})

    pipeline.append(
        {"$setWindowFields": {"sortBy": {"total_late_minutes": -1}, "output": {"rank": {"$rank": {}}}}}
    )
    pipeline.append({"$match": {"rank": {"$lte": limit}}})  
    pipeline.append({"$sort": {"total_late_minutes": -1, "_id": 1}})  
    pipeline.append({"$project": {
        "_id": 0,
        "rank": 1,
        "emp_code": "$_id",
        "name": "$emp.name",
        "department": "$emp.department",
        "total_late_minutes": 1,
        "late_count": 1,
    }})
    return pipeline


@router.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(pattern=MONTH_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None,
):
    items = list(logs.aggregate(late_leaderboard_pipeline(month, limit, department)))
    return {"month": month, "items": items}



def department_trend_pipeline(department, from_day, to_day):
    if to_day < from_day:
        raise HTTPException(422, "to must be on or after from")
    if (to_day - from_day).days + 1 > 92:
        raise HTTPException(422, "the range can not be longer than 92 days")

    staff = list(employees.find({"department": department}))
    if not staff:
        raise HTTPException(404, "department not found")

    emp_codes = []
    join_dates = []
    for emp in staff:
        emp_codes.append(emp["emp_code"])
        join_dates.append(emp["joined_on"])

    first = from_day.isoformat()
    last = to_day.isoformat()
    first_midnight = datetime.combine(from_day, time(), UTC)
    day_after_last = datetime.combine(to_day + timedelta(days=1), time(), UTC)

    return [
        # step 1: the department's records in the date range
        {"$match": {"emp_code": {"$in": emp_codes}, "date": {"$gte": first, "$lte": last}}},
        # step 2: add one empty row on the first day, so step 5 always has a starting point
        {"$unionWith": {"pipeline": [{"$documents": [{"date": first}]}]}},
        # step 3: one row per day with the counts
        {"$group": {"_id": "$date", "present_count": {"$sum": PRESENT_VALUE}, "late_count": {"$sum": ONE_IF_LATE}}},
        # step 4: turn the "2026-07-06" text into a real date
        {"$addFields": {"day": {"$dateFromString": {"dateString": "$_id"}}}},
        # step 5: $densify adds the missing days (weekends, days with no records)
        {"$densify": {"field": "day", "range": {"step": 1, "unit": "day", "bounds": [first_midnight, day_after_last]}}},
        # step 6: fill in the new empty days
        {"$addFields": {
            "date": {"$dateToString": {"date": "$day", "format": "%Y-%m-%d"}},
            "present_count": {"$ifNull": ["$present_count", 0]},
            "late_count": {"$ifNull": ["$late_count", 0]},
            "is_working_day": {"$lte": [{"$isoDayOfWeek": "$day"}, 5]},
        }},
        # step 7: headcount = how many join dates are on or before this day (R9)
        {"$addFields": {"headcount": {"$size": {"$filter": {
            "input": join_dates,
            "cond": {"$lte": ["$$this", "$date"]},
        }}}}},
        # step 8: rate only on working days with people, otherwise None
        {"$addFields": {"attendance_rate": {"$cond": [
            {"$and": ["$is_working_day", {"$gt": ["$headcount", 0]}]},
            {"$divide": ["$present_count", "$headcount"]},
            None,
        ]}}},
        # step 9: average of this day and the 6 days before it ($avg skips None)
        {"$setWindowFields": {"sortBy": {"day": 1}, "output": {
            "moving_avg_7d": {"$avg": "$attendance_rate", "window": {"documents": [-6, 0]}},
        }}},
        # step 10: sort by day and keep only the fields we return
        {"$sort": {"day": 1}},
        {"$project": {"_id": 0, "date": 1, "is_working_day": 1, "headcount": 1, "present_count": 1,
                      "late_count": 1, "attendance_rate": 1, "moving_avg_7d": 1}},
    ]


@router.get("/analytics/departments/{department}/trend")
def department_trend(department: str, from_day: date = Query(alias="from"), to_day: date = Query(alias="to")):
    items = list(logs.aggregate(department_trend_pipeline(department, from_day, to_day)))
    for row in items:
        row["attendance_rate"] = round_half_up(row["attendance_rate"], 4)
        row["moving_avg_7d"] = round_half_up(row["moving_avg_7d"], 4)
    return {"department": department, "items": items}
