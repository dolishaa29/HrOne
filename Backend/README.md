# Employee Attendance & Analytics API (backend)

Full documentation: see the [README in the repository root](../README.md).

Quick start (from this folder):
```bash
python -m venv .venv
.venv\Scripts\activate            # Linux / macOS: source .venv/bin/activate
pip install -r requirements.txt
# set MONGO_URI and MONGO_DB (environment variables or a local .env file)
uvicorn app.main:app --port 8000
```
API docs: http://localhost:8000/docs
