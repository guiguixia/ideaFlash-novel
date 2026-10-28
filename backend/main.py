from __future__ import annotations
import json,os
from datetime import datetime,timezone
from pathlib import Path
from dotenv import load_dotenv
from fastapi import BackgroundTasks,Depends,FastAPI,File,Form,HTTPException,Response,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import models
from auth import CurrentUser,get_current_user
from database import Base,SessionLocal,engine,get_db,reset_legacy_schema,run_schema_migrations
from schemas import *
from services import build_experience_snapshot,experience_role_cards,narrate,narrate_stream,snapshot,split_source_document
from trace import TraceMiddleware,trace_id
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DEFAULT_COMMUNITY_QR_IMAGE_URL="https://ideaflash-releases.oss-cn-shanghai.aliyuncs.com/story/image/public/ideaFlash-%E5%89%A7%E6%9C%AC%E5%88%B7%E8%AE%A8%E8%AE%BA%E7%BE%A4.png"
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
app=FastAPI(title="Story Experience API",version="1.0.0");app.add_middleware(TraceMiddleware);app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:5179","http://localhost:5179","null"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
def out(data=None,msg="ok"):return {"code":0,"data":data,"msg":msg,"traceId":trace_id()}
def lst(data,msg="ok"):return {"code":0,"list":data,"msg":msg,"traceId":trace_id()}
def wd(w,counts=None):
 c=counts or {};return {"id":w.id,"title":w.title,"workType":w.work_type,"summary":w.summary,"settings":w.settings or {},"status":w.status,"privacy":"owner_only","sourceSegmentCount":c.get("segments",0),"scriptCount":c.get("scripts",0),"createdAt":w.created_at.isoformat() if w.created_at else None}
def sd(s,n=0):return {"id":s.id,"title":s.title,"sourceStart":s.source_start,"sourceEnd":s.source_end,"playerIdentity":s.player_identity,"characters":[str(row.get("name")) for row in (s.snapshot or {}).get("extractedCharacters",[]) if isinstance(row,dict) and row.get("name")],"perspective":s.perspective,"version":s.version,"status":s.status,"sessionCount":n}
def sess(x,full=False):
 d={"id":x.id,"scriptId":x.script_id,"title":x.title,"status":x.status,"turn":x.turn,"state":x.state or {},"createdAt":x.created_at.isoformat() if x.created_at else None}
 if full:d["history"]=x.history or []
 return d
def owned(db,id,u):
 w=db.query(models.Work).filter_by(id=id,platform_user_id=u.platform_user_id).first()
 if not w:raise HTTPException(404,"作品不存在")
 return w
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
  result=await build_experience_snapshot(db,work,parts,progress);script.snapshot=result;script.status="ready";run.status,run.stage,run.processed="succeeded","ready",len(parts);db.commit()
 except Exception as exc:
  if 'run' in locals() and run:run.status,run.stage,run.error="failed","failed",str(exc)
  if 'script' in locals() and script:script.status="failed"
  db.commit()
 finally:db.close()
