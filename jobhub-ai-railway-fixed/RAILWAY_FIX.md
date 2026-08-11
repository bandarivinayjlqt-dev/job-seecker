# Railway deployment fix

The error `npm: not found` means Railway is using Railpack/Node detection instead of the Dockerfile.
This project is intended to use the Dockerfile.

IMPORTANT: the repository root connected to Railway MUST contain these files directly:

Dockerfile
railway.json
railway.toml
backend/
frontend/

Do NOT connect a repository where these files are inside another nested folder.

Railway's current docs say a Dockerfile in the source repository is automatically used. If the deployment still shows `npm run build` as a Railpack step, check the deployment's source/root directory and make sure the connected repository points to this folder.

For GitHub:
1. Create a repository, e.g. jobhub-ai.
2. Upload the CONTENTS of this folder, not the folder itself.
3. GitHub root should show Dockerfile immediately.
4. Connect that repository to Railway.
5. Redeploy.

For Railway variables, add:
MONGODB_URL
DATABASE_NAME
JWT_SECRET
JWT_EXPIRE_MINUTES
OPENAI_API_KEY
OPENAI_MODEL
OPENAI_EMBEDDING_MODEL
FRONTEND_URL
ADMIN_EMAIL
ADMIN_PASSWORD
SCRAPE_INTERVAL_HOURS

Never commit your real OpenAI API key.
