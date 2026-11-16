import os,time,json,logging
from pathlib import Path
import redis
from src.config.database import Session
from src.models.entities import Cohort,IntervalRevision
from src.services.analysis import calculate
from src.services.intervals import apply_revision
r=redis.Redis.from_url(os.environ['REDIS_URL'])
with Session() as recovery:
 for pending in recovery.query(Cohort).filter(Cohort.state.in_(['queued','running'])).all():
  pending.state='queued';r.rpush('cohort:jobs',pending.id)
 for pending in recovery.query(IntervalRevision).filter_by(status='processing').all():
  r.rpush('interval:jobs',pending.id)
 recovery.commit()
while True:
 Path('/tmp/heartbeat').touch()
 try:
  item=r.blpop(['interval:jobs','cohort:jobs'],timeout=3)
  if not item:continue
  queue,raw=item[0].decode(),int(item[1])
  if queue=='interval:jobs':
   with Session() as s:
    try:apply_revision(s,raw)
    except Exception as e:
     s.rollback();row=s.get(IntervalRevision,raw)
     if row and row.status!='completed':row.status='failed';row.error=str(e);s.commit()
     logging.exception('interval revision %s failed',raw)
   continue
  with Session() as s:
   row=s.get(Cohort,raw)
   if not row or row.state!='queued':continue
   snapshot=row.result['snapshot'];row.state='running';s.commit()
   try:
    row.result={**calculate(snapshot),'snapshot':snapshot};row.state='done'
    try:Path('/artifacts/'+str(row.id)+'.json').write_text(json.dumps(row.result,ensure_ascii=False))
    except OSError:logging.warning('artifact write skipped for cohort %s',row.id)
   except Exception as e:row.state='failed';row.error=str(e)
   s.commit()
 except Exception:logging.exception('worker');time.sleep(2)
