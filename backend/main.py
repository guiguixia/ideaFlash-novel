from __future__ import annotations
import asyncio,json,os,re,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from queue import Empty,Queue
from dotenv import load_dotenv
from fastapi import BackgroundTasks,Depends,FastAPI,File,Form,HTTPException,Response,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import httpx
import models
from emotions import FIXED_EMOTION_META,FIXED_EMOTION_SLOTS,configured_emotion_states,configured_mood_ids,valid_configured_mood
from auth import CurrentUser,get_current_user
from database import Base,SessionLocal,engine,get_db,reset_legacy_schema,run_schema_migrations
from schemas import *
from services import _narration_completion,build_experience_snapshot,build_work_rag_index,compact_role_chat_memory,experience_role_cards,narrate,narrate_stream,role_chat_reply_stream,snapshot,split_source_document,work_rag_index_progress
from trace import TraceMiddleware,trace_id
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
ROLE_ASSET_DIR=Path(os.getenv("NOVEL_DATA_DIR") or Path(__file__).resolve().parent / "data") / "role-cards";ROLE_ASSET_DIR.mkdir(parents=True,exist_ok=True)
DEFAULT_COMMUNITY_QR_IMAGE_URL="https://ideaflash-releases.oss-cn-shanghai.aliyuncs.com/story/image/public/ideaFlash-%E5%89%A7%E6%9C%AC%E5%88%B7%E8%AE%A8%E8%AE%BA%E7%BE%A4.png"
# 导入资料的副本构建会连续调用很多次模型；它与用户正在进行的体验必须隔离，
# 否则多个构建任务会占满线程，使新开场或对话只能无期限排队。
LLM_BUILD_WORKERS=ThreadPoolExecutor(max_workers=1,thread_name_prefix="story-build-llm")
LLM_INTERACTIVE_WORKERS=ThreadPoolExecutor(max_workers=2,thread_name_prefix="story-interactive-llm")
reset_legacy_schema();Base.metadata.create_all(engine);run_schema_migrations()
def recover_interrupted_experience_builds():
 db=SessionLocal()
 try:
  runs=db.query(models.ExperienceBuildRun).filter(models.ExperienceBuildRun.status.in_(("queued","running"))).all()
  for run in runs:
   run.status,run.stage,run.error="failed","failed","构建被服务重启中断，请重新生成体验副本"
   script=db.get(models.ExperienceScript,run.script_id)
   if script and script.status in {"queued","building"}:script.status="failed"
  if runs:db.commit()
 finally:db.close()
recover_interrupted_experience_builds()
app=FastAPI(title="Story Experience API",version="1.0.0");app.add_middleware(TraceMiddleware);app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:5179","http://localhost:5179","null"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"]);app.mount("/uploads/role-cards",StaticFiles(directory=str(ROLE_ASSET_DIR)),name="role-card-assets")
def out(data=None,msg="ok"):return {"code":0,"data":data,"msg":msg,"traceId":trace_id()}
def lst(data,msg="ok"):return {"code":0,"list":data,"msg":msg,"traceId":trace_id()}
def wd(w,counts=None):
 c=counts or {};return {"id":w.id,"title":w.title,"workType":w.work_type,"summary":w.summary,"settings":w.settings or {},"status":w.status,"privacy":"owner_only","sourceSegmentCount":c.get("segments",0),"scriptCount":c.get("scripts",0),"ragIndex":{"status":w.rag_status,"processed":w.rag_processed,"total":w.rag_total,"error":w.rag_error},"createdAt":w.created_at.isoformat() if w.created_at else None}
def sd(s,n=0):return {"id":s.id,"title":s.title,"sourceStart":s.source_start,"sourceEnd":s.source_end,"playerIdentity":s.player_identity,"characters":[str(row.get("name")) for row in (s.snapshot or {}).get("extractedCharacters",[]) if isinstance(row,dict) and row.get("name")],"perspective":s.perspective,"version":s.version,"status":s.status,"sessionCount":n}
def sess(x,full=False):
 d={"id":x.id,"scriptId":x.script_id,"title":x.title,"status":x.status,"turn":x.turn,"state":x.state or {},"createdAt":x.created_at.isoformat() if x.created_at else None}
 if full:d["history"]=x.history or []
 return d
EMOTION_SLOTS=FIXED_EMOTION_SLOTS
DEFAULT_EMOTION_DESCRIPTIONS={slot:meta[1] for slot,meta in FIXED_EMOTION_META.items()}
MOOD_TAG_RE=re.compile(r"^\s*\[mood:([a-z][a-z0-9_-]{0,63})\]\s*$")
MOOD_TAG_PREFIX_RE=re.compile(r"^\s*\[mood:([a-z][a-z0-9_-]{0,63})\]\s*")
CHOICES_START="[choices]"
CHOICES_BLOCK_RE=re.compile(r"\[choices\]\s*(.*?)\s*\[/choices\]\s*$",re.S)
def parse_story_suggestions(block:str):
 choices=[]
 for line in block.splitlines():
  value=re.sub(r"^\s*[-*]\s*", "", line).strip()
  if value and value not in choices:choices.append(value[:80])
 return choices[:4]
def custom_emotions(card):return [item for item in (card.custom_emotions or []) if isinstance(item,dict) and item.get("id")]
def emotion_descriptions(card):
 saved=card.emotion_descriptions or {}
 return {slot:str(saved.get(slot) or (card.appearance if slot=="default" and card.appearance else DEFAULT_EMOTION_DESCRIPTIONS[slot])) for slot in EMOTION_SLOTS}
