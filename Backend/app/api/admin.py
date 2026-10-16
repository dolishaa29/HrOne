import json
from datetime import date
from typing import Literal, Optional

from bson import json_util
from fastapi import APIRouter, HTTPException, Query

from app.api.analytics import department_summary_pipeline, department_trend_pipeline, late_leaderboard_pipeline, monthly_pipeline
from app.api.attendance import ATTENDANCE_SORT, build_attendance_query
from app.db.connection import db
from app.utils.constants import ALL_STATUSES, MONTH_PATTERN

router = APIRouter()


@router.get("/admin/explain/{endpoint}")
def explain(
    endpoint: Literal["attendance_list", "employee_monthly", "department_summary", "late_leaderboard", "department_trend"],
    emp_code: Optional[str] = None,
    month: Optional[str] = Query(None, pattern=MONTH_PATTERN),
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[ALL_STATUSES] = None,
    from_day: Optional[date] = Query(None, alias="from"),
    to_day: Optional[date] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if endpoint == "attendance_list":
        collection = "attendance_logs"
        command = {
            "find": collection,
            "filter": build_attendance_query(emp_code, date_from, date_to, status),
            "sort": dict(ATTENDANCE_SORT),
            "skip": (page - 1) * page_size,
            "limit": page_size,
        }

    elif endpoint == "employee_monthly":
        if emp_code is None or month is None:
            raise HTTPException(422, "emp_code and month are required")
        collection = "attendance_logs"
        command = {"aggregate": collection, "pipeline": monthly_pipeline(emp_code, month), "cursor": {}}

    elif endpoint == "department_summary":
        if month is None:
            raise HTTPException(422, "month is required")
        collection = "employees"
        command = {"aggregate": collection, "pipeline": department_summary_pipeline(month, department), "cursor": {}}

    elif endpoint == "late_leaderboard":
        if month is None:
            raise HTTPException(422, "month is required")
        collection = "attendance_logs"
        command = {"aggregate": collection, "pipeline": late_leaderboard_pipeline(month, limit, department), "cursor": {}}

    else:  
        if department is None or from_day is None or to_day is None:
            raise HTTPException(422, "department, from and to are required")
        collection = "attendance_logs"
        command = {"aggregate": collection, "pipeline": department_trend_pipeline(department, from_day, to_day), "cursor": {}}

    result = db.command("explain", command, verbosity="executionStats")
    return {"endpoint": endpoint, "collection": collection, "explain": json.loads(json_util.dumps(result))}
