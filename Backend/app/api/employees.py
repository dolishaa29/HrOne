"""GET /health, POST /employees, GET /employees"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db.connection import client, employees
from app.models.schemas import EmployeeIn
from app.utils.helpers import employee_to_json, now

router = APIRouter()


@router.get("/health")
def health():
    try:
        client.admin.command("ping")
    except PyMongoError:
        raise HTTPException(503, "database unavailable")
    return {"status": "ok"}


@router.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    emp = body.model_dump()
    emp["joined_on"] = body.joined_on.isoformat()  # store as "2026-01-05"
    emp["created_at"] = now()
    try:
        employees.insert_one(emp)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    return employee_to_json(emp)


@router.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = {}
    if department:
        query["department"] = department

    skip = (page - 1) * page_size  # page 1 skips nothing
    cursor = employees.find(query).sort("emp_code", 1).skip(skip).limit(page_size)

    items = []
    for emp in cursor:
        items.append(employee_to_json(emp))
    return {"items": items, "total": employees.count_documents(query), "page": page, "page_size": page_size}
