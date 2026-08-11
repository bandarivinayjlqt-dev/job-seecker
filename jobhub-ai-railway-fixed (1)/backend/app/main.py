from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timezone
from bson import ObjectId
from .config import settings
from .db import init_db, users, jobs, sources, logs
from .security import hash_password, verify_password, token, current_user, admin_user
from .ai import parse_resume, embed, cosine, career_chat
from .sources import public_career_page
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio
import io


app = FastAPI(title="JobHub AI API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Register(BaseModel):
    name: str
    email: EmailStr
    password: str


class Login(BaseModel):
    email: EmailStr
    password: str


class Profile(BaseModel):
    skills: list[str] = Field(default_factory=list)
    experience_years: float = 0
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_job_types: list[str] = Field(default_factory=list)
    remote_only: bool = False


class Chat(BaseModel):
    message: str


class Source(BaseModel):
    name: str
    source_type: str = "public_career_page"
    base_url: str = ""
    company: str = ""
    location: str = ""
    enabled: bool = True


def ser(x):
    if not x:
        return None

    x = dict(x)

    if "_id" in x:
        x["id"] = str(x.pop("_id"))

    # ObjectIds are not JSON serializable.
    for key, value in list(x.items()):
        if isinstance(value, ObjectId):
            x[key] = str(value)

    return x


def object_id_or_404(value: str):
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")


@app.on_event("startup")
async def startup():
    await init_db()

    admin_email = settings.admin_email.lower()

    if not await users.find_one({"email": admin_email}):
        await users.insert_one(
            {
                "name": "JobHub Admin",
                "email": admin_email,
                "password_hash": hash_password(settings.admin_password),
                "role": "admin",
                "skills": [],
                "experience_years": 0,
                "preferred_roles": [],
                "preferred_locations": [],
                "preferred_job_types": [],
                "remote_only": False,
            }
        )


@app.get("/")
async def root():
    index = Path(__file__).resolve().parent.parent / "static" / "index.html"

    if index.exists():
        return FileResponse(index)

    return {
        "name": "JobHub AI",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "jobhub-ai",
    }


@app.post("/api/auth/register")
async def register(x: Register):
    email = x.email.lower()

    if await users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    d = {
        "name": x.name,
        "email": email,
        "password_hash": hash_password(x.password),
        "role": "user",
        "skills": [],
        "experience_years": 0,
        "preferred_roles": [],
        "preferred_locations": [],
        "preferred_job_types": [],
        "remote_only": False,
    }

    r = await users.insert_one(d)
    d["_id"] = r.inserted_id

    return {
        "token": token(str(r.inserted_id)),
        "user": ser(d),
    }


@app.post("/api/auth/login")
async def login(x: Login):
    u = await users.find_one({"email": x.email.lower()})

    if not u or not verify_password(x.password, u["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return {
        "token": token(str(u["_id"])),
        "user": ser(u),
    }


@app.get("/api/profile")
async def profile(u=Depends(current_user)):
    return ser(u)


@app.put("/api/profile")
async def update_profile(x: Profile, u=Depends(current_user)):
    await users.update_one(
        {"_id": u["_id"]},
        {"$set": x.model_dump()},
    )

    return {"message": "Profile updated"}


@app.post("/api/profile/resume")
async def resume(
    file: UploadFile = File(...),
    u=Depends(current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    filename = file.filename.lower()

    if not filename.endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Use PDF, DOCX or TXT",
        )

    data = await file.read()

    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Resume exceeds 8 MB",
        )

    if filename.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    elif filename.endswith(".docx"):
        from docx import Document

        document = Document(io.BytesIO(data))
        text = "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
        )

    else:
        text = data.decode("utf-8", "ignore")

    info = await parse_resume(text)

    profile_text = " ".join(
        [
            info.get("summary", ""),
            " ".join(info.get("skills", [])),
            " ".join(info.get("preferred_roles", [])),
        ]
    )

    vector = await embed(profile_text)

    await users.update_one(
        {"_id": u["_id"]},
        {
            "$set": {
                "resume_text": text,
                "resume_filename": file.filename,
                "skills": info.get("skills", []),
                "experience_years": info.get("experience_years", 0),
                "preferred_roles": info.get("preferred_roles", []),
                "resume_embedding": vector,
            }
        },
    )

    return info


@app.get("/api/jobs")
async def get_jobs(
    q: str = "",
    location: str = "",
    work_mode: str = "",
    job_type: str = "",
    limit: int = Query(40, ge=1, le=100),
):
    query = {}

    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"company": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"skills": {"$regex": q, "$options": "i"}},
        ]

    if location:
        query["location"] = {"$regex": location, "$options": "i"}

    if work_mode:
        query["work_mode"] = work_mode

    if job_type:
        query["job_type"] = job_type

    return [
        ser(x)
        async for x in jobs.find(query)
        .sort("created_at", -1)
        .limit(limit)
    ]