def mood_ids(card):return configured_mood_ids(card)
def valid_mood(card,value):return valid_configured_mood(card,value)
def normalize_role_chat_history(history):
 cleaned=[]
 for row in history or []:
  item=dict(row);match=MOOD_TAG_PREFIX_RE.match(str(item.get("content") or "")) if item.get("role")=="assistant" else None
  if match:
   item["content"]=str(item.get("content") or "")[match.end():]
   if not item.get("mood") or item.get("mood")=="default":item["mood"]=match.group(1)
  cleaned.append(item)
 return cleaned
def role_card(row):
 def image_url(path):
  asset=ROLE_ASSET_DIR/path
  version=asset.stat().st_mtime_ns if asset.exists() else 0
  return f"/uploads/role-cards/{path}?v={version}"
 images={slot:image_url(path) for slot,path in (row.emotion_images or {}).items() if slot in EMOTION_SLOTS and path}
 if row.image_path:images["default"]=image_url(row.image_path)
 custom=[{"id":str(item["id"]),"name":str(item.get("name") or "自定义状态"),"description":str(item.get("description") or ""),"imageUrl":image_url(item["image_path"]) if item.get("image_path") else ""} for item in custom_emotions(row)]
 return {"id":row.id,"scriptId":row.script_id,"name":row.name,"identity":row.identity,"personality":row.personality,"appearance":row.appearance,"background":row.background,"currentState":row.current_state,"attributes":row.attributes or {},"sourceSegmentOrders":row.source_segment_orders or [],"dialogueExamples":row.dialogue_examples or [],"imageUrl":images.get("default",""),"emotionImages":images,"emotionDescriptions":emotion_descriptions(row),"customEmotions":custom,"availableEmotions":configured_emotion_states(row),"roleMode":"replacement"}
def role_chat(chat,full=False):
 d={"id":chat.id,"title":chat.title,"turn":chat.turn,"createdAt":chat.created_at.isoformat() if chat.created_at else None,"updatedAt":chat.updated_at.isoformat() if chat.updated_at else None}
 if full:d["history"]=normalize_role_chat_history(chat.history)
 return d
def seed_role_cards(db,work_id,script):
 if db.query(models.ExperienceRoleCard).filter_by(script_id=script.id).count():return
 for source in experience_role_cards(script.snapshot or {}):
  db.add(models.ExperienceRoleCard(work_id=work_id,script_id=script.id,name=source["name"],identity=source.get("identity","") or "",appearance=source.get("appearance","") or "",current_state=source.get("currentState","") or "",attributes=source.get("attributes") or {},source_segment_orders=source.get("sourceSegmentOrders") or [],dialogue_examples=source.get("dialogueExamples") or []))
 db.commit()
def role_card_for_script(db,work,script_id,card_id):
 script=db.query(models.ExperienceScript).filter_by(id=script_id,work_id=work.id).first()
 if not script:raise HTTPException(404,"体验副本不存在")
 card=db.query(models.ExperienceRoleCard).filter_by(id=card_id,script_id=script.id,work_id=work.id).first()
 if not card:raise HTTPException(404,"角色卡不存在")
 return script,card
def owned(db,id,u):
 w=db.query(models.Work).filter_by(id=id,platform_user_id=u.platform_user_id).first()
 if not w:raise HTTPException(404,"作品不存在")
 return w
async def run_in_interactive_llm_worker(job,*args):
 loop=asyncio.get_running_loop()
 return await loop.run_in_executor(LLM_INTERACTIVE_WORKERS,lambda:asyncio.run(job(*args)))
async def run_in_build_llm_worker(job,*args):
 loop=asyncio.get_running_loop()
 return await loop.run_in_executor(LLM_BUILD_WORKERS,lambda:asyncio.run(job(*args)))
def enqueue_interactive_llm_worker(job,*args):
 return LLM_INTERACTIVE_WORKERS.submit(lambda:asyncio.run(job(*args)))
def enqueue_build_llm_worker(job,*args):
 return LLM_BUILD_WORKERS.submit(lambda:asyncio.run(job(*args)))
async def run_experience_build(run_id:str):
 db=SessionLocal()
 try:
  run=db.get(models.ExperienceBuildRun,run_id)
  if not run:return
  script=db.get(models.ExperienceScript,run.script_id);work=db.get(models.Work,run.work_id)
  if not script or not work:return
  run.status,run.stage,script.status="running","chapter_extraction","building";db.commit()
  parts=db.query(models.SourceSegment).filter(models.SourceSegment.work_id==work.id,models.SourceSegment.sequence>=script.source_start,models.SourceSegment.sequence<=script.source_end).order_by(models.SourceSegment.sequence).all()
  async def progress(done,stage):run.processed,run.stage=done,stage;db.commit()
  result=await build_experience_snapshot(db,work,parts,progress);script.snapshot=result;script.status="ready";run.status,run.stage,run.processed="succeeded","ready",len(parts);db.commit();seed_role_cards(db,work.id,script)
 except Exception as exc:
  if 'run' in locals() and run:run.status,run.stage,run.error="failed","failed",str(exc)
  if 'script' in locals() and script:script.status="failed"
  db.commit()
 finally:db.close()

async def run_experience_build_in_worker(run_id:str):
 """让耗时的大模型构建脱离 API 事件循环，避免任务卡住作品列表与其他操作。"""
 await run_in_build_llm_worker(run_experience_build,run_id)
async def run_work_rag_build(work_id:str):
 db=SessionLocal()
 try:
  work=db.get(models.Work,work_id)
  if work:await build_work_rag_index(db,work)
 finally:db.close()

