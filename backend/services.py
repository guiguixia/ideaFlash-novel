from __future__ import annotations
import io,json,re,zipfile
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from models import ExperienceScript,LLMConfig,SourceSegment,Work
from prompts.experience import render_experience_snapshot_extraction_prompt
from prompts.historical_question import render_historical_question_resolver_prompt
from prompts.scenario_context import render_scenario_initial_context_analysis_prompt
from trace import logger

def _llm_client(config:LLMConfig):return AsyncOpenAI(api_key=config.api_key,base_url=config.base_url or None,http_client=httpx.AsyncClient(trust_env=False,timeout=httpx.Timeout(90)),max_retries=0)
def _model_request_options(config:LLMConfig):
 """按供应商官方 OpenAI 兼容参数关闭可选思考，未知供应商不传扩展字段。"""
 base_url=(config.base_url or "").lower();model=(config.model or "").lower()
 if "deepseek" in base_url or model.startswith("deepseek-"):
  return {"extra_body":{"thinking":{"type":"disabled"}}}
 if "dashscope" in base_url or model.startswith("qwen"):
  return {"extra_body":{"enable_thinking":False}}
 if "bigmodel" in base_url or "z.ai" in base_url or model.startswith("glm-"):
  return {"extra_body":{"thinking":{"type":"disabled"}}}
 return {}
def _require_narration_config(config:LLMConfig|None):
 if not config or not config.api_key:raise RuntimeError("未配置大模型 API Key，无法继续体验")

def _log_llm_request(stage:str,config:LLMConfig,prompt:str,temperature:float,stream:bool=False,response_format:str="text"):
 logger.info("LLM_REQUEST_BEGIN\nstage: %s\nmodel: %s\nbase_url: %s\ntemperature: %s\nstream: %s\nresponse_format: %s\nprompt:\n%s\nLLM_REQUEST_END",stage,config.model,config.base_url,temperature,stream,response_format,prompt)

def _log_llm_response(stage:str,config:LLMConfig,content:str):
 logger.info("LLM_RESPONSE_BEGIN\nstage: %s\nmodel: %s\ncontent:\n%s\nLLM_RESPONSE_END",stage,config.model,content)

async def _narration_completion(config:LLMConfig,prompt:str,temperature:float,stage:str):
 client=_llm_client(config)
 try:
  _log_llm_request(stage,config,prompt,temperature)
  response=await client.chat.completions.create(model=config.model,messages=[{"role":"user","content":prompt}],temperature=temperature,**_model_request_options(config))
  content=(response.choices[0].message.content or "场景静待你的选择。").strip()
  _log_llm_response(stage,config,content)
  return content,config.model
 except Exception:
  logger.exception("LLM_REQUEST_FAILED stage=%s model=%s",stage,config.model)
  raise
 finally:await client.close()
async def _narration_stream(config:LLMConfig,prompt:str,temperature:float,stage:str):
 client=_llm_client(config)
 chunks=[]
 try:
  _log_llm_request(stage,config,prompt,temperature,stream=True)
  response=await client.chat.completions.create(model=config.model,messages=[{"role":"user","content":prompt}],temperature=temperature,stream=True,**_model_request_options(config))
  async for item in response:
   content=item.choices[0].delta.content if item.choices else ""
   if content:
    chunks.append(content)
    yield content
 except Exception:
  logger.exception("LLM_REQUEST_FAILED stage=%s model=%s",stage,config.model)
  raise
 finally:
  if chunks:_log_llm_response(stage,config,"".join(chunks))
  await client.close()
