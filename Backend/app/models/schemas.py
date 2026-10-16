"""Request bodies. FastAPI checks them and answers 422 if they are wrong."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.utils.constants import ALL_STATUSES, MAX_MS, MIN_MS, TIME_PATTERN


class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=TIME_PATTERN)
    shift_end: str = Field("18:30", pattern=TIME_PATTERN)
    joined_on: date

    @model_validator(mode="after")
    def check_shift(self):
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self


# strict=True: only whole numbers are accepted (no "123" strings, no 1.5 floats)
class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, strict=True, ge=MIN_MS, le=MAX_MS)
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, strict=True, ge=MIN_MS, le=MAX_MS)


class RegularizeIn(BaseModel):
    status: Optional[ALL_STATUSES] = None
    punch_in: Optional[int] = Field(None, strict=True, ge=MIN_MS, le=MAX_MS)
    punch_out: Optional[int] = Field(None, strict=True, ge=MIN_MS, le=MAX_MS)
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)