async def generate_session_opening(session_id:str):
 db=SessionLocal()
 try:
  x=db.get(models.ExperienceSession,session_id)
  if not x:raise RuntimeError("体验记录不存在")
  s=db.get(models.ExperienceScript,x.script_id)
  if not s:raise RuntimeError("体验副本不存在")
  player=str((x.state or {}).get("playerIdentity") or s.player_identity or "一名进入故事的旅人")
  return await narrate(db,s,[],player_identity=player)
 finally:db.close()

async def generate_session_turn(session_id:str,events:Queue):
 db=SessionLocal()
 try:
  x=db.get(models.ExperienceSession,session_id)
  if not x:raise RuntimeError("体验记录不存在")
  s=db.get(models.ExperienceScript,x.script_id)
  if not s:raise RuntimeError("体验副本不存在")
  history=list(x.history or [])
  if len(history)<2 or history[-1].get("status")!="generating":raise RuntimeError("没有待生成的剧情")
  message=str(history[-2].get("content") or "").strip()
  player=str((x.state or {}).get("playerIdentity") or s.player_identity or "")
  card=db.query(models.ExperienceRoleCard).filter_by(script_id=s.id,name=player).first()
  custom=configured_emotion_states(card) if card else []
  chunks=[];model="";mood="default";prefix="";waiting_for_mood=True;tail="";choices_raw="";reading_choices=False
  def emit_story_content(content:str):
   nonlocal tail,choices_raw,reading_choices
   if not content:return
   if reading_choices:
    choices_raw+=content;return
   tail+=content;marker=tail.find(CHOICES_START)
   if marker>=0:
    visible=tail[:marker];choices_raw=tail[marker:];tail="";reading_choices=True
    if visible:chunks.append(visible);events.put(("chunk",visible))
    return
   safe=max(0,len(tail)-len(CHOICES_START)+1)
   if safe:
    visible=tail[:safe];tail=tail[safe:];chunks.append(visible);events.put(("chunk",visible))
  async for chunk,item_model in narrate_stream(db,s,history[:-1],message,player,custom):
   model=item_model
   if waiting_for_mood:
    prefix+=chunk
    prefix_match=MOOD_TAG_PREFIX_RE.match(prefix)
    if prefix_match:
     mood=valid_mood(card,prefix_match.group(1)) if card else "default";events.put(("mood",mood));content=prefix[prefix_match.end():];waiting_for_mood=False
     emit_story_content(content)
     prefix="";continue
    if "\n" not in prefix and len(prefix)<80:continue
    first_line,separator,content=prefix.partition("\n");matched=MOOD_TAG_RE.match(first_line);waiting_for_mood=False
    if matched:
     mood=valid_mood(card,matched.group(1)) if card else "default";events.put(("mood",mood))
     emit_story_content(content)
    else:emit_story_content(prefix)
    prefix=""
   else:emit_story_content(chunk)
  if waiting_for_mood and prefix:
   matched=MOOD_TAG_RE.match(prefix)
   if matched:mood=valid_mood(card,matched.group(1)) if card else "default";events.put(("mood",mood))
   else:emit_story_content(prefix)
  if reading_choices:
   match=CHOICES_BLOCK_RE.search(choices_raw)
   if match:suggestions=parse_story_suggestions(match.group(1))
   else:chunks.append(choices_raw);events.put(("chunk",choices_raw));suggestions=[]
  else:
   suggestions=[]
  if tail:chunks.append(tail);events.put(("chunk",tail))
  reply="".join(chunks).strip()
  if not reply:raise RuntimeError("大模型未返回可展示内容")
  x.history=history[:-1]+[{"role":"assistant","content":reply,"model":model,"mood":mood,"suggestions":suggestions}];x.turn+=1;x.updated_at=datetime.now(timezone.utc);db.commit();events.put(("done",sess(x,True)))
 except Exception as exc:
  db.rollback()
  x=db.get(models.ExperienceSession,session_id)
  if x:
   history=list(x.history or [])
   if history and history[-1].get("status")=="generating":x.history=history[:-1]+[{"role":"assistant","content":"","status":"failed","error":str(exc)}];x.updated_at=datetime.now(timezone.utc);db.commit()
  events.put(("error",str(exc)))
 finally:db.close()

