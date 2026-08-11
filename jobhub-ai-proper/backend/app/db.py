from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings
client=AsyncIOMotorClient(settings.mongodb_url); db=client[settings.database_name]
users=db.users; jobs=db.jobs; sources=db.sources; logs=db.logs
async def init_db():
 await users.create_index('email',unique=True)
 await jobs.create_index([('source',1),('external_id',1)],unique=True,sparse=True)
 await jobs.create_index([('title','text'),('description','text'),('company','text')])
 await sources.create_index('name',unique=True)
