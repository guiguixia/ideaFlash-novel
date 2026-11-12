from typing import Literal
from pydantic import BaseModel,Field
class LLMConfigUpdateRequest(BaseModel):base_url:str=Field(min_length=1,max_length=500);model:str=Field(min_length=1,max_length=160);api_key:str=Field(default="",max_length=10000);embedding_base_url:str=Field(default="",max_length=500);embedding_model:str=Field(default="",max_length=160);embedding_api_key:str=Field(default="",max_length=10000);role_image_base_url:str=Field(default="",max_length=500);role_image_model:str=Field(default="",max_length=160);role_image_api_key:str=Field(default="",max_length=10000);scene_image_base_url:str=Field(default="",max_length=500);scene_image_model:str=Field(default="",max_length=160);scene_image_api_key:str=Field(default="",max_length=10000)
class ConnectionTestRequest(BaseModel):kind:Literal["model","embedding","role_image","scene_image"];base_url:str=Field(min_length=1,max_length=500);model:str=Field(min_length=1,max_length=160);api_key:str=Field(default="",max_length=10000)
class WorkCreateRequest(BaseModel):title:str=Field(min_length=1,max_length=160);summary:str="";genre:str="";world:str="";player_identity:str="";opening_scene:str="";tone:str=""
class WorkUpdateRequest(WorkCreateRequest):pass
class ExperienceScriptCreateRequest(BaseModel):title:str="";start_sequence:int=Field(default=0,ge=0);end_sequence:int=Field(default=0,ge=0);player_identity:str="";perspective:Literal["first","third"]="first"
class ExperienceSessionCreateRequest(BaseModel):title:str="";player_identity:str=""
class ExperienceSessionUpdateRequest(BaseModel):title:str=Field(min_length=1,max_length=160)
class ExperienceTurnRequest(BaseModel):message:str=Field(min_length=1,max_length=4000)
class RoleCardUpsertRequest(BaseModel):name:str=Field(min_length=1,max_length=80);identity:str="";personality:str="";appearance:str="";background:str="";current_state:str=""
class RoleCardCustomEmotionRequest(BaseModel):name:str=Field(min_length=1,max_length=40);description:str=Field(default="",max_length=160)
class RoleCardEmotionDescriptionRequest(BaseModel):description:str=Field(min_length=1,max_length=160)
class RoleChatPlayerProfile(BaseModel):identity:str=Field(default="",max_length=160);gender:str=Field(default="",max_length=40);age:str=Field(default="",max_length=40);description:str=Field(default="",max_length=800)
class UserProfileUpdateRequest(RoleChatPlayerProfile):pass
class RoleChatCreateRequest(BaseModel):title:str=""
class RoleChatUpdateRequest(BaseModel):title:str=""
class RoleChatTurnRequest(BaseModel):message:str=Field(min_length=1,max_length=4000)
