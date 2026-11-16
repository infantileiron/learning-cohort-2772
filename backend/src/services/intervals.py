from datetime import datetime,timezone
import hashlib,json,uuid
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.models.entities import TrainingInterval,IntervalState,IntervalRevision,Cohort,Intervention
from src.services.calendar import normalize_segments

def _now():return datetime.now(timezone.utc).isoformat(timespec='seconds')

def _get_or_create_state(s):
 row=s.get(IntervalState,1)
 if not row:
  row=IntervalState(id=1,version=0);s.add(row);s.flush()
 return row

def current_version(s,lock=False):
 """读取全局区间版本。lock=True 取写锁供冻结/签核/落库串行化；读路径不建行不写入。"""
 if lock:
  row=s.query(IntervalState).filter_by(id=1).with_for_update().first()
  if not row:
   s.add(IntervalState(id=1,version=0));s.flush();row=s.get(IntervalState,1)
  return int(row.version or 0)
 row=s.query(IntervalState).filter_by(id=1).first()
 return int(row.version or 0) if row else 0

def bump_version(s):
 row=_get_or_create_state(s);row.version=int(row.version or 0)+1;s.flush();return int(row.version)

def snapshot_intervals(s,lock=True):
 """返回(一致快照,版本)。

 写路径(建方案)传 lock=True 锁住版本行，使修订落库与冻结互斥；读路径传
  lock=False，事务快照保证读到同一版本，双读再兜底 READ COMMITTED 下的交错。
 """
 if lock:
  locked=s.query(IntervalState).filter_by(id=1).with_for_update().first()
  if not locked:_get_or_create_state(s)
 for _ in range(5):
  v1=current_version(s)
  rows=s.query(TrainingInterval).order_by(TrainingInterval.learner,TrainingInterval.start_date,TrainingInterval.id).all()
  payload=[dict(id=r.id,learner=r.learner,start_date=r.start_date,end_date=r.end_date,revision_id=r.revision_id) for r in rows]
  if v1==current_version(s):return payload,v1
 raise HTTPException(409,'参训区间正在修订，请稍后重试')

def all_intervals(s):
 rows=s.query(TrainingInterval).order_by(TrainingInterval.learner,TrainingInterval.start_date,TrainingInterval.id).all()
 return [dict(id=r.id,learner=r.learner,start_date=r.start_date,end_date=r.end_date,revision_id=r.revision_id) for r in rows]

def grouped(s):
 payload,version=snapshot_intervals(s,lock=False);groups={}
 for row in payload:
  groups.setdefault(row['learner'],[]).append(dict(id=row['id'],start_date=row['start_date'],end_date=row['end_date'],revision_id=row['revision_id']))
 return {'version':version,'learners':[{'learner':learner,'segments':segments} for learner,segments in sorted(groups.items())],'interval_count':sum(len(v) for v in groups.values())}

