from __future__ import annotations
import io,json,re,zipfile
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session
from models import ExperienceRoleCard,ExperienceScript,LLMConfig,RagSourceChunk,SourceSegment,Work
from prompts.experience import render_experience_snapshot_extraction_prompt
from prompts.historical_question import render_historical_question_resolver_prompt
from prompts.role_chat import render_role_card_chat_prompt,render_role_chat_memory_summary_prompt
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
def _source_chunks(text:str,size:int=500,overlap:int=50):
 step=size-overlap
 return [text[index:index+size].strip() for index in range(0,len(text),step) if text[index:index+size].strip()]
def _cosine(left:list[float],right:list[float]):
 numerator=sum(a*b for a,b in zip(left,right));denominator=(sum(a*a for a in left)*sum(b*b for b in right))**.5
 return numerator/denominator if denominator else 0
def _query_keywords(message:str,role_name:str):
 text=re.sub(r"[，。！？、；：,.!?\s]","",message)
 ignored={"为什么","怎么","什么","是不是","可以","能够","一下","这个","那个","然后","请问","知道","事情","关于"}
 candidates={role_name} if role_name else set()
 for size in range(2,min(8,len(text))+1):
  candidates.update(text[index:index+size] for index in range(len(text)-size+1))
 return [word for word in candidates if word and word not in ignored]
async def retrieve_prior_knowledge(db:Session,script:ExperienceScript,message:str,role_name:str,limit:int=5):
 """检索副本选中章节及此前的原文证据；副本结束后的章节不参与。"""
 upper_bound=script.source_end or script.source_start
 if not upper_bound:return []
 rows=db.query(RagSourceChunk).filter(RagSourceChunk.work_id==script.work_id,RagSourceChunk.source_segment_order<=upper_bound).all()
 if not rows:return []
 config=db.get(LLMConfig,1)
 try:query=(await _embed(config,[message]))[0]
 except Exception:return []
 keywords=_query_keywords(message,role_name);ranked=[]
 for row in rows:
  semantic=_cosine(query,row.embedding or []);keyword=sum(1 for word in keywords if len(word)>=2 and word in row.content)
  score=semantic+min(keyword,4)*.08+(0.04 if role_name and role_name in row.content else 0)
  ranked.append((score,row))
 ranked.sort(key=lambda item:item[0],reverse=True)
 return [{"chapter":row.source_segment_order,"title":row.source_title,"content":row.content,"score":round(score,4)} for score,row in ranked[:limit]]
def _retrieved_knowledge_lines(items:list[dict]):
 """把检索命中压缩为 Prompt 可引用的短原文证据。"""
 return "\n".join(f"- 第 {item['chapter']} 节《{item['title']}》：{item['content'][:500]}" for item in items) or "- （未检索到可用的副本前原文依据。）"
async def _embed(config:LLMConfig,texts:list[str]):
 if not config.embedding_base_url or not config.embedding_api_key or not config.embedding_model:raise RuntimeError("请先在大模型设置中配置 Embedding 服务")
 client=AsyncOpenAI(api_key=config.embedding_api_key,base_url=config.embedding_base_url,http_client=httpx.AsyncClient(trust_env=False,timeout=httpx.Timeout(90)),max_retries=0)
 try:
  response=await client.embeddings.create(model=config.embedding_model,input=texts,encoding_format="float")
  return [item.embedding for item in sorted(response.data,key=lambda item:item.index)]
 finally:await client.close()
def _work_rag_rows(db:Session,work:Work):
 segments=db.query(SourceSegment).filter_by(work_id=work.id).order_by(SourceSegment.sequence).all()
 return [(segment,order,text) for segment in segments for order,text in enumerate(_source_chunks(segment.content))]
def work_rag_index_progress(db:Session,work:Work):
 rows=_work_rag_rows(db,work);existing={(item.source_segment_order,item.chunk_order) for item in db.query(RagSourceChunk).filter_by(work_id=work.id).all()}
 completed=sum((segment.sequence,order) in existing for segment,order,_ in rows)
 return {"total":len(rows),"completed":completed,"remaining":len(rows)-completed}
async def build_work_rag_index(db:Session,work:Work):
 config=db.get(LLMConfig,1);rows=_work_rag_rows(db,work)
 completed={(item.source_segment_order,item.chunk_order) for item in db.query(RagSourceChunk).filter_by(work_id=work.id).all()};pending=[item for item in rows if (item[0].sequence,item[1]) not in completed]
 work.rag_status,work.rag_processed,work.rag_total,work.rag_error="building",len(rows)-len(pending),len(rows),"";db.commit()
 logger.info("RAG_INDEX_BUILD_BEGIN work_id=%s completed=%s total=%s remaining=%s embedding_model=%s embedding_base_url=%s",work.id,work.rag_processed,work.rag_total,len(pending),config.embedding_model if config else "",config.embedding_base_url if config else "")
 try:
  for start in range(0,len(pending),20):
   batch=pending[start:start+20];vectors=await _embed(config,[item[2] for item in batch])
   db.add_all([RagSourceChunk(work_id=work.id,source_segment_order=segment.sequence,source_title=segment.title,chunk_order=order,content=text,embedding=vector) for (segment,order,text),vector in zip(batch,vectors)])
   work.rag_processed=len(rows)-len(pending)+start+len(batch);db.commit()
  work.rag_status="ready";db.commit()
 except Exception as exc:
  work.rag_status,work.rag_error="failed",f"{exc.__class__.__name__}: {exc}";db.commit()
  logger.exception("RAG_INDEX_BUILD_FAILED work_id=%s processed=%s total=%s batch_start=%s batch_size=%s embedding_model=%s embedding_base_url=%s",work.id,work.rag_processed,work.rag_total,locals().get("start",0),len(locals().get("batch",[])),config.embedding_model if config else "",config.embedding_base_url if config else "")
  raise

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
EXTRACTION_SCHEMA_VERSION=2

