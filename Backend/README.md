# Employee Attendance & Analytics API

FastAPI + MongoDB.

```
app/
  main.py          creates the app and adds the routers
  db/              MongoDB connection + indexes
  models/          request bodies (validation)
  utils/           constants, helpers, business rules R1 - R5
  api/             endpoints: employees, attendance, analytics, admin
```

## Run
```bash
python -m venv .venv
.venv\Scripts\activate          # Linux / macOS: source .venv/bin/activate
pip install -r requirements.txt
# set MONGO_URI and MONGO_DB (environment variables, or a local .env file)
uvicorn app.main:app --port 8000
```
Open http://localhost:8000/docs to try the endpoints. `python sample_seed.py` loads the sample data.

## Notes
- Indexes are created automatically at startup.
- Times in the API are epoch milliseconds; MongoDB stores UTC datetimes; shift times and dates are IST.
- All endpoints in the contract are implemented. Fixes to the starter are listed in `REVIEW.md`, design choices in `DECISIONS.md`.
