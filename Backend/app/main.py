from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, analytics, attendance, employees
from app.db.connection import create_indexes


@asynccontextmanager
async def lifespan(app):
    create_indexes() 
    yield


app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0", lifespan=lifespan)

app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(analytics.router)
app.include_router(admin.router)
