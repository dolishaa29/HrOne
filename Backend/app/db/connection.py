import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv() 

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True, serverSelectionTimeoutMS=3000)
db = client[os.getenv("MONGO_DB", "attendance_db")]
employees = db["employees"]
logs = db["attendance_logs"]


def create_indexes():
    employees.create_index("emp_code", unique=True)
    employees.create_index([("department", 1), ("emp_code", 1)])
    employees.create_index("joined_on")

    logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
    logs.create_index([("date", -1), ("emp_code", 1)])
    logs.create_index([("status", 1), ("date", -1), ("emp_code", 1)])
    logs.create_index([("emp_code", 1), ("punch_in", -1)])
