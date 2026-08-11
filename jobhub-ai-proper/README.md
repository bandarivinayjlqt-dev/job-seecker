# JobHub AI

Full-stack AI job aggregator: React/Vite/Tailwind + FastAPI + MongoDB + OpenAI.

## Run backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Run frontend
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```
Open http://localhost:5173. API docs: http://localhost:8000/docs.

Seed demo jobs with POST /api/jobs/seed. Admin credentials come from .env.

For LinkedIn, Indeed, Naukri and Glassdoor, use official/licensed APIs or feeds. The supplied public career-page adapter does not bypass CAPTCHAs, login walls, robots restrictions or anti-bot controls.


## OpenAI API key setup

Create `backend/.env` from `backend/.env.example`:

```text
OPENAI_API_KEY=your_new_key_here
```

The backend already reads this value automatically. Do not put the OpenAI key in React/frontend code.
