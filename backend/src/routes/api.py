import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import User,Event,Cohort,Intervention,Audit,IntervalRevision
from src.schemas.business import Login,EventInput,CohortInput,InterventionInput,NoteInput,IntervalRevisionInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.interventions import draft
from src.services.intervals import submit_revision,retry_revision,apply_revision,grouped,snapshot_intervals,ensure_approvable
from src.controllers.business import ensure_cohort,ensure_intervention
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/events')
def events(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Event).order_by(Event.id.desc()).all()]
@router.post('/events')
def event(data:EventInput,u=Depends(editor),s=Depends(db)):
 existing=s.query(Event).filter_by(code=data.code).first()
 if existing:
  if all(getattr(existing,k)==v for k,v in data.model_dump().items()):return dump(existing)
  raise HTTPException(409,'同事件编号的内容冲突，请修订原记录或使用新编号')
 r=Event(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:
  s.rollback();other=s.query(Event).filter_by(code=data.code).first()
  if other and all(getattr(other,k)==v for k,v in data.model_dump().items()):return dump(other)
  raise HTTPException(409,'同事件编号的内容冲突')
 audit(s,u,'录入学习事件 '+r.code);return dump(r)
@router.put('/events/{i}')
def edit_event(i:int,data:EventInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Event,i)
 if not r:raise HTTPException(404,'事件不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'事件编号重复')
 audit(s,u,'修订学习事件 '+str(i));return dump(r)
@router.get('/intervals')
def intervals(u=Depends(current),s=Depends(db)):return grouped(s)
@router.get('/intervals/revisions')
def revisions(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(IntervalRevision).order_by(IntervalRevision.id.desc()).all()]
@router.post('/intervals/revisions')
def create_revision(data:IntervalRevisionInput,u=Depends(editor),s=Depends(db)):
 try:r,replayed=submit_revision(s,data,u)
 except ValueError as exc:raise HTTPException(422,str(exc))
 if replayed:
  if r.status=='processing':_enqueue_interval(r.id,s)
  return {'revision':dump(r),'replayed':True,'idempotent':True}
 if not _enqueue_interval(r.id,s):raise HTTPException(503,'区间任务队列暂不可用，请稍后重试')
 audit(s,u,'受理参训区间修订 '+str(r.id)+' / '+r.learner)
 return {'revision':dump(r),'replayed':False,'idempotent':False}

def _enqueue_interval(revision_id,s=None):
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('interval:jobs',revision_id)
 except redis.RedisError:
  if s is not None:
   row=s.get(IntervalRevision,revision_id)
   if row and row.status=='processing':row.status='failed';row.error='区间任务队列暂不可用，请稍后重试';s.commit()
  return False
 return True
@router.get('/intervals/revisions/{i}')
def revision_detail(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(IntervalRevision,i)
 if not r:raise HTTPException(404,'区间修订不存在')
 return dump(r)
@router.post('/intervals/revisions/{i}/retry')
def revision_retry(i:int,u=Depends(editor),s=Depends(db)):
 r,allowed=retry_revision(s,i)
 if not allowed:return {'revision':dump(r),'replayed':True}
 try:result=apply_revision(s,i)
 except (ValueError,IntegrityError) as exc:
  s.rollback();r=s.get(IntervalRevision,i)
  if r and r.status!='completed':r.status='failed';r.error=str(exc);s.commit()
  raise HTTPException(409,str(exc))
 s.expire_all();r=s.get(IntervalRevision,i)
 audit(s,u,'重试参训区间修订 '+str(i)+' / '+r.learner)
 return {'revision':dump(r),'result':result,'replayed':False}
@router.get('/cohorts')
def cohorts(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Cohort).order_by(Cohort.id.desc()).all()]
@router.post('/cohorts')
def cohort(data:CohortInput,u=Depends(editor),s=Depends(db)):
 cfg=data.model_dump(mode='json');intervals,version=snapshot_intervals(s)
 snapshot={'config':cfg,'events':[dump(r) for r in s.query(Event).order_by(Event.id).all()],'intervals':intervals,'interval_version':version}
 r=Cohort(**cfg,result={'snapshot':snapshot},interval_version=version);s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'方案提交冲突，请重试')
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('cohort:jobs',r.id)
 except redis.RedisError:r.state='failed';r.error='队列暂不可用，请稍后重试';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交留存队列 '+str(r.id)+' @区间v'+str(version));return dump(r)
@router.get('/cohorts/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_cohort(s,i))
@router.get('/cohorts/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_cohort(s,i)
 if r.state!='done':raise HTTPException(409,'计算成功后才能导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="learning-cohort-{i}.json"'})
@router.get('/interventions')
def interventions(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Intervention).order_by(Intervention.id.desc()).all()]
@router.post('/interventions')
def intervention(data:InterventionInput,u=Depends(editor),s=Depends(db)):
 c=ensure_cohort(s,data.cohort_id)
 r=draft(s,c,data);audit(s,u,'生成干预清单 '+str(r.id)+' @区间v'+str(r.interval_version));return dump(r)
@router.put('/interventions/{i}')
def edit_intervention(i:int,data:NoteInput,u=Depends(editor),s=Depends(db)):
 r=ensure_intervention(s,i)
 if r.status!='draft':raise HTTPException(409,'已签核清单不可修改')
 r.note=data.note;s.commit();audit(s,u,'修订干预说明 '+str(i));return dump(r)
@router.post('/interventions/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=ensure_approvable(s,i)
 r.status='approved';s.commit();audit(s,u,'签核干预清单 '+str(i)+' @区间v'+str(r.interval_version));return dump(r)
@router.get('/interventions/{i}')
def intervention_detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_intervention(s,i))
@router.get('/interventions/{i}/export')
def action_export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_intervention(s,i);return dump(r)
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