@app.get("/health")
def health():return {"status":"ok"}
@app.get("/api/settings/llm")
def llm_get(response:Response,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 response.headers["Cache-Control"]="no-store"
 c=db.get(models.LLMConfig,1);return out({"baseUrl":c.base_url if c else "https://api.deepseek.com","model":c.model if c else "deepseek-v4-pro","apiKey":c.api_key if c else "","apiKeyConfigured":bool(c and c.api_key)})
@app.patch("/api/settings/llm")
def llm_set(body:LLMConfigUpdateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 c=db.get(models.LLMConfig,1) or models.LLMConfig(id=1);db.add(c);c.base_url=body.base_url.strip().rstrip("/");c.model=body.model.strip();c.api_key=body.api_key.strip();db.commit();return out({"baseUrl":c.base_url,"model":c.model,"apiKeyConfigured":bool(c.api_key)},"大模型配置已保存")
@app.get("/api/community-qr")
def community_qr_get():
 url=os.getenv("NOVEL_COMMUNITY_QR_IMAGE_URL",DEFAULT_COMMUNITY_QR_IMAGE_URL).strip()
 if url and not url.startswith(("https://","http://")):raise HTTPException(500,"NOVEL_COMMUNITY_QR_IMAGE_URL 必须是公开的 http(s) 图片地址")
 return out({"imageUrl":url})
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
@app.get("/api/works/{work_id}/segments")
def work_segments(work_id:str,page:int=1,page_size:int=20,start_sequence:int|None=None,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    w=owned(db,work_id,current_user);page=max(1,page);page_size=min(50,max(10,page_size));query=db.query(models.SourceSegment).filter_by(work_id=w.id)
    if start_sequence is not None:
        rows=query.filter(models.SourceSegment.sequence>=max(1,start_sequence)).order_by(models.SourceSegment.sequence).limit(page_size).all();return out({"items":[{"id":x.id,"sequence":x.sequence,"title":x.title,"content":x.content} for x in rows],"page":1,"pageSize":page_size,"total":len(rows),"totalPages":1})
    total=query.count();rows=query.order_by(models.SourceSegment.sequence).offset((page-1)*page_size).limit(page_size).all();return out({"items":[{"id":x.id,"sequence":x.sequence,"title":x.title,"content":x.content} for x in rows],"page":page,"pageSize":page_size,"total":total,"totalPages":max(1,(total+page_size-1)//page_size)})
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
 if run:background_tasks.add_task(run_experience_build,run.id)
 return out({**sd(s),"build":{"status":run.status,"stage":run.stage,"processed":0,"total":run.total,"error":""} if run else None},"体验副本正在构建" if run else "体验副本已生成")
@app.get("/api/works/{work_id}/scripts/{script_id}/role-cards")
def script_role_cards(work_id:str,script_id:str,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);s=db.query(models.ExperienceScript).filter_by(id=script_id,work_id=w.id).first()
 if not s:raise HTTPException(404,"体验副本不存在")
 if s.status!="ready":raise HTTPException(409,"体验副本仍在构建中")
 return out(experience_role_cards(s.snapshot or {}),"副本角色卡")
@app.post("/api/works/{work_id}/scripts/{script_id}/sessions")
async def session_create(work_id:str,script_id:str,body:ExperienceSessionCreateRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);s=db.query(models.ExperienceScript).filter_by(id=script_id,work_id=w.id).first()
 if not s:raise HTTPException(404,"体验副本不存在")
 if s.status!="ready":raise HTTPException(409,"体验副本仍在构建中")
 characters=[str(row.get("name")) for row in (s.snapshot or {}).get("extractedCharacters",[]) if isinstance(row,dict) and row.get("name")];player=body.player_identity.strip() or s.player_identity
 if characters and player not in characters:raise HTTPException(400,"请从副本可用角色中选择玩家身份")
 if not player and w.work_type!="original_story":raise HTTPException(400,"该副本未识别到可选择角色，请重新生成副本")
 player=player or "一名进入故事的旅人"
 x=models.ExperienceSession(work_id=w.id,script_id=s.id,title=body.title.strip() or s.title,state={"scriptVersion":s.version,"playerIdentity":player},history=[]);db.add(x);db.flush();opening,model=await narrate(db,s,[],player_identity=player);x.history=[{"role":"assistant","content":opening,"model":model}];db.commit();db.refresh(x);return out(sess(x,True),"体验已开始")
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
 opening,model=await narrate(db,s,[],player_identity=player)
 x.history=[{"role":"assistant","content":opening,"model":model}];x.turn=0;x.updated_at=datetime.now(timezone.utc);db.commit();db.refresh(x)
 return out(sess(x,True),"体验已重置")
@app.post("/api/works/{work_id}/sessions/{session_id}/turn")
async def turn(work_id:str,session_id:str,body:ExperienceTurnRequest,current_user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
 w=owned(db,work_id,current_user);x=db.query(models.ExperienceSession).filter_by(id=session_id,work_id=w.id,status="active").first()
 if not x:raise HTTPException(404,"进行中的体验不存在")
 s=db.query(models.ExperienceScript).filter_by(id=x.script_id,work_id=w.id).first();message=body.message.strip();h=list(x.history or []);h.append({"role":"user","content":message})
 def sse(event:str,data:dict):return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n"
 async def stream():
  chunks=[];model=""
  try:
   async for chunk,item_model in narrate_stream(db,s,h,message,str((x.state or {}).get("playerIdentity") or "")):
    chunks.append(chunk);model=item_model;yield sse("chunk",{"content":chunk})
   reply="".join(chunks).strip()
   if not reply:raise RuntimeError("大模型未返回可展示内容")
   h.append({"role":"assistant","content":reply,"model":model});x.history=h;x.turn+=1;x.updated_at=datetime.now(timezone.utc);db.commit()
   yield sse("done",{"reply":reply,"session":sess(x,True),"traceId":trace_id()})
  except Exception as exc:
   db.rollback();yield sse("error",{"message":str(exc),"traceId":trace_id()})
 return StreamingResponse(stream(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
