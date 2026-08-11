from datetime import datetime,timedelta,timezone
from jose import jwt,JWTError
from passlib.context import CryptContext
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from bson import ObjectId
from .config import settings
from .db import users
pwd=CryptContext(schemes=['bcrypt'],deprecated='auto'); bearer=HTTPBearer()
def hash_password(p): return pwd.hash(p)
def verify_password(p,h): return pwd.verify(p,h)
def token(uid):
 exp=datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_expire_minutes); return jwt.encode({'sub':uid,'exp':exp},settings.jwt_secret,algorithm='HS256')
async def current_user(c:HTTPAuthorizationCredentials=Depends(bearer)):
 try: u=await users.find_one({'_id':ObjectId(jwt.decode(c.credentials,settings.jwt_secret,algorithms=['HS256'])['sub'])})
 except (JWTError,KeyError,ValueError): u=None
 if not u: raise HTTPException(401,'Invalid token')
 return u
async def admin_user(u=Depends(current_user)):
 if u.get('role')!='admin': raise HTTPException(403,'Admin access required')
 return u