async def generate_role_chat_turn(chat_id:str,events:Queue):
 db=SessionLocal()
 try:
  chat=db.get(models.RoleChatSession,chat_id)
  if not chat:raise RuntimeError("私聊不存在")
  card=db.get(models.ExperienceRoleCard,chat.role_card_id)
  if not card:raise RuntimeError("角色卡不存在")
  script=db.get(models.ExperienceScript,card.script_id)
  if not script:raise RuntimeError("体验副本不存在")
  history=normalize_role_chat_history(chat.history)
  if len(history)<2 or history[-1].get("status")!="generating":raise RuntimeError("没有待生成的私聊消息")
  message=str(history[-2].get("content") or "").strip();chunks=[];model="";mood="default";prefix="";waiting_for_mood=True
  async for chunk,item_model in role_chat_reply_stream(db,script,card,history[:-1],message,chat.memory_summary or "",chat.summary_cursor or 0):
   model=item_model
   if waiting_for_mood:
    prefix+=chunk
    prefix_match=MOOD_TAG_PREFIX_RE.match(prefix)
    if prefix_match:
     mood=valid_mood(card,prefix_match.group(1));events.put(("mood",mood));content=prefix[prefix_match.end():];waiting_for_mood=False
     if content:chunks.append(content);events.put(("chunk",content))
     prefix="";continue
    if "\n" not in prefix and len(prefix)<80:continue
    first_line,separator,content=prefix.partition("\n");matched=MOOD_TAG_RE.match(first_line);waiting_for_mood=False
    if matched:
     mood=valid_mood(card,matched.group(1));events.put(("mood",mood))
     if content:chunks.append(content);events.put(("chunk",content))
    else:chunks.append(prefix);events.put(("chunk",prefix))
    prefix=""
   else:chunks.append(chunk);events.put(("chunk",chunk))
  if waiting_for_mood and prefix:
   matched=MOOD_TAG_RE.match(prefix)
   if matched:mood=valid_mood(card,matched.group(1));events.put(("mood",mood))
   else:chunks.append(prefix);events.put(("chunk",prefix))
  reply="".join(chunks).strip()
  if not reply:raise RuntimeError("大模型未返回可展示内容")
  chat.history=history[:-1]+[{"role":"assistant","content":reply,"model":model,"mood":mood}];chat.turn+=1;await compact_role_chat_memory(db,chat,card);chat.updated_at=datetime.now(timezone.utc);db.commit();db.refresh(chat);events.put(("done",role_chat(chat,True)))
 except Exception as exc:
  db.rollback();chat=db.get(models.RoleChatSession,chat_id)
  if chat:
   history=list(chat.history or [])
   if history and history[-1].get("status")=="generating":chat.history=history[:-1]+[{"role":"assistant","content":"","status":"failed","error":str(exc)}];chat.updated_at=datetime.now(timezone.utc);db.commit()
  events.put(("error",str(exc)))
 finally:db.close()

