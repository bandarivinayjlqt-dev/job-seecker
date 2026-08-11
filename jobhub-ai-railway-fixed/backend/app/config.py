from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
 mongodb_url:str='mongodb://localhost:27017'; database_name:str='jobhub_ai'; jwt_secret:str='change-me'; jwt_expire_minutes:int=1440; openai_api_key:str=''; openai_model:str='gpt-5-mini'; openai_embedding_model:str='text-embedding-3-small'; frontend_url:str='http://localhost:5173'; admin_email:str='admin@jobhub.local'; admin_password:str='Admin@12345'; scrape_interval_hours:int=6
 model_config=SettingsConfigDict(env_file='.env',extra='ignore')
settings=Settings()