@app.get("/api/jobs/saved/me")
async def saved(u=Depends(current_user)):
    saved_ids = u.get("saved_jobs", [])

    return [
        ser(x)
        async for x in jobs.find({"_id": {"$in": saved_ids}})
    ]


@app.get("/api/jobs/recommendations/me")
async def recs(u=Depends(current_user)):
    skills = u.get("skills", [])
    roles = u.get("preferred_roles", [])

    vector = u.get("resume_embedding")

    if not vector:
        vector = await embed(" ".join(skills + roles))

    output = []

    async for job in jobs.find({}):
        job_vector = job.get("embedding")

        if vector and job_vector:
            score = cosine(vector, job_vector)
        else:
            user_skills = {
                str(s).lower()
                for s in skills
            }

            job_skills = {
                str(s).lower()
                for s in job.get("skills", [])
            }

            score = len(user_skills & job_skills) / max(
                1,
                len(user_skills),
            )

        output.append((score, job))

    output.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            **ser(job),
            "match_score": round(score * 100, 1),
        }
        for score, job in output[:12]
    ]


@app.post("/api/jobs/{jid}/save")
async def save_job(
    jid: str,
    u=Depends(current_user),
):
    job_id = object_id_or_404(jid)

    if not await jobs.find_one({"_id": job_id}):
        raise HTTPException(status_code=404, detail="Job not found")

    await users.update_one(
        {"_id": u["_id"]},
        {"$addToSet": {"saved_jobs": job_id}},
    )

    return {"message": "Saved"}


@app.get("/api/jobs/{jid}")
async def get_job(jid: str):
    job_id = object_id_or_404(jid)

    x = await jobs.find_one({"_id": job_id})

    if not x:
        raise HTTPException(status_code=404, detail="Job not found")

    return ser(x)


@app.post("/api/jobs/semantic-search")
async def semantic_search(x: dict):
    query_text = str(x.get("query", "")).strip()

    if not query_text:
        return []

    vector = await embed(query_text)

    if not vector:
        return [
            ser(j)
            async for j in jobs.find(
                {
                    "$or": [
                        {"title": {"$regex": query_text, "$options": "i"}},
                        {
                            "description": {
                                "$regex": query_text,
                                "$options": "i",
                            }
                        },
                        {
                            "skills": {
                                "$regex": query_text,
                                "$options": "i",
                            }
                        },
                    ]
                }
            ).limit(20)
        ]

    output = []

    async for job in jobs.find(
        {"embedding": {"$exists": True}}
    ):
        job_vector = job.get("embedding")

        if job_vector:
            score = cosine(vector, job_vector)
            output.append((score, job))

    output.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            **ser(job),
            "semantic_score": round(score * 100, 1),
        }
        for score, job in output[:20]
    ]


