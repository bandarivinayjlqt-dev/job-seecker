from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Query,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,EmailStr
from datetime import datetime,timezone
from bson import ObjectId
from .config import settings
from .db import init_db,users,jobs,sources,logs
from .security import hash_password,verify_password,token,current_user,admin_user
from .ai import parse_resume,embed,cosine,career_chat
from .sources import public_career_page
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio,io
app=FastAPI(title='JobHub AI API',version='1.0')
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_url,'http://localhost:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
class Register(BaseModel): name:str; email:EmailStr; password:str
class Login(BaseModel): email:EmailStr; password:str
class Profile(BaseModel): skills:list[str]=[]; experience_years:float=0; preferred_roles:list[str]=[]; preferred_locations:list[str]=[]; preferred_job_types:list[str]=[]; remote_only:bool=False
class Chat(BaseModel): message:str
class Source(BaseModel): name:str; source_type:str='public_career_page'; base_url:str=''; company:str=''; location:str=''; enabled:bool=True
def ser(x):
 if not x:return None
 x=dict(x); x['id']=str(x.pop('_id')); return x
@app.on_event('startup')
async def startup():
 await init_db()
 if not await users.find_one({'email':settings.admin_email.lower()}): await users.insert_one({'name':'JobHub Admin','email':settings.admin_email.lower(),'password_hash':hash_password(settings.admin_password),'role':'admin','skills':[]})
@app.get('/')
async def root():
    index=Path(__file__).resolve().parent.parent / 'static' / 'index.html'
    if index.exists():
        return FileResponse(index)
    return {'name':'JobHub AI','status':'running','docs':'/docs'}
@app.post('/api/auth/register')
async def register(x:Register):
 if await users.find_one({'email':x.email.lower()}):raise HTTPException(400,'Email already registered')
 d={'name':x.name,'email':x.email.lower(),'password_hash':hash_password(x.password),'role':'user','skills':[],'experience_years':0,'preferred_roles':[],'preferred_locations':[],'preferred_job_types':[],'remote_only':False}; r=await users.insert_one(d); d['_id']=r.inserted_id; return {'token':token(str(r.inserted_id)),'user':ser(d)}
@app.post('/api/auth/login')
async def login(x:Login):
 u=await users.find_one({'email':x.email.lower()})
 if not u or not verify_password(x.password,u['password_hash']):raise HTTPException(401,'Invalid email or password')
 return {'token':token(str(u['_id'])),'user':ser(u)}
@app.get('/api/profile')
async def profile(u=Depends(current_user)):return ser(u)
@app.put('/api/profile')
async def update(x:Profile,u=Depends(current_user)):await users.update_one({'_id':u['_id']},{'$set':x.model_dump()});return {'message':'Profile updated'}
@app.post('/api/profile/resume')
async def resume(file:UploadFile=File(...),u=Depends(current_user)):
 if not file.filename.lower().endswith(('.pdf','.docx','.txt')):raise HTTPException(400,'Use PDF, DOCX or TXT')
 data=await file.read()
 if len(data)>8*1024*1024:raise HTTPException(413,'Resume exceeds 8 MB')
 if file.filename.lower().endswith('.pdf'):
  from pypdf import PdfReader; text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(data)).pages)
 elif file.filename.lower().endswith('.docx'):
  from docx import Document; text='\n'.join(p.text for p in Document(io.BytesIO(data)).paragraphs)
 else:text=data.decode('utf-8','ignore')
 info=await parse_resume(text); v=await embed(' '.join([info.get('summary',''),' '.join(info.get('skills',[])),' '.join(info.get('preferred_roles',[]))])); await users.update_one({'_id':u['_id']},{'$set':{'resume_text':text[:20000],'resume_filename':file.filename,'skills':info.get('skills',[]),'experience_years':info.get('experience_years',0),'preferred_roles':info.get('preferred_roles',[]),'resume_embedding':v}}); return info
@app.get('/api/jobs')
async def get_jobs(q:str='',location:str='',work_mode:str='',job_type:str='',limit:int=Query(40,le=100)):
 query={}
 if q:query['$or']=[{'title':{'$regex':q,'$options':'i'}},{'company':{'$regex':q,'$options':'i'}},{'description':{'$regex':q,'$options':'i'}},{'skills':{'$regex':q,'$options':'i'}}]
 if location:query['location']={'$regex':location,'$options':'i'}
 if work_mode:query['work_mode']=work_mode
 if job_type:query['job_type']=job_type
 return [ser(x) async for x in jobs.find(query).sort('created_at',-1).limit(limit)]
@app.get('/api/jobs/{jid}')
async def get_job(jid:str):
 x=await jobs.find_one({'_id':ObjectId(jid)})
 if not x:raise HTTPException(404,'Job not found')
 return ser(x)
