# JobHub AI - Railway deployment

## Important
Upload/push the CONTENTS of this folder to GitHub, not a folder containing this folder. Railway must see `Dockerfile` at the repository root.

## Deploy
1. Create a GitHub repository and upload these files so `Dockerfile`, `railway.json`, `backend/`, and `frontend/` are at the repository root.
2. In Railway, create a new project and deploy from that GitHub repository.
3. Railway should detect the Dockerfile automatically.
4. Add a MongoDB database (or use MongoDB Atlas) and set `MONGODB_URL`.
5. Add the remaining variables from `RAILWAY_ENV.txt`.
6. Generate a public domain in Railway.

The Dockerfile builds React and then FastAPI serves the React production build, so you get one service and one URL.

Do not put your OpenAI key in source code or commit `.env`. Use Railway Variables.
