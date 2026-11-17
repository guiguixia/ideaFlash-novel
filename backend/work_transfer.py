from __future__ import annotations
import json, shutil, zipfile
from pathlib import Path
from sqlalchemy.orm import Session
import models

FORMAT_VERSION=1

def task_data(task, asset_dir:Path):
    return {"id":task.id,"type":task.task_type,"status":task.status,"stage":task.stage,"processed":task.processed,"total":task.total,"error":task.error,"workId":task.work_id or None,"fileUrl":f"/uploads/transfers/{task.output_path}" if task.output_path and (asset_dir/task.output_path).exists() else "","createdAt":task.created_at.isoformat() if task.created_at else None,"updatedAt":task.updated_at.isoformat() if task.updated_at else None}

def _row(row, names): return {name:getattr(row,name) for name in names}
def _copy_asset(zf, asset_dir:Path, path:str, prefix:str, copied:set[str]):
    if not path or path in copied or not (asset_dir/path).is_file(): return
    zf.write(asset_dir/path, f"assets/{prefix}/{path}"); copied.add(path)

def export_work(db:Session, task_id:str, asset_dir:Path, export_dir:Path):
    task=db.get(models.WorkTransferTask,task_id); work=db.get(models.Work,task.work_id)
    if not task or not work or task.status == "cancelled": return
    try:
        task.status,task.stage,task.total="running","收集作品数据",4; db.commit()
        scripts=db.query(models.ExperienceScript).filter_by(work_id=work.id).all()
        cards=db.query(models.ExperienceRoleCard).filter_by(work_id=work.id).all()
        roles=db.query(models.WorkRole).filter_by(work_id=work.id).all()
        data={"work":_row(work,["title","work_type","summary","settings","status"]),"segments":[_row(x,["sequence","title","content","experience_extraction"]) for x in db.query(models.SourceSegment).filter_by(work_id=work.id).order_by(models.SourceSegment.sequence)],"scripts":[_row(x,["id","title","source_start","source_end","player_identity","perspective","version","status","snapshot"]) for x in scripts],"roleCards":[_row(x,["script_id","name","identity","personality","appearance","background","current_state","attributes","source_segment_orders","dialogue_examples","image_path","emotion_images","emotion_descriptions","special_emotion_label","custom_emotions"]) for x in cards],"roles":[_row(x,["name","aliases","identity","personality","speech_style","appearance","background","memory_chapter","image_path"]) for x in roles]}
        task.processed,task.stage=1,"写入作品包"; db.commit(); export_dir.mkdir(parents=True,exist_ok=True)
        filename=f"{work.title[:80]}-{task.id[:8]}.novel-work.zip"; target=export_dir/filename; copied=set()
        with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json",json.dumps({"format":"ideaFlash-work","version":FORMAT_VERSION,"title":work.title},ensure_ascii=False))
            zf.writestr("work.json",json.dumps(data,ensure_ascii=False))
            for card in cards:
                _copy_asset(zf,asset_dir,card.image_path,"role-cards",copied)
                for path in (card.emotion_images or {}).values(): _copy_asset(zf,asset_dir,path,"role-cards",copied)
                for item in card.custom_emotions or []: _copy_asset(zf,asset_dir,str(item.get("image_path") or ""),"role-cards",copied)
            for role in roles: _copy_asset(zf,asset_dir,role.image_path,"role-cards",copied)
        task.status,task.stage,task.processed,task.total,task.output_path="succeeded","已完成",4,4,filename; db.commit()
    except Exception as exc:
        task.status,task.stage,task.error="failed","失败",f"{type(exc).__name__}: {exc}";db.commit()

def import_work(db:Session, task_id:str, upload_dir:Path, asset_dir:Path):
    task=db.get(models.WorkTransferTask,task_id)
    if not task or task.status == "cancelled":return
    try:
        task.status,task.stage,task.total="running","校验作品包",4;db.commit(); path=upload_dir/task.input_path
        with zipfile.ZipFile(path) as zf:
            manifest=json.loads(zf.read("manifest.json")); data=json.loads(zf.read("work.json"))
            if manifest.get("format")!="ideaFlash-work" or manifest.get("version")!=FORMAT_VERSION: raise ValueError("不支持的作品包版本")
            title=str(data["work"].get("title") or "未命名作品")[:160]
            if db.query(models.Work).filter_by(platform_user_id=task.platform_user_id,title=title).first(): title=f"{title[:155]}-{task.id[:4].upper()}"
            task.stage,task.processed="恢复来源资料",1;db.commit()
            w=models.Work(platform_user_id=task.platform_user_id,title=title,work_type=data["work"].get("work_type") or "imported_novel",summary=data["work"].get("summary") or "",settings=data["work"].get("settings") or {},status=data["work"].get("status") or "draft",rag_status="not_built",rag_processed=0,rag_total=0,rag_error="");db.add(w);db.flush()
            db.add_all([models.SourceSegment(work_id=w.id,**x) for x in data.get("segments",[])])
            task.stage,task.processed="恢复剧情与角色",2;db.commit(); ids={}
            for x in data.get("scripts",[]): old=x.pop("id",""); row=models.ExperienceScript(work_id=w.id,**x);db.add(row);db.flush();ids[old]=row.id
            for x in data.get("roleCards",[]): x["script_id"]=ids.get(x.get("script_id"),x.get("script_id"));db.add(models.ExperienceRoleCard(work_id=w.id,**x))
            for x in data.get("roles",[]): db.add(models.WorkRole(work_id=w.id,**x))
            task.stage,task.processed="恢复图片资源",3;db.commit()
            for name in zf.namelist():
                if name.startswith("assets/role-cards/") and "/" not in name.removeprefix("assets/role-cards/"):
                    (asset_dir/Path(name).name).write_bytes(zf.read(name))
        task.work_id=w.id;task.status,task.stage,task.processed="succeeded","已完成",4;db.commit()
    except Exception as exc:
        task.status,task.stage,task.error="failed","失败",f"{type(exc).__name__}: {exc}";db.commit()