@app.post("/api/jobs/seed")
async def seed():
    demo = [
        (
            "Python AI Engineer",
            "Nova Labs",
            "Hyderabad",
            ["python", "fastapi", "llm", "mongodb"],
            "Hybrid",
        ),
        (
            "React Frontend Developer",
            "PixelWorks",
            "Bengaluru",
            ["react", "javascript", "tailwind css", "git"],
            "Remote",
        ),
        (
            "Machine Learning Engineer",
            "DataForge",
            "Pune",
            ["python", "machine learning", "pytorch", "nlp"],
            "On-site",
        ),
        (
            "Backend Engineer",
            "CloudNest",
            "Remote",
            ["node.js", "mongodb", "rest api", "docker"],
            "Remote",
        ),
        (
            "Data Analyst",
            "InsightWorks",
            "Chennai",
            ["python", "sql", "pandas", "numpy"],
            "Hybrid",
        ),
    ]

    for i, (title, company, location, skills, mode) in enumerate(demo):
        job = {
            "title": title,
            "company": company,
            "location": location,
            "salary_min": 500000 + i * 100000,
            "salary_max": 1000000 + i * 150000,
            "experience_min": i % 3,
            "job_type": "Full-time",
            "work_mode": mode,
            "description": f"Build and maintain {title} solutions.",
            "skills": skills,
            "source": "JobHub Demo",
            "source_url": f"https://example.com/jobs/{i + 1}",
            "external_id": f"demo-{i + 1}",
            "created_at": datetime.now(timezone.utc),
        }

        job["embedding"] = await embed(
            " ".join(
                [
                    title,
                    company,
                    job["description"],
                    *skills,
                ]
            )
        )

        await jobs.update_one(
            {
                "source": job["source"],
                "external_id": job["external_id"],
            },
            {"$set": job},
            upsert=True,
        )

    return {"message": "Demo jobs seeded"}


@app.post("/api/chat")
async def chat(
    x: Chat,
    u=Depends(current_user),
):
    return {"reply": await career_chat(x.message, u)}


@app.get("/api/admin/stats")
async def stats(a=Depends(admin_user)):
    return {
        "users": await users.count_documents({}),
        "jobs": await jobs.count_documents({}),
        "sources": await sources.count_documents({}),
        "logs": await logs.count_documents({}),
    }


@app.get("/api/admin/sources")
async def source_list(a=Depends(admin_user)):
    return [
        ser(x)
        async for x in sources.find({})
    ]


@app.post("/api/admin/sources")
async def source_add(
    x: Source,
    a=Depends(admin_user),
):
    d = x.model_dump()
    d["created_at"] = datetime.now(timezone.utc)

    r = await sources.insert_one(d)
    d["_id"] = r.inserted_id

    return ser(d)


@app.get("/api/admin/logs")
async def log_list(a=Depends(admin_user)):
    return [
        ser(x)
        async for x in logs.find({})
        .sort("started_at", -1)
        .limit(200)
    ]


async def scheduler():
    while True:
        try:
            async for source in sources.find({"enabled": True}):
                started = datetime.now(timezone.utc)

                try:
                    rows = await public_career_page(source)

                    for row in rows:
                        row["created_at"] = datetime.now(timezone.utc)

                        row["embedding"] = await embed(
                            " ".join(
                                [
                                    row.get("title", ""),
                                    row.get("company", ""),
                                    row.get("description", ""),
                                    *row.get("skills", []),
                                ]
                            )
                        )

                        await jobs.update_one(
                            {
                                "source": row.get(
                                    "source",
                                    source.get("name", ""),
                                ),
                                "external_id": row.get(
                                    "external_id",
                                    row.get("source_url", ""),
                                ),
                            },
                            {"$set": row},
                            upsert=True,
                        )

                    await logs.insert_one(
                        {
                            "source": source.get("name", ""),
                            "status": "success",
                            "count": len(rows),
                            "started_at": started,
                            "finished_at": datetime.now(timezone.utc),
                        }
                    )

                except Exception as exc:
                    await logs.insert_one(
                        {
                            "source": source.get("name", ""),
                            "status": "error",
                            "error": str(exc),
                            "started_at": started,
                            "finished_at": datetime.now(timezone.utc),
                        }
                    )

        except Exception:
            pass

        await asyncio.sleep(
            max(1, settings.scrape_interval_hours) * 3600
        )


@app.on_event("startup")
async def run_scheduler():
    asyncio.create_task(scheduler())


# Serve the Vite production build from the same Railway service.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "static"

if (FRONTEND_DIR / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIR / "assets"),
        name="frontend-assets",
    )


@app.get("/{path:path}")
async def frontend_routes(path: str):
    if path.startswith("api/"):
        raise HTTPException(
            status_code=404,
            detail="API endpoint not found",
        )

    requested = FRONTEND_DIR / path

    if requested.is_file():
        return FileResponse(requested)

    index = FRONTEND_DIR / "index.html"

    if index.exists():
        return FileResponse(index)

    raise HTTPException(
        status_code=404,
        detail="Not found",
    )
