import re,json
from .config import settings
SKILLS={'python','javascript','typescript','react','node.js','fastapi','django','flask','java','sql','mysql','postgresql','mongodb','docker','kubernetes','aws','azure','git','machine learning','deep learning','nlp','pandas','numpy','tensorflow','pytorch','scikit-learn','xgboost','llm','rag','agents','tailwind css','rest api'}
def local_skills(t):
 t=t.lower(); return sorted([s for s in SKILLS if re.search(r'(?<!\w)'+re.escape(s)+r'(?!\w)',t)])
async def client():
 if not settings.openai_api_key:return None
 from openai import AsyncOpenAI
 return AsyncOpenAI(api_key=settings.openai_api_key)
async def parse_resume(text):
 fallback={'summary':text[:700],'skills':local_skills(text),'experience_years':0,'preferred_roles':[]}
 c=await client()
 if not c:return fallback
 prompt='Extract career information from this resume. Return ONLY JSON with keys summary, skills, experience_years, preferred_roles.\nResume:\n'+text[:15000]
 try:
  r=await c.responses.create(model=settings.openai_model,input=prompt); x=json.loads(r.output_text); x['skills']=sorted(set(x.get('skills',[])+local_skills(text))); return x
 except Exception:return fallback
async def embed(text):
 c=await client()
 if not c:return None
 try:
  r=await c.embeddings.create(model=settings.openai_embedding_model,input=text[:8000]); return r.data[0].embedding
 except Exception:return None
def cosine(a,b):
 if not a or not b or len(a)!=len(b):return 0
 d=sum(x*y for x,y in zip(a,b)); na=sum(x*x for x in a)**.5; nb=sum(y*y for y in b)**.5; return d/(na*nb) if na and nb else 0
async def career_chat(msg,u):
 c=await client()
 if not c:return 'Add OPENAI_API_KEY to enable Career AI. Job search and resume skill extraction still work without it.'
 prompt=f'You are JobHub AI Career Assistant. Give concise practical career guidance. Skills: {u.get("skills",[])}. Experience: {u.get("experience_years",0)}. Roles: {u.get("preferred_roles",[])}. Question: {msg}'
 r=await c.responses.create(model=settings.openai_model,input=prompt); return r.output_text
