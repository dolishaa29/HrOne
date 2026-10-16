# REVIEW.md

Defects found in the starter `app/main.py`.

| # | Where | What is wrong | How you'd notice it | How I fixed it |
|---|---|---|---|---|
| 1 | `compute_late_minutes` | Works on the server's local time, not IST. `punch_in.replace(hour=...)` sets the shift start in whatever time zone the datetime happens to have (naive local time). | Run the server in UTC: a 09:45 IST punch-in (04:15 UTC) is compared with 09:30 UTC and is never late. | Convert the punch to IST and build the shift start with `tzinfo=IST` (`shift_start_time`). |
| 2 | `compute_late_minutes` | Grace check uses floored minutes: `minutes > 10`. 09:40:30 floors to 10, so it returns 0, but R2 says anything strictly after 10:00 is late. | Punch at 09:40:01 with a 09:30 shift: returns 0, expected 10. | Compare seconds: late if `seconds > 600`, then `seconds // 60`. |
| 3 | `compute_late_minutes` | Overnight shifts: the shift start is put on the punch's calendar day. A 05:00 punch for a 22:00 shift gives a negative difference. | Shift 22:00-06:00, punch 05:00: returns 0. | Shift start is built from the record's attendance date (R1), not the punch's calendar day. |
| 4 | `compute_work_hours` | Uses Python `round()`, which works on the float and is not half-up. | 54 seconds = 0.015 h: `round()` gives 0.01, R4 expects 0.02. | `Decimal` with `ROUND_HALF_UP` (`round_half_up`). |
| 5 | `compute_overtime` | No 30-minute minimum (R3). | Punch out 18:45 for an 18:30 shift: returns 15, expected 0. | Return the minutes only when `>= 30`. |
| 6 | `compute_overtime` | Overnight shift end is not moved to the next day. | Shift 22:00-06:00, out 06:40 next day: gives about 1000 minutes instead of 40. | `shift_end_time` adds one day when `shift_end <= shift_start`. |
| 7 | `health` | Always returns `ok`, even when MongoDB is down. | Stop MongoDB: `/health` still says 200. | Send `ping` to MongoDB; on error return 503. |
| 8 | `create_employee` | Check-then-insert with no unique index: two parallel requests both pass the check. | 10 parallel POSTs with the same `emp_code`: more than one 201. | Unique index on `emp_code`; catch `DuplicateKeyError` and return 409. |
| 9 | `create_employee` | `created_at = datetime.now()` is naive local time; MongoDB stores it as if it were UTC (5:30 off in India). The response returns a datetime string, not epoch ms. | Compare `created_at` with the real time. | `datetime.now(UTC)`; returned as epoch ms. |
| 10 | `EmployeeIn` | No validation: any `emp_code`, email, shift time or date is accepted, and `shift_start == shift_end` is allowed. | POST `emp_code: "x"`, `shift_start: "25:99"`: 201. | Field patterns and lengths from the contract plus a validator for equal shift times. Returns 422. |
| 11 | `list_employees` | `skip = page * page_size` skips the first page. | 6 employees, `page=1`: `items` is empty. | `skip = (page - 1) * page_size`. |
| 12 | `list_employees` | `total` counts the whole collection, not the filtered set. | `?department=Eng`: total shows all employees. | `count_documents(query)`. |
| 13 | `list_employees` | No sort; order is undefined. | Pages can return items in any order. | `.sort("emp_code", 1)` (index `department, emp_code`). |
| 14 | `list_employees`, `list_attendance` | `page` and `page_size` are not validated. `page=0` gives a negative skip (500) and `page_size` has no maximum. | `?page=0`: 500; `?page_size=100000` dumps everything. | `Query(ge=1)`, `page_size` `le=100`. Returns 422. |
| 15 | `punch_in` | Unknown employee: `emp` is `None`, so `emp["shift_start"]` raises a `TypeError` (500). | Punch in `EMP9999`: 500. | `get_employee` returns 404. |
| 16 | `punch_in` | `status` accepts any string, including `ABSENT`, `LEAVE`, `HELLO`. | Punch in with `"status": "ABSENT"`: 201. | `Literal["PRESENT", "WFH", "ON_DUTY"]`. Returns 422. |
| 17 | `punch_in` | `punched_at` is `Optional[int]` in lax mode: strings like `"1783312500000"`, floats like `1.0` and seconds like `1783312500` are all accepted. | Send seconds: a record in 1970. | Strict int with range 100000000000 - 4102444800000. Returns 422. |
| 18 | `punch_in` | `datetime.fromtimestamp(...)` uses the server's time zone and returns a naive datetime. The attendance date comes from the server zone, not IST, and the value is stored with the wrong offset. Milliseconds are not truncated (R1). | Server in UTC, punch at 02:00 IST: the date is the previous day. | `EPOCH + timedelta(seconds=ms // 1000)`, aware UTC, then IST for the date. |
| 19 | `punch_in` | Overnight shifts: the date is always the punch's calendar date. | 22:00-06:00 shift, punch 01:00: the record goes to the wrong day. | `get_attendance_date` (R1). |
| 20 | `punch_in` | Check-then-insert race: two parallel punch-ins both get 201 (two records for one day). | 10 parallel identical punch-ins. | Unique index on `(emp_code, date)`; `DuplicateKeyError` returns 409. |
| 21 | `punch_in` | `if body.punched_at` treats 0 as "missing". | Only an edge case (0 is now rejected by the range anyway). | `is not None`. |
| 22 | `punch_in`, `list_attendance` | Response contains `id` (the `_id`) and datetimes instead of epoch ms. The contract says no id, and instants are in ms. | Look at the response. | `record_to_json` builds the response explicitly. |
| 23 | `list_attendance` | Loads every matching document into memory and sorts in Python. Very slow at 100k records. | `GET /attendance` on 100k records. | `find().sort().skip().limit()` in MongoDB, backed by indexes. |
| 24 | `list_attendance` | The sort is only by `date`; the contract says `date` desc, then `emp_code` asc. | Same-day records come back in random order. | Sort `{date: -1, emp_code: 1}`. |
| 25 | `list_attendance` | No validation: `date_from > date_to`, a bad date format or an unknown status are accepted. | `?date_from=2026-07-09&date_to=2026-07-01`: 200 with nothing. | `date` typed params, `Status` literal, explicit 422. |
| 26 | `list_attendance` | Legacy records without `half_day` / `history` are returned without those fields. | Fetch the legacy sample record. | `record_to_json` defaults them to `false` / `[]`. |
| 27 | whole file | No indexes are created. | `explain` shows `COLLSCAN`. | `create_indexes()` at startup. |
| 28 | `MongoClient` | Without `tz_aware=True`, PyMongo returns naive datetimes. Mixing them with aware ones raises errors or gives wrong times. | Subtracting a stored `punch_in` from an aware datetime raises a `TypeError`. | `MongoClient(..., tz_aware=True)`. |

## Looked at and decided were not defects
- `load_dotenv()`: by default it does **not** override variables that are already set, so real environment variables win as required.
- `IST = timezone(timedelta(hours=5, minutes=30))` is correct.
- `doc.pop("_id", None)` after `insert_one` in `create_employee` is fine (`insert_one` adds `_id` to the dict). I replaced it anyway with `employee_to_json`.
- The date range filter in `list_attendance` compares `YYYY-MM-DD` strings. This is correct, because that format sorts the same way as the dates.