@app.post('/api/jobs/{jid}/save')
async def save(jid:str,u=Depends(current_user)):await users.update_one({'_id':u['_id']},{'$addToSet':{'saved_jobs':ObjectId(jid)}});return {'message':'Saved'}
@app.get('/api/jobs/saved/me')
async def saved(u=Depends(current_user)):return [ser(x) async for x in jobs.find({'_id':{'$in':u.get('saved_jobs',[])}})]
@app.get('/api/jobs/recommendations/me')
async def recs(u=Depends(current_user)):
 v=u.get('resume_embedding') or await embed(' '.join(u.get('skills',[])+u.get('preferred_roles',[]))); out=[]
 async for j in jobs.find({}):
  s=cosine(v,j.get('embedding')) if v else len(set(map(str.lower,u.get('skills',[])))&set(map(str.lower,j.get('skills',[]))))/max(1,len(u.get('skills',[]))); out.append((s,j))
 out.sort(key=lambda z:z[0],reverse=True); return [{**ser(j),'match_score':round(s*100,1)} for s,j in out[:12]]
@app.post('/api/jobs/semantic-search')
async def semantic(x:dict):
 v=await embed(x.get('query',''))
 if not v:return [ser(j) async for j in jobs.find({'$text':{'$search':x.get('query','')}}).limit(20)]
 out=[]
 async for j in jobs.find({'embedding':{'$exists':True}}):out.append((cosine(v,j['embedding']),j))
 out.sort(key=lambda z:z[0],reverse=True); return [{**ser(j),'semantic_score':round(s*100,1)} for s,j in out[:20]]
@app.post('/api/jobs/seed')
async def seed():
 demo=[('Python AI Engineer','Nova Labs','Hyderabad',['python','fastapi','llm','mongodb'],'Hybrid'),('React Frontend Developer','PixelWorks','Bengaluru',['react','javascript','tailwind css','git'],'Remote'),('Machine Learning Engineer','DataForge','Pune',['python','machine learning','pytorch','nlp'],'On-site'),('Backend Engineer','CloudNest','Remote',['node.js','mongodb','rest api','docker'],'Remote'),('Data Analyst','InsightWorks','Chennai',['python','sql','pandas','numpy'],'Hybrid')]
 for i,(t,c,l,s,m) in enumerate(demo):
  d={'title':t,'company':c,'location':l,'salary_min':500000+i*100000,'salary_max':1000000+i*150000,'experience_min':i%3,'job_type':'Full-time','work_mode':m,'description':f'Build and maintain {t} solutions.','skills':s,'source':'JobHub Demo','source_url':f'https://example.com/jobs/{i+1}','external_id':f'demo-{i+1}','created_at':datetime.now(timezone.utc)}; d['embedding']=await embed(' '.join([t,c,d['description']]+s)); await jobs.update_one({'source':d['source'],'external_id':d['external_id']},{'$set':d},upsert=True)
 return {'message':'Demo jobs seeded'}
@app.post('/api/chat')
async def chat(x:Chat,u=Depends(current_user)):return {'reply':await career_chat(x.message,u)}
@app.get('/api/admin/stats')
async def stats(a=Depends(admin_user)):return {'users':await users.count_documents({}),'jobs':await jobs.count_documents({}),'sources':await sources.count_documents({}),'logs':await logs.count_documents({})}
@app.get('/api/admin/sources')
async def source_list(a=Depends(admin_user)):return [ser(x) async for x in sources.find({})]
@app.post('/api/admin/sources')
async def source_add(x:Source,a=Depends(admin_user)):
 d=x.model_dump();d['created_at']=datetime.now(timezone.utc);r=await sources.insert_one(d);d['_id']=r.inserted_id;return ser(d)
@app.get('/api/admin/logs')
async def log_list(a=Depends(admin_user)):return [ser(x) async for x in logs.find({}).sort('started_at',-1).limit(200)]
async def scheduler():
 while True:
  try:
   async for s in sources.find({'enabled':True}):
    st=datetime.now(timezone.utc)
    try:
     rows=await public_career_page(s)
     for row in rows:
      row['created_at']=datetime.now(timezone.utc);row['embedding']=await embed(row['title']+' '+row['company']+' '+row['description']);await jobs.update_one({'source':row['source'],'external_id':row['external_id']},{'$set':row},upsert=True)
     await logs.insert_one({'source':s['name'],'status':'success','count':len(rows),'started_at':st,'finished_at':datetime.now(timezone.utc)})
    except Exception as e:await logs.insert_one({'source':s['name'],'status':'error','error':str(e),'started_at':st,'finished_at':datetime.now(timezone.utc)})
  except Exception:pass
  await asyncio.sleep(max(1,settings.scrape_interval_hours)*3600)
@app.on_event('startup')
async def run_scheduler():asyncio.create_task(scheduler())


# Serve the Vite production build when deployed as a single Railway service.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'static'
if (FRONTEND_DIR / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND_DIR / 'assets'), name='frontend-assets')

@app.get('/{path:path}')
async def frontend_routes(path: str):
    if path.startswith('api/'):
        raise HTTPException(status_code=404, detail='API endpoint not found')
    requested = FRONTEND_DIR / path
    if requested.is_file():
        return FileResponse(requested)
    index = FRONTEND_DIR / 'index.html'
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail='Not found')
