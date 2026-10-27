from typing import Literal
from pydantic import BaseModel,Field
class LoginRequest(BaseModel):username:str;password:str
class LLMConfigUpdateRequest(BaseModel):base_url:str=Field(min_length=1,max_length=500);model:str=Field(min_length=1,max_length=160);api_key:str=Field(default="",max_length=10000)
class WorkCreateRequest(BaseModel):title:str=Field(min_length=1,max_length=160);summary:str="";genre:str="";world:str="";player_identity:str="";opening_scene:str="";tone:str=""
class WorkUpdateRequest(WorkCreateRequest):pass
class ExperienceScriptCreateRequest(BaseModel):title:str="";start_sequence:int=Field(default=0,ge=0);end_sequence:int=Field(default=0,ge=0);player_identity:str="";perspective:Literal["first","third"]="first"
class ExperienceSessionCreateRequest(BaseModel):title:str="";player_identity:str=""
class ExperienceSessionUpdateRequest(BaseModel):title:str=Field(min_length=1,max_length=160)
class ExperienceTurnRequest(BaseModel):message:str=Field(min_length=1,max_length=4000)