def split_source_document(filename:str,content:bytes):
 if filename.lower().endswith(".zip"):
  with zipfile.ZipFile(io.BytesIO(content)) as z:return sum((split_source_document(n,z.read(n)) for n in z.namelist() if n.lower().endswith((".txt",".md"))),[])
 text=content.decode("utf-8-sig",errors="ignore").replace("\r\n","\n").strip();marks=list(re.finditer(r"(?m)^(第[0-9一二三四五六七八九十百千零〇两]+[章节回卷].{0,80})$",text))
 if not marks:return [("导入资料",text)] if text else []
 return [(m.group(1)[:200],text[m.end():(marks[i+1].start() if i+1<len(marks) else len(text))].strip()) for i,m in enumerate(marks) if text[m.end():(marks[i+1].start() if i+1<len(marks) else len(text))].strip()]
def snapshot(work:Work,segments:list[SourceSegment],player:str):
 s=work.settings or {};return {"kind":work.work_type,"playerIdentity":player or s.get("playerIdentity") or "一名进入故事的旅人","openingScene":s.get("openingScene","") ,"world":s.get("world","") ,"tone":s.get("tone","") ,"sourceRange":[{"sequence":x.sequence,"title":x.title} for x in segments],"sourceText":"\n\n".join(f"{x.title}\n{x.content}" for x in segments)[:30000]}
async def _json_completion(db:Session,prompt:str,temperature:float=.1,stage:str="json_completion"):
 config=db.get(LLMConfig,1)
 if not config or not config.api_key:raise RuntimeError("未配置大模型 API Key，无法构建体验副本")
 if (config.base_url or "").rstrip("/").endswith("/chat/completions"):raise RuntimeError("大模型 Base URL 配置错误：请填写服务根地址，例如 https://api.deepseek.com 或 https://api.deepseek.com/v1，而不是 /chat/completions")
 client=_llm_client(config)
 try:
  _log_llm_request(stage,config,prompt,temperature,response_format="json_object")
  result=await client.chat.completions.create(model=config.model,messages=[{"role":"user","content":prompt}],temperature=temperature,response_format={"type":"json_object"},**_model_request_options(config))
  raw=(result.choices[0].message.content or "").strip()
  _log_llm_response(stage,config,raw)
  if not raw:raise RuntimeError(f"大模型 {config.model} 未返回内容")
  data=json.loads(raw)
  if not isinstance(data,dict):raise RuntimeError(f"大模型 {config.model} 未返回 JSON 对象")
  return data
 except RuntimeError:
  logger.exception("LLM_REQUEST_FAILED stage=%s model=%s",stage,config.model)
  raise
 except Exception as exc:
  logger.exception("LLM_REQUEST_FAILED stage=%s model=%s",stage,config.model)
  raise RuntimeError(f"大模型调用失败（{config.model}）：{exc.__class__.__name__}: {exc}") from exc
 finally:await client.close()
async def extract_experience_chapter(db:Session,segment:SourceSegment):
 cached=segment.experience_extraction if isinstance(segment.experience_extraction,dict) else {}
 if cached:return {**cached,"sourceSegmentOrder":segment.sequence,"chapterTitle":segment.title}
 prompt=render_experience_snapshot_extraction_prompt(segment.content[:18000])
 data=await _json_completion(db,prompt,stage=f"experience_chapter_extraction:{segment.sequence}")
 segment.experience_extraction=data
 db.commit()
 return {**data,"sourceSegmentOrder":segment.sequence,"chapterTitle":segment.title}
def _merge_named(rows:list[dict],key:str):
 merged={}
 for row in rows:
  for item in row.get(key) or []:
   if isinstance(item,dict) and item.get("name"):
    name=str(item["name"]);current=merged.setdefault(name,{**item,"sourceSegmentOrders":[]});current["sourceSegmentOrders"].append(row.get("sourceSegmentOrder"))
 return list(merged.values())