def _fingerprint(learner,segments):
 return hashlib.sha256(json.dumps({'learner':learner,'segments':segments},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def _same(row,learner,segments):
 return row.learner==learner and normalize_segments(row.segments)==segments

def submit_revision(s,data,actor):
 learner=data.learner
 segments=normalize_segments([item.model_dump(mode='json') for item in data.segments])
 key=data.idempotency_key or uuid.uuid4().hex
 existing=s.query(IntervalRevision).filter_by(idempotency_key=key).first()
 if existing:
  if not _same(existing,learner,segments):raise HTTPException(409,'幂等键已被不同内容的修订占用')
  return existing,True
 # 锁版本行串行化受理：同一工号只允许一条在处理，避免并发修订互相覆盖。
 current_version(s,lock=True)
 pending=s.query(IntervalRevision).filter_by(learner=learner,status='processing').first()
 if pending and not (pending.idempotency_key==key and _same(pending,learner,segments)):
  raise HTTPException(409,'该工号已有处理中的区间修订，请等待完成后再提交')
 row=IntervalRevision(learner=learner,segments=segments,status='processing',idempotency_key=key,fingerprint=_fingerprint(learner,segments),note=data.note,requested_by=actor.email,created_at=_now())
 s.add(row)
 try:s.commit()
 except IntegrityError:
  s.rollback();other=s.query(IntervalRevision).filter_by(idempotency_key=key).first()
  if not other or not _same(other,learner,segments):raise HTTPException(409,'区间修订并发冲突，请刷新后重试')
  return other,True
 return row,False

def retry_revision(s,revision_id):
 row=s.query(IntervalRevision).filter_by(id=revision_id).with_for_update().first()
 if not row:raise HTTPException(404,'区间修订不存在')
 if row.status=='completed':return row,False
 if row.status!='failed':raise HTTPException(409,'该修订正在处理，不能重试')
 row.status='processing';row.error='';s.commit()
 return row,True

def apply_revision(s,revision_id):
 """把处理的修订落库并重核未签核名单，全部在一个事务内提交。

 幂等：已完成直接返回原结果；已落库但未完成只补做重核，不重复替换区间。
 并发：版本行加锁串行化，替换区间、版本递增和名单重核同事务可见；计算与签核
 只能读到修订前或修订后的完整版本，不会混用。
 """
 # 锁顺序：先版本行，后修订行；与签核、受理一致，避免死锁。
 before=current_version(s,lock=True)
 row=s.query(IntervalRevision).filter_by(id=revision_id).with_for_update().first()
 if not row:raise HTTPException(404,'区间修订不存在')
 if row.status=='completed':return row.result or {}
 if row.status!='processing':raise HTTPException(409,'该修订不在处理中')
 if row.applied_version is None:
  s.query(TrainingInterval).filter_by(learner=row.learner).delete(synchronize_session=False)
  for segment in row.segments:s.add(TrainingInterval(learner=row.learner,start_date=segment['start_date'],end_date=segment['end_date'],revision_id=row.id,created_at=_now()))
  s.flush()
  after=bump_version(s);row.applied_version=after
 else:after=row.applied_version
 rechecked=_recheck_drafts(s,row.learner,after)
 result={'learner':row.learner,'segments':row.segments,'version_before':before,'version_after':after,'rechecked':rechecked}
 row.status='completed';row.completed_at=_now();row.result=result;s.commit()
 return result

def _recheck_drafts(s,changed_learner,version):
 from src.services.analysis import calculate,members_for_cell
 drafts=s.query(Intervention).filter(Intervention.status=='draft').order_by(Intervention.id).all()
 if not drafts:return []
 intervals=all_intervals(s);cache={};results=[]
 for item in drafts:
  cohort=s.query(Cohort).populate_existing().filter_by(id=item.cohort_id).first();old=item.members or []
  if not cohort or cohort.state!='done' or not cohort.result or 'snapshot' not in (cohort.result or {}):
   item.recheck={'state':'pending','version':version,'checked_at':_now()};results.append({'intervention_id':item.id,'state':'pending'});continue
  if cohort.id not in cache:
   try:cache[cohort.id]=calculate({**cohort.result['snapshot'],'intervals':intervals,'interval_version':version})
   except ValueError as exc:cache[cohort.id]=exc
  computed=cache[cohort.id]
  if isinstance(computed,Exception):
   item.recheck={'state':'invalid','version':version,'detail':str(computed),'checked_at':_now()};results.append({'intervention_id':item.id,'state':'invalid'});continue
  cell=members_for_cell(computed,item.cohort_week,item.week_index)
  if not cell or not cell['mature']:
   item.recheck={'state':'invalid','version':version,'detail':'该首学队列或成熟周在修订后不再成立','checked_at':_now()};results.append({'intervention_id':item.id,'state':'invalid'});continue
  new_members=list(cell['missing_current'])
  added=sorted(set(new_members)-set(old));removed=sorted(set(old)-set(new_members))
  item.members=new_members;item.interval_version=version
  item.recheck={'state':'empty' if not new_members else 'rechecked','version':version,'added':added,'removed':removed,'at_risk':cell['at_risk'],'censored':cell['censored'],'changed_learner':changed_learner,'checked_at':_now()}
  results.append({'intervention_id':item.id,'state':item.recheck['state'],'added':added,'removed':removed})
 return results

def ensure_approvable(s,item_id):
 """签核一致性校验并锁定名单行。锁顺序先版本后名单，与修订落库一致。

 版本行锁把签核与修订落库串行化：签核要么看到旧版合法名单，要么看到重核后的
 新版名单；不会出现签核写回旧成员、或与修订交错后成员/版本不匹配。
 """
 version=current_version(s,lock=True)
 item=s.query(Intervention).filter_by(id=item_id).with_for_update().first()
 if not item:raise HTTPException(404,'干预清单不存在')
 if item.status!='draft':raise HTTPException(409,'已签核，不可重复签核')
 if item.interval_version!=version:raise HTTPException(409,'参训区间已修订，名单待重核，请刷新后再签核')
 recheck=item.recheck or {}
 if not recheck:raise HTTPException(409,'名单尚未完成重核，暂不能签核')
 if recheck.get('state') in ('pending','invalid','empty'):raise HTTPException(409,'名单正在重核或已失效，暂不能签核')
 if recheck.get('version')!=version:raise HTTPException(409,'名单重核版本与当前区间版本不一致，请刷新')
 if not item.members:raise HTTPException(409,'重核后没有仍在训的缺席成员，不能签核')
 return item