async def extract_experience_chapter(db:Session,segment:SourceSegment):
 cached=segment.experience_extraction if isinstance(segment.experience_extraction,dict) else {}
 if cached.get("extractionSchemaVersion",1)>=EXTRACTION_SCHEMA_VERSION:return {**cached,"sourceSegmentOrder":segment.sequence,"chapterTitle":segment.title}
 prompt=render_experience_snapshot_extraction_prompt(segment.content[:18000])
 data=await _json_completion(db,prompt,stage=f"experience_chapter_extraction:{segment.sequence}")
 data["extractionSchemaVersion"]=EXTRACTION_SCHEMA_VERSION
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
def _role_dialogue_examples(snapshot:dict,name:str,limit:int=8):
 """按来源片段汇总角色原文短对白，供私聊时再挑选少量口吻参考。"""
 examples=[];seen=set()
 for chapter in snapshot.get("chapterExtractions") or []:
  order=chapter.get("sourceSegmentOrder")
  for character in chapter.get("characters") or []:
   if not isinstance(character,dict) or str(character.get("name") or "")!=name:continue
   for row in character.get("dialogues") or []:
    if not isinstance(row,dict):continue
    text=str(row.get("text") or "").strip()
    if not text or text in seen:continue
    seen.add(text);examples.append({"text":text[:80],"scene":str(row.get("scene") or "")[:80],"tone":str(row.get("tone") or "")[:40],"sourceSegmentOrder":order})
    if len(examples)>=limit:return examples
 return examples

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
  name=str(row["name"])
  cards.append({"name":name,"identity":str(attributes.get("identity") or attributes.get("身份") or ""),"affiliation":str(attributes.get("affiliation") or attributes.get("所属势力") or attributes.get("势力") or ""),"ability":str(attributes.get("ability") or attributes.get("能力") or attributes.get("实力") or attributes.get("修为") or ""),"appearance":str(row.get("appearance") or initial.get("appearance") or ""),"currentState":str(initial_attributes.get("currentState") or initial_attributes.get("current_state") or initial_attributes.get("当前状态") or ""),"attributes":attributes,"sourceSegmentOrders":row.get("sourceSegmentOrders") or [],"dialogueExamples":_role_dialogue_examples(snapshot,name),"roleMode":"replacement"})
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
  knowledge=await retrieve_prior_knowledge(db,script,message or f"{identity} 副本开始前的经历、关系与处境",identity)
  prompt=f"你是局部小说副本的剧情主持人。玩家替换角色：{identity}。只依据以下副本结构化事实推进，不能使用副本外知识或把后续事件提前给角色；不替玩家说话、行动或决定。当前会话实际发生的事优先于原事件轨迹。\n副本事实：{json.dumps(context,ensure_ascii=False)[:18000]}\n副本关联原文依据（覆盖副本选中章节及此前内容；可补充事实，但不要将未在当前会话发生的情节提前叙述为已发生）：\n{_retrieved_knowledge_lines(knowledge)}\n会话：{recent}\n玩家行动：{message or '生成副本开场'}\n输出中文沉浸式叙事，并在可行动节点停下。"
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
  knowledge=await retrieve_prior_knowledge(db,script,message,identity)
  prompt=f"你是局部小说副本的剧情主持人。玩家替换角色：{identity}。只依据以下副本结构化事实推进，不能使用副本外知识或把后续事件提前给角色；不替玩家说话、行动或决定。当前会话实际发生的事优先于原事件轨迹。\n副本事实：{json.dumps(context,ensure_ascii=False)[:18000]}\n副本关联原文依据（覆盖副本选中章节及此前内容；可补充事实，但不要将未在当前会话发生的情节提前叙述为已发生）：\n{_retrieved_knowledge_lines(knowledge)}\n会话：{recent}\n玩家行动：{message}\n输出中文沉浸式叙事，并在可行动节点停下。"
  async for chunk in _narration_stream(config,prompt,.35,"experience_narration_stream"):yield chunk,config.model
  return
 _require_narration_config(config)
 recent="\n".join(f"{'玩家' if x.get('role')=='user' else '叙事者'}：{x.get('content','')}" for x in history[-12:]);ctx=str(snap.get("sourceText") or snap.get("openingScene") or snap.get("world") or "")[:18000]
 prompt=f"你是私有互动故事叙事者。玩家身份：{identity}，视角：{script.perspective}。背景：{ctx}\n会话：{recent}\n玩家行动：{message}\n中文沉浸式叙事；不复述长段来源文本，不替玩家决定或发言，结尾留出行动空间。"
 async for chunk in _narration_stream(config,prompt,.8,"original_story_narration_stream"):yield chunk,config.model