def experience_role_cards(snapshot:dict):
 first={}
 for chapter in snapshot.get("chapterExtractions") or []:
  for character in chapter.get("characters") or []:
   if isinstance(character,dict) and character.get("name"):first.setdefault(str(character["name"]),character)
 cards=[]
 for row in snapshot.get("extractedCharacters") or []:
  if not isinstance(row,dict) or not row.get("name"):continue
  attributes=dict(row.get("attributes") or {}) if isinstance(row.get("attributes"),dict) else {}
  initial=first.get(str(row["name"]),{})
  initial_attributes=initial.get("attributes") if isinstance(initial.get("attributes"),dict) else {}
  cards.append({"name":str(row["name"]),"identity":str(attributes.get("identity") or attributes.get("身份") or ""),"affiliation":str(attributes.get("affiliation") or attributes.get("所属势力") or attributes.get("势力") or ""),"ability":str(attributes.get("ability") or attributes.get("能力") or attributes.get("实力") or attributes.get("修为") or ""),"appearance":str(row.get("appearance") or initial.get("appearance") or ""),"currentState":str(initial_attributes.get("currentState") or initial_attributes.get("current_state") or initial_attributes.get("当前状态") or ""),"attributes":attributes,"sourceSegmentOrders":row.get("sourceSegmentOrders") or [],"roleMode":"replacement"})
 return cards
async def build_experience_snapshot(db:Session,work:Work,segments:list[SourceSegment],progress=None):
 # 兼容缓存字段上线前已经成功生成的副本：首次再次使用时，把其章节结果回填到资料片段。
 previous={}
 for script in db.query(ExperienceScript).filter(ExperienceScript.work_id==work.id,ExperienceScript.status=="ready").order_by(ExperienceScript.created_at.desc()).all():
  for chapter in (script.snapshot or {}).get("chapterExtractions") or []:
   if isinstance(chapter,dict) and isinstance(chapter.get("sourceSegmentOrder"),int):previous.setdefault(chapter["sourceSegmentOrder"],chapter)
 chapters=[]
 for index,segment in enumerate(segments,1):
  if not segment.experience_extraction and segment.sequence in previous:
   segment.experience_extraction={key:value for key,value in previous[segment.sequence].items() if key not in {"sourceSegmentOrder","chapterTitle"}}
   db.commit()
  chapters.append(await extract_experience_chapter(db,segment))
  if progress:await progress(index,"chapter_extraction")
 events=[{**item,"sourceSegmentOrder":row["sourceSegmentOrder"]} for row in chapters for item in row.get("events") or [] if isinstance(item,dict)]
 relations=[{**item,"sourceSegmentOrder":row["sourceSegmentOrder"]} for row in chapters for item in row.get("relations") or [] if isinstance(item,dict)]
 conflicts=[{**item,"sourceSegmentOrder":row["sourceSegmentOrder"]} for row in chapters for item in row.get("conflicts") or [] if isinstance(item,dict)]
 scenario_input={"startSourceSegment":segments[0].sequence,"endSourceSegment":segments[-1].sequence,"chapterExtractions":chapters,"extractedCharacters":_merge_named(chapters,"characters"),"factions":_merge_named(chapters,"factions"),"locations":_merge_named(chapters,"locations"),"entities":_merge_named(chapters,"entities"),"events":events,"relations":relations,"conflicts":conflicts}
 if progress:await progress(len(segments),"scenario_analysis")
 analysis=await _json_completion(db,render_scenario_initial_context_analysis_prompt(segments[0].sequence,segments[-1].sequence,json.dumps(scenario_input,ensure_ascii=False,separators=(",",":"))),stage=f"experience_scenario_analysis:{segments[0].sequence}-{segments[-1].sequence}")
 questions=analysis.get("historical_questions",[]) if isinstance(analysis.get("historical_questions"),list) else []
 resolved=[{**question,"status":"unresolved","accumulated_answer":"","remaining_need":"","evidence_chapters":[]} for question in questions[:8] if isinstance(question,dict) and question.get("id") and question.get("question")]
 history_rows=db.query(SourceSegment).filter(SourceSegment.work_id==work.id,SourceSegment.sequence<segments[0].sequence).order_by(SourceSegment.sequence.desc()).all()
 if progress:await progress(len(segments),"historical_backtracking")
 for row in history_rows:
  active=[question for question in resolved if question.get("status")!="resolved"]
  if not active:break
  answer=await _json_completion(db,render_historical_question_resolver_prompt(json.dumps(active,ensure_ascii=False,separators=(",",":")),row.sequence,row.content[:18000]),stage=f"experience_historical_backtracking:{row.sequence}")
  by_id={str(item.get("id")):item for item in answer.get("question_results",[]) if isinstance(item,dict)}
  for question in active:
   item=by_id.get(str(question["id"]))
   if not item:continue
   status=item.get("status")
   if status in {"resolved","partial","unresolved"}:question["status"]=status
   delta=str(item.get("answer_delta") or "").strip()
   if delta:question["accumulated_answer"]="；".join(filter(None,[str(question.get("accumulated_answer") or ""),delta]))
   question["remaining_need"]=str(item.get("remaining_need") or question.get("remaining_need") or "")
   if item.get("evidence"):question["evidence_chapters"].append({"sequence":row.sequence,"evidence":item["evidence"]})
 if progress:await progress(len(segments),"historical_backtracking")
 result={"mode":"experience_snapshot","startSourceSegment":segments[0].sequence,"endSourceSegment":segments[-1].sequence,"chapterRefs":[{"id":x.id,"sequence":x.sequence,"title":x.title} for x in segments],**scenario_input,"scenarioAnalysis":analysis,"confirmedPreload":analysis.get("confirmed_preload",[]),"historicalQuestions":resolved,"historicalBacktracking":{"searchedSegments":[x.sequence for x in history_rows]}}
 result["roleCards"]=experience_role_cards(result)
 return result