@app.get("/health")
def health():return {"status":"ok"}
@app.get("/api/settings/llm")
def llm_get(response:Response,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 response.headers["Cache-Control"]="no-store"
 c=db.get(models.LLMConfig,1);return out({"baseUrl":c.base_url if c else "https://api.deepseek.com","model":c.model if c else "deepseek-v4-pro","apiKey":c.api_key if c else "","apiKeyConfigured":bool(c and c.api_key),"embeddingBaseUrl":c.embedding_base_url if c else "","embeddingModel":c.embedding_model if c else "","embeddingApiKey":c.embedding_api_key if c else "","embeddingApiKeyConfigured":bool(c and c.embedding_api_key)})
@app.patch("/api/settings/llm")
def llm_set(body:LLMConfigUpdateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 c=db.get(models.LLMConfig,1) or models.LLMConfig(id=1);db.add(c);c.base_url=body.base_url.strip().rstrip("/");c.model=body.model.strip();c.api_key=body.api_key.strip();c.embedding_base_url=body.embedding_base_url.strip().rstrip("/");c.embedding_model=body.embedding_model.strip();c.embedding_api_key=body.embedding_api_key.strip();db.commit();return out({"baseUrl":c.base_url,"model":c.model,"apiKeyConfigured":bool(c.api_key),"embeddingBaseUrl":c.embedding_base_url,"embeddingModel":c.embedding_model,"embeddingApiKeyConfigured":bool(c.embedding_api_key)},"大模型配置已保存")
@app.post("/api/settings/llm/test")
async def llm_test(body:LLMConfigUpdateRequest,current_user:CurrentUser=Depends(get_current_user)):
 base_url=body.base_url.strip().rstrip("/")
 if base_url.endswith("/chat/completions"):raise HTTPException(400,"大模型 Base URL 配置错误：请填写服务根地址，例如 https://api.deepseek.com 或 https://api.deepseek.com/v1，而不是 /chat/completions")
 if not body.api_key.strip():raise HTTPException(400,"请输入 API Key 后再测试连接")
 probe=models.LLMConfig(base_url=base_url,model=body.model.strip(),api_key=body.api_key.strip())
 try:
  reply,model=await _narration_completion(probe,"请仅回复：连接成功",0,"llm_connection_test")
 except Exception as exc:
  raise HTTPException(400,f"连接失败：{exc}") from exc
 return out({"model":model,"replyPreview":reply[:200]},"连接成功")
@app.get("/api/community-qr")
def community_qr_get():
 url=os.getenv("NOVEL_COMMUNITY_QR_IMAGE_URL",DEFAULT_COMMUNITY_QR_IMAGE_URL).strip()
 if url and not url.startswith(("https://","http://")):raise HTTPException(500,"NOVEL_COMMUNITY_QR_IMAGE_URL 必须是公开的 http(s) 图片地址")
 return out({"imageUrl":"/api/community-qr/image"})
@app.get("/api/community-qr/image")
def community_qr_image():
 url=os.getenv("NOVEL_COMMUNITY_QR_IMAGE_URL",DEFAULT_COMMUNITY_QR_IMAGE_URL).strip()
 if not url.startswith(("https://","http://")):raise HTTPException(500,"NOVEL_COMMUNITY_QR_IMAGE_URL 必须是公开的 http(s) 图片地址")
 separator="&" if "?" in url else "?"
 try:
  remote=httpx.get(f"{url}{separator}_={time.time_ns()}",headers={"Cache-Control":"no-cache","Pragma":"no-cache"},follow_redirects=True,timeout=15,trust_env=False)
  remote.raise_for_status()
 except httpx.HTTPError as exc:
  raise HTTPException(502,"群二维码暂时无法获取，请稍后重试") from exc
 content_type=remote.headers.get("content-type","image/png").split(";",1)[0]
 if not content_type.startswith("image/"):raise HTTPException(502,"群二维码源返回的不是图片")
 return Response(content=remote.content,media_type=content_type,headers={"Cache-Control":"no-store, max-age=0","Pragma":"no-cache"})
@app.get("/api/works")
def works(current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 rows=db.query(models.Work).filter_by(platform_user_id=current_user.platform_user_id).order_by(models.Work.updated_at.desc()).all();return lst([wd(x,{"segments":db.query(models.SourceSegment).filter_by(work_id=x.id).count(),"scripts":db.query(models.ExperienceScript).filter_by(work_id=x.id).count()}) for x in rows])
@app.post("/api/works")
def work_create(body:WorkCreateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=models.Work(platform_user_id=current_user.platform_user_id,title=body.title.strip(),work_type="original_story",summary=body.summary.strip(),settings={"genre":body.genre,"world":body.world,"playerIdentity":body.player_identity,"openingScene":body.opening_scene,"tone":body.tone});db.add(w);db.commit();db.refresh(w);return out(wd(w),"原创故事已创建")
@app.post("/api/works/import")
async def work_import(work_type:str=Form(...),title:str=Form(""),file:UploadFile=File(...),current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 if work_type not in {"imported_novel","imported_screenwork"}:raise HTTPException(400,"不支持的导入类型")
 raw=await file.read()
 if not raw or len(raw)>20*1024*1024:raise HTTPException(400,"文件不能为空且不得超过 20MB")
 rows=split_source_document(file.filename or "import.txt",raw)
 if not rows:raise HTTPException(400,"未识别到可用文本")
 w=models.Work(platform_user_id=current_user.platform_user_id,title=(title.strip() or (file.filename or "未命名导入").rsplit(".",1)[0])[:160],work_type=work_type,summary="私有导入资料，仅自己可体验",settings={"filename":file.filename or ""});db.add(w);db.flush();db.add_all([models.SourceSegment(work_id=w.id,sequence=i,title=a,content=b) for i,(a,b) in enumerate(rows,1)]);db.commit();return out(wd(w,{"segments":len(rows)}),f"已导入 {len(rows)} 个资料片段")
@app.get("/api/works/{work_id}")
def work_get(work_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    w=owned(db,work_id,current_user);segments=db.query(models.SourceSegment).filter_by(work_id=w.id).count();scripts=db.query(models.ExperienceScript).filter_by(work_id=w.id).order_by(models.ExperienceScript.created_at.desc()).all();sessions=db.query(models.ExperienceSession).filter_by(work_id=w.id).order_by(models.ExperienceSession.updated_at.desc()).all();runs={x.script_id:x for x in db.query(models.ExperienceBuildRun).filter_by(work_id=w.id).all()};return out({**wd(w,{"segments":segments,"scripts":len(scripts)}),"scripts":[{**sd(x,sum(y.script_id==x.id for y in sessions)),"build":({"status":runs[x.id].status,"stage":runs[x.id].stage,"processed":runs[x.id].processed,"total":runs[x.id].total,"error":runs[x.id].error} if x.id in runs else None)} for x in scripts],"sessions":[sess(x) for x in sessions]})
@app.delete("/api/works/{work_id}")
def work_delete(work_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);db.delete(w);db.commit();return out({"id":work_id},"作品及其体验记录已删除")
@app.get("/api/works/{work_id}/segments")
def work_segments(work_id:str,page:int=1,page_size:int=20,start_sequence:int|None=None,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    w=owned(db,work_id,current_user);page=max(1,page);page_size=min(50,max(10,page_size));query=db.query(models.SourceSegment).filter_by(work_id=w.id)
    if start_sequence is not None:
        rows=query.filter(models.SourceSegment.sequence>=max(1,start_sequence)).order_by(models.SourceSegment.sequence).limit(page_size).all();return out({"items":[{"id":x.id,"sequence":x.sequence,"title":x.title,"content":x.content} for x in rows],"page":1,"pageSize":page_size,"total":len(rows),"totalPages":1})
    total=query.count();rows=query.order_by(models.SourceSegment.sequence).offset((page-1)*page_size).limit(page_size).all();return out({"items":[{"id":x.id,"sequence":x.sequence,"title":x.title,"content":x.content} for x in rows],"page":page,"pageSize":page_size,"total":total,"totalPages":max(1,(total+page_size-1)//page_size)})
@app.post("/api/works/{work_id}/rag-index")
def rag_index_build(work_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user)
 if w.work_type=="original_story":raise HTTPException(400,"原创故事暂不支持原文知识库")
 if w.rag_status=="building":return out(wd(w),"角色知识库正在构建")
 w.rag_status,w.rag_error="queued","";db.commit();enqueue_build_llm_worker(run_work_rag_build,w.id);return out(wd(w),"已开始构建角色知识库")
@app.get("/api/works/{work_id}/rag-index/preview")
def rag_index_preview(work_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user)
 if w.work_type=="original_story":raise HTTPException(400,"原创故事暂不支持原文知识库")
 return out({**work_rag_index_progress(db,w),"status":w.rag_status},"知识库构建预览")
@app.patch("/api/works/{work_id}")
def work_update(work_id:str,body:WorkUpdateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user)
 if w.work_type!="original_story":raise HTTPException(409,"导入资料不能改写原作；请在副本中配置范围和视角")
 w.title=body.title.strip();w.summary=body.summary.strip();w.settings={"genre":body.genre,"world":body.world,"playerIdentity":body.player_identity,"openingScene":body.opening_scene,"tone":body.tone};db.commit();return out(wd(w),"故事设定已保存")
@app.post("/api/works/{work_id}/scripts")
async def script_create(work_id:str,body:ExperienceScriptCreateRequest,background_tasks:BackgroundTasks,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);parts=[]
 if w.work_type!="original_story":
  if not body.start_sequence or not body.end_sequence or body.start_sequence>body.end_sequence or body.end_sequence-body.start_sequence>=30:raise HTTPException(400,"请选择连续且不超过 30 个片段的范围")
  parts=db.query(models.SourceSegment).filter(models.SourceSegment.work_id==w.id,models.SourceSegment.sequence>=body.start_sequence,models.SourceSegment.sequence<=body.end_sequence).order_by(models.SourceSegment.sequence).all()
  if len(parts)!=body.end_sequence-body.start_sequence+1:raise HTTPException(400,"范围中存在缺失片段")
 count=db.query(models.ExperienceScript).filter_by(work_id=w.id).count();title=body.title.strip() or (f"第{body.start_sequence}—{body.end_sequence}段体验" if parts else "开局体验");player=body.player_identity.strip() or str((w.settings or {}).get("playerIdentity") or "");s=models.ExperienceScript(work_id=w.id,title=title,source_start=body.start_sequence,source_end=body.end_sequence,player_identity=player,perspective=body.perspective,version=count+1,status="queued" if parts else "ready",snapshot=snapshot(w,parts,player) if not parts else {});db.add(s);db.flush();run=None
 if parts:run=models.ExperienceBuildRun(work_id=w.id,script_id=s.id,status="queued",stage="queued",total=len(parts));db.add(run)
 db.commit();db.refresh(s)
 if run:background_tasks.add_task(run_experience_build_in_worker,run.id)
 return out({**sd(s),"build":{"status":run.status,"stage":run.stage,"processed":0,"total":run.total,"error":""} if run else None},"体验副本正在构建" if run else "体验副本已生成")
@app.get("/api/works/{work_id}/scripts/{script_id}/role-cards")
def script_role_cards(work_id:str,script_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);s=db.query(models.ExperienceScript).filter_by(id=script_id,work_id=w.id).first()
 if not s:raise HTTPException(404,"体验副本不存在")
 if s.status!="ready":raise HTTPException(409,"体验副本仍在构建中")
 seed_role_cards(db,w.id,s);return out([role_card(row) for row in db.query(models.ExperienceRoleCard).filter_by(work_id=w.id,script_id=s.id).order_by(models.ExperienceRoleCard.created_at).all()],"副本角色卡")
@app.get("/api/works/{work_id}/role-contexts")
def role_contexts(work_id:str,name:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);role_name=name.strip()
 if not role_name:raise HTTPException(400,"缺少角色名称")
 scripts=db.query(models.ExperienceScript).filter_by(work_id=w.id,status="ready").order_by(models.ExperienceScript.created_at.desc()).all()
 for script in scripts:seed_role_cards(db,w.id,script)
 cards=db.query(models.ExperienceRoleCard).filter_by(work_id=w.id,name=role_name).all();by_script={card.script_id:card for card in cards}
 return out([{"script":sd(script),"card":role_card(by_script[script.id])} for script in scripts if script.id in by_script],"角色可切换副本")
@app.post("/api/works/{work_id}/scripts/{script_id}/role-cards")
def role_card_create(work_id:str,script_id:str,body:RoleCardUpsertRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);s=db.query(models.ExperienceScript).filter_by(id=script_id,work_id=w.id).first()
 if not s:raise HTTPException(404,"体验副本不存在")
 card=models.ExperienceRoleCard(work_id=w.id,script_id=s.id,name=body.name.strip(),identity=body.identity.strip(),personality=body.personality.strip(),appearance=body.appearance.strip(),background=body.background.strip(),current_state=body.current_state.strip());db.add(card);db.commit();db.refresh(card);return out(role_card(card),"角色卡已创建")
@app.patch("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}")
def role_card_update(work_id:str,script_id:str,card_id:str,body:RoleCardUpsertRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);card.name=body.name.strip();card.identity=body.identity.strip();card.personality=body.personality.strip();card.appearance=body.appearance.strip();card.background=body.background.strip();card.current_state=body.current_state.strip();db.commit();db.refresh(card);return out(role_card(card),"角色卡已保存")
@app.post("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/image")
async def role_card_image(work_id:str,script_id:str,card_id:str,slot:str="default",file:UploadFile=File(...),current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);raw=await file.read()
 if slot not in EMOTION_SLOTS:raise HTTPException(400,"不支持的固定情绪槽位")
 if not raw or len(raw)>5*1024*1024:raise HTTPException(400,"图片不能为空且不得超过 5MB")
 suffix={"image/jpeg":".jpg","image/png":".png","image/webp":".webp","image/gif":".gif"}.get(file.content_type or "")
 if not suffix:raise HTTPException(400,"仅支持 JPG、PNG、WebP 或 GIF 图片")
 path=f"{card.id}{suffix}" if slot=="default" else f"{card.id}-{slot}{suffix}"
 (ROLE_ASSET_DIR/path).write_bytes(raw)
 if slot=="default":card.image_path=path
 else:
  images=dict(card.emotion_images or {});images[slot]=path;card.emotion_images=images
 db.commit();db.refresh(card);return out(role_card(card),"角色形象已上传")
@app.delete("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/image")
def role_card_image_delete(work_id:str,script_id:str,card_id:str,slot:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id)
 if slot not in EMOTION_SLOTS or slot=="default":raise HTTPException(400,"默认形象不可删除")
 images=dict(card.emotion_images or {});images.pop(slot,None);card.emotion_images=images;db.commit();db.refresh(card);return out(role_card(card),"情绪形象已删除")
@app.patch("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/emotion-descriptions/{slot}")
def role_card_emotion_description_update(work_id:str,script_id:str,card_id:str,slot:str,body:RoleCardEmotionDescriptionRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id)
 if slot not in EMOTION_SLOTS:raise HTTPException(400,"不支持的固定情绪槽位")
 descriptions=dict(card.emotion_descriptions or {});descriptions[slot]=body.description.strip();card.emotion_descriptions=descriptions;db.commit();db.refresh(card);return out(role_card(card),"形象状态描述已保存")
@app.post("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/custom-emotions")
def role_card_custom_emotion_create(work_id:str,script_id:str,card_id:str,body:RoleCardCustomEmotionRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);items=[dict(item) for item in custom_emotions(card)]
 if len(items)>=5:raise HTTPException(400,"每个角色最多新增 5 个自定义状态")
 items.append({"id":f"custom_{models.new_id()[:12]}","name":body.name.strip(),"description":body.description.strip(),"image_path":""});card.custom_emotions=items;db.commit();db.refresh(card);return out(role_card(card),"自定义状态已新增")
@app.patch("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/custom-emotions/{emotion_id}")
def role_card_custom_emotion_update(work_id:str,script_id:str,card_id:str,emotion_id:str,body:RoleCardCustomEmotionRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);items=[dict(item) for item in custom_emotions(card)];item=next((item for item in items if item["id"]==emotion_id),None)
 if not item:raise HTTPException(404,"自定义状态不存在")
 item["name"],item["description"]=body.name.strip(),body.description.strip();card.custom_emotions=items;db.commit();db.refresh(card);return out(role_card(card),"自定义状态已保存")
@app.post("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/custom-emotions/{emotion_id}/image")
async def role_card_custom_emotion_image(work_id:str,script_id:str,card_id:str,emotion_id:str,file:UploadFile=File(...),current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);items=[dict(item) for item in custom_emotions(card)];item=next((item for item in items if item["id"]==emotion_id),None)
 if not item:raise HTTPException(404,"自定义状态不存在")
 raw=await file.read()
 if not raw or len(raw)>5*1024*1024:raise HTTPException(400,"图片不能为空且不得超过 5MB")
 suffix={"image/jpeg":".jpg","image/png":".png","image/webp":".webp","image/gif":".gif"}.get(file.content_type or "")
 if not suffix:raise HTTPException(400,"仅支持 JPG、PNG、WebP 或 GIF 图片")
 path=f"{card.id}-{emotion_id}{suffix}";(ROLE_ASSET_DIR/path).write_bytes(raw);item["image_path"]=path;card.custom_emotions=items;db.commit();db.refresh(card);return out(role_card(card),"自定义状态形象已上传")
@app.delete("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/custom-emotions/{emotion_id}")
def role_card_custom_emotion_delete(work_id:str,script_id:str,card_id:str,emotion_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);items=custom_emotions(card);remaining=[item for item in items if item["id"]!=emotion_id]
 if len(remaining)==len(items):raise HTTPException(404,"自定义状态不存在")
 card.custom_emotions=remaining;db.commit();db.refresh(card);return out(role_card(card),"自定义状态已删除")
@app.post("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/chats")
def role_chat_create(work_id:str,script_id:str,card_id:str,body:RoleChatCreateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);chat=models.RoleChatSession(role_card_id=card.id,title=body.title.strip());db.add(chat);db.flush()
 if not chat.title:chat.title=f"会话 #{chat.id[:5].upper()}"
 db.commit();db.refresh(chat);return out(role_chat(chat,True),"私聊已创建")
@app.get("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/chats")
def role_chat_list(work_id:str,script_id:str,card_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);rows=db.query(models.RoleChatSession).filter_by(role_card_id=card.id).order_by(models.RoleChatSession.updated_at.desc(),models.RoleChatSession.created_at.desc()).all();return out([role_chat(row) for row in rows],"私聊会话")
@app.get("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/chats/{chat_id}")
def role_chat_get(work_id:str,script_id:str,card_id:str,chat_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);chat=db.query(models.RoleChatSession).filter_by(id=chat_id,role_card_id=card.id).first()
 if not chat:raise HTTPException(404,"私聊不存在")
 return out(role_chat(chat,True))
@app.patch("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/chats/{chat_id}")
def role_chat_update(work_id:str,script_id:str,card_id:str,chat_id:str,body:RoleChatUpdateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);chat=db.query(models.RoleChatSession).filter_by(id=chat_id,role_card_id=card.id).first()
 if not chat:raise HTTPException(404,"私聊不存在")
 chat.title=body.title.strip();db.commit();db.refresh(chat);return out(role_chat(chat),"会话名称已修改")
@app.delete("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/chats/{chat_id}")
def role_chat_delete(work_id:str,script_id:str,card_id:str,chat_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);_,card=role_card_for_script(db,w,script_id,card_id);chat=db.query(models.RoleChatSession).filter_by(id=chat_id,role_card_id=card.id).first()
 if not chat:raise HTTPException(404,"私聊不存在")
 db.delete(chat);db.commit();return out({"id":chat_id},"私聊已删除")
@app.post("/api/works/{work_id}/scripts/{script_id}/role-cards/{card_id}/chats/{chat_id}/turn")
async def role_chat_turn(work_id:str,script_id:str,card_id:str,chat_id:str,body:RoleChatTurnRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);script,card=role_card_for_script(db,w,script_id,card_id);chat=db.query(models.RoleChatSession).filter_by(id=chat_id,role_card_id=card.id).first()
 if not chat:raise HTTPException(404,"私聊不存在")
 history=list(chat.history or [])
 if history and history[-1].get("role")=="assistant" and history[-1].get("status")=="generating":raise HTTPException(409,"上一条私聊仍在生成中")
 history.extend([{"role":"user","content":body.message.strip()},{"role":"assistant","content":"","status":"generating"}]);chat.history=history;chat.updated_at=datetime.now(timezone.utc);db.commit();events:Queue=Queue();enqueue_interactive_llm_worker(generate_role_chat_turn,chat.id,events)
 def sse(event:str,data:dict):return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n"
 async def stream():
  while True:
   try:event,data=events.get_nowait()
   except Empty:
    await asyncio.sleep(.08);continue
   if event=="chunk":yield sse("chunk",{"content":data})
   elif event=="mood":yield sse("mood",{"mood":data})
   elif event=="done":yield sse("done",{"session":data});return
   else:yield sse("error",{"message":data});return
 return StreamingResponse(stream(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
@app.post("/api/works/{work_id}/scripts/{script_id}/sessions")
async def session_create(work_id:str,script_id:str,body:ExperienceSessionCreateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);s=db.query(models.ExperienceScript).filter_by(id=script_id,work_id=w.id).first()
 if not s:raise HTTPException(404,"体验副本不存在")
 if s.status!="ready":raise HTTPException(409,"体验副本仍在构建中")
 characters=[str(row.get("name")) for row in (s.snapshot or {}).get("extractedCharacters",[]) if isinstance(row,dict) and row.get("name")];player=body.player_identity.strip() or s.player_identity
 if characters and player not in characters:raise HTTPException(400,"请从副本可用角色中选择玩家身份")
 if not player and w.work_type!="original_story":raise HTTPException(400,"该副本未识别到可选择角色，请重新生成副本")
 player=player or "一名进入故事的旅人"
 x=models.ExperienceSession(work_id=w.id,script_id=s.id,title=body.title.strip() or s.title,state={"scriptVersion":s.version,"playerIdentity":player},history=[]);db.add(x);db.commit();db.refresh(x);opening,model=await run_in_interactive_llm_worker(generate_session_opening,x.id);x.history=[{"role":"assistant","content":opening,"model":model}];db.commit();db.refresh(x);return out(sess(x,True),"体验已开始")
@app.get("/api/works/{work_id}/sessions/{session_id}")
def session_get(work_id:str,session_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);x=db.query(models.ExperienceSession).filter_by(id=session_id,work_id=w.id).first()
 if not x:raise HTTPException(404,"体验记录不存在")
 return out(sess(x,True))
@app.patch("/api/works/{work_id}/sessions/{session_id}")
def session_update(work_id:str,session_id:str,body:ExperienceSessionUpdateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);x=db.query(models.ExperienceSession).filter_by(id=session_id,work_id=w.id).first()
 if not x:raise HTTPException(404,"体验记录不存在")
 title=body.title.strip()
 if not title:raise HTTPException(400,"体验名称不能为空")
 x.title=title;db.commit();db.refresh(x)
 return out(sess(x,True),"体验名称已更新")
@app.post("/api/works/{work_id}/sessions/{session_id}/reset")
async def session_reset(work_id:str,session_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);x=db.query(models.ExperienceSession).filter_by(id=session_id,work_id=w.id,status="active").first()
 if not x:raise HTTPException(404,"进行中的体验不存在")
 s=db.query(models.ExperienceScript).filter_by(id=x.script_id,work_id=w.id).first()
 if not s:raise HTTPException(404,"体验副本不存在")
 player=str((x.state or {}).get("playerIdentity") or s.player_identity or "一名进入故事的旅人")
 opening,model=await run_in_interactive_llm_worker(generate_session_opening,x.id)
 x.history=[{"role":"assistant","content":opening,"model":model}];x.turn=0;x.updated_at=datetime.now(timezone.utc);db.commit();db.refresh(x)
 return out(sess(x,True),"体验已重置")
@app.post("/api/works/{work_id}/sessions/{session_id}/turn")
async def turn(work_id:str,session_id:str,body:ExperienceTurnRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);x=db.query(models.ExperienceSession).filter_by(id=session_id,work_id=w.id,status="active").first()
 if not x:raise HTTPException(404,"进行中的体验不存在")
 message=body.message.strip();h=list(x.history or [])
 if h and h[-1].get("role")=="assistant" and h[-1].get("status")=="generating":raise HTTPException(409,"上一段剧情仍在生成中")
 h.extend([{"role":"user","content":message},{"role":"assistant","content":"","status":"generating"}]);x.history=h;x.updated_at=datetime.now(timezone.utc);db.commit()
 def sse(event:str,data:dict):return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n"
 events:Queue=Queue();enqueue_interactive_llm_worker(generate_session_turn,x.id,events)
 async def stream():
  while True:
   try:event,data=events.get_nowait()
   except Empty:
    await asyncio.sleep(.08)
    continue
   if event=="chunk":yield sse("chunk",{"content":data})
   elif event=="mood":yield sse("mood",{"mood":data})
   elif event=="done":yield sse("done",{"reply":"","session":data,"traceId":trace_id()});return
   else:yield sse("error",{"message":str(data),"traceId":trace_id()});return
 return StreamingResponse(stream(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