ROLE_CHAT_CONTEXT_TURNS=15
ROLE_CHAT_SUMMARY_TURNS=10

async def role_chat_reply_stream(db:Session,script:ExperienceScript,card:ExperienceRoleCard,history:list[dict],message:str,memory_summary:str="",summary_cursor:int=0):
 config=db.get(LLMConfig,1);_require_narration_config(config)
 prompt=await _role_chat_prompt(db,script,card,history,message,memory_summary,summary_cursor)
 async for chunk in _narration_stream(config,prompt,.75,"role_card_chat_stream"):yield chunk,config.model

def _select_dialogue_examples(examples:list,limit:int=5):
 """优先覆盖不同来源片段，避免同一场景的对白占满 Prompt。"""
 selected=[];orders=set()
 for row in examples:
  if not isinstance(row,dict) or not row.get("text") or row.get("sourceSegmentOrder") in orders:continue
  selected.append(row);orders.add(row.get("sourceSegmentOrder"))
  if len(selected)>=limit:return selected
 for row in examples:
  if isinstance(row,dict) and row.get("text") and row not in selected:selected.append(row)
  if len(selected)>=limit:break
 return selected

async def _role_chat_prompt(db:Session,script:ExperienceScript,card:ExperienceRoleCard,history:list[dict],message:str,memory_summary:str="",summary_cursor:int=0):
 """整理私聊上下文；具体规则纳管在 prompts.role_chat，两个私聊入口共用。"""
 snap=script.snapshot or {};world=(snap.get("scenarioAnalysis") or {}).get("scenario",{}) if snap.get("mode")=="experience_snapshot" else {"world":(snap.get("world") or ""),"openingScene":snap.get("openingScene") or ""}
 custom_emotions=[{"id":str(item.get("id") or ""),"name":str(item.get("name") or ""),"description":str(item.get("description") or "")} for item in (card.custom_emotions or []) if item.get("id")]
 profile={"name":card.name,"identity":card.identity,"personality":card.personality,"appearance":card.appearance,"background":card.background,"currentState":card.current_state,"attributes":card.attributes or {}}
 recent="\n".join(f"{'用户' if row.get('role')=='user' else card.name}：{row.get('content','')}" for row in history[max(summary_cursor,0):][-ROLE_CHAT_CONTEXT_TURNS*2:])
 knowledge=await retrieve_prior_knowledge(db,script,message,card.name)
 return render_role_card_chat_prompt(role_name=card.name,profile_json=json.dumps(profile,ensure_ascii=False),world_json=json.dumps(world,ensure_ascii=False)[:6000],recent_messages=recent,memory_summary=memory_summary,message=message,custom_emotions_json=json.dumps(custom_emotions,ensure_ascii=False),dialogue_examples_json=json.dumps(_select_dialogue_examples(card.dialogue_examples or []),ensure_ascii=False),retrieved_knowledge_lines=_retrieved_knowledge_lines(knowledge))

def _completed_role_chat_turns(history:list[dict],cursor:int=0):
 """从未压缩历史中按时间顺序识别成功的“用户消息 + 角色回复”回合。"""
 turns=[];index=max(cursor,0)
 while index+1<len(history):
  user,assistant=history[index],history[index+1]
  if user.get("role")=="user" and assistant.get("role")=="assistant" and assistant.get("content") and assistant.get("status")!="failed":turns.append((user,assistant,index+2))
  index+=2
 return turns

def _format_role_chat_turns(turns:list[tuple[dict,dict,int]],role_name:str):
 """摘要输入保持时间升序，并保留说话者，避免摘要器混淆事实来源。"""
 return "\n\n".join(f"用户：{user.get('content','')}\n{role_name}：{assistant.get('content','')}" for user,assistant,_ in turns)

async def compact_role_chat_memory(db:Session,chat,card:ExperienceRoleCard):
 """每满 15 个未压缩成功回合，压缩最早 10 回合，完整 history 仍保留给界面展示。"""
 while True:
  turns=_completed_role_chat_turns(chat.history or [],chat.summary_cursor or 0)
  if len(turns)<ROLE_CHAT_CONTEXT_TURNS:return
  batch=turns[:ROLE_CHAT_SUMMARY_TURNS]
  config=db.get(LLMConfig,1);_require_narration_config(config)
  prompt=render_role_chat_memory_summary_prompt(previous_summary=chat.memory_summary or "",turns=_format_role_chat_turns(batch,card.name))
  try:
   summary,_=await _narration_completion(config,prompt,.25,"role_card_chat_summary")
  except Exception:
   logger.exception("ROLE_CHAT_SUMMARY_FAILED chat_id=%s",chat.id)
   return
  chat.memory_summary=summary[:800]
  chat.summary_cursor=batch[-1][2]