async def extract_character_names(db:Session,segments:list[SourceSegment]):
 text="\n\n".join(f"{x.title}\n{x.content}" for x in segments)[:40000];config=db.get(LLMConfig,1)
 if config and config.api_key:
  prompt="从以下小说或影视资料中抽取适合作为玩家身份的已命名角色。仅返回 JSON 字符串数组，例如 [\"萧炎\",\"药老\"]；最多 20 个；不含旁白、路人、你、我、他等泛称，也不要解释。\n\n"+text
  client=_llm_client(config)
  try:
   _log_llm_request("role_candidate_extraction",config,prompt,.1)
   reply=await client.chat.completions.create(model=config.model,messages=[{"role":"user","content":prompt}],temperature=.1,**_model_request_options(config))
   raw=(reply.choices[0].message.content or "").strip();_log_llm_response("role_candidate_extraction",config,raw);match=re.search(r"\[[\s\S]*\]",raw);names=json.loads(match.group(0) if match else raw)
   if isinstance(names,list):
    cleaned=[]
    for name in names:
     value=str(name).strip()
     if 1<len(value)<=20 and value not in cleaned:cleaned.append(value)
    if cleaned:return cleaned[:20]
  except Exception:logger.exception("LLM_REQUEST_FAILED stage=role_candidate_extraction model=%s",config.model)
  finally:await client.close()
 patterns=[r"([\u4e00-\u9fff]{2,4})[：:]",r"([\u4e00-\u9fff]{2,4})(?:说道|问道|笑道|喊道|答道)",r"(?:角色|人物)[：:]?\s*([\u4e00-\u9fff]{2,4})"]
 names=[]
 for pattern in patterns:
  for value in re.findall(pattern,text):
   if value not in {"这个","那里","他们","我们","自己","已经","不会","什么","一个","不是"} and value not in names:names.append(value)
 return names[:20]
async def narrate(db:Session,script:ExperienceScript,history:list[dict],message:str|None=None,player_identity:str=""):
 snap=script.snapshot or {};config=db.get(LLMConfig,1);identity=player_identity or snap.get("playerIdentity", "你")
 if snap.get("mode")=="experience_snapshot":
  role_card=next((row for row in snap.get("roleCards",[]) if isinstance(row,dict) and row.get("name")==identity),{})
  context={"scenario":(snap.get("scenarioAnalysis") or {}).get("scenario",{}),"confirmedPreload":snap.get("confirmedPreload",[]),"events":snap.get("events",[]),"relations":snap.get("relations",[]),"conflicts":snap.get("conflicts",[]),"historicalQuestions":snap.get("historicalQuestions",[]),"roleCard":role_card}
  _require_narration_config(config)
  recent="\n".join(f"{'玩家' if x.get('role')=='user' else '叙事者'}：{x.get('content','')}" for x in history[-10:])
  prompt=f"你是局部小说副本的剧情主持人。玩家替换角色：{identity}。只依据以下副本结构化事实推进，不能使用副本外知识或把后续事件提前给角色；不替玩家说话、行动或决定。当前会话实际发生的事优先于原事件轨迹。\n副本事实：{json.dumps(context,ensure_ascii=False)[:18000]}\n会话：{recent}\n玩家行动：{message or '生成副本开场'}\n输出中文沉浸式叙事，并在可行动节点停下。"
  return await _narration_completion(config,prompt,.35,"experience_narration")
 _require_narration_config(config)
 recent="\n".join(f"{'玩家' if x.get('role')=='user' else '叙事者'}：{x.get('content','')}" for x in history[-12:]);ctx=str(snap.get("sourceText") or snap.get("openingScene") or snap.get("world") or "")[:18000]
 prompt=f"你是私有互动故事叙事者。玩家身份：{identity}，视角：{script.perspective}。背景：{ctx}\n会话：{recent}\n玩家行动：{message or '生成开场'}\n中文沉浸式叙事；不复述长段来源文本，不替玩家决定或发言，结尾留出行动空间。"
 return await _narration_completion(config,prompt,.8,"original_story_narration")
async def narrate_stream(db:Session,script:ExperienceScript,history:list[dict],message:str,player_identity:str=""):
 snap=script.snapshot or {};config=db.get(LLMConfig,1);identity=player_identity or snap.get("playerIdentity", "你")
 if snap.get("mode")=="experience_snapshot":
  role_card=next((row for row in snap.get("roleCards",[]) if isinstance(row,dict) and row.get("name")==identity),{})
  context={"scenario":(snap.get("scenarioAnalysis") or {}).get("scenario",{}),"confirmedPreload":snap.get("confirmedPreload",[]),"events":snap.get("events",[]),"relations":snap.get("relations",[]),"conflicts":snap.get("conflicts",[]),"historicalQuestions":snap.get("historicalQuestions",[]),"roleCard":role_card}
  _require_narration_config(config)
  recent="\n".join(f"{'玩家' if x.get('role')=='user' else '叙事者'}：{x.get('content','')}" for x in history[-10:])
  prompt=f"你是局部小说副本的剧情主持人。玩家替换角色：{identity}。只依据以下副本结构化事实推进，不能使用副本外知识或把后续事件提前给角色；不替玩家说话、行动或决定。当前会话实际发生的事优先于原事件轨迹。\n副本事实：{json.dumps(context,ensure_ascii=False)[:18000]}\n会话：{recent}\n玩家行动：{message}\n输出中文沉浸式叙事，并在可行动节点停下。"
  async for chunk in _narration_stream(config,prompt,.35,"experience_narration_stream"):yield chunk,config.model
  return
 _require_narration_config(config)
 recent="\n".join(f"{'玩家' if x.get('role')=='user' else '叙事者'}：{x.get('content','')}" for x in history[-12:]);ctx=str(snap.get("sourceText") or snap.get("openingScene") or snap.get("world") or "")[:18000]
 prompt=f"你是私有互动故事叙事者。玩家身份：{identity}，视角：{script.perspective}。背景：{ctx}\n会话：{recent}\n玩家行动：{message}\n中文沉浸式叙事；不复述长段来源文本，不替玩家决定或发言，结尾留出行动空间。"
 async for chunk in _narration_stream(config,prompt,.8,"original_story_narration_stream"):yield chunk,config.model
