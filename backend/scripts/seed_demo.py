import random
from datetime import date,timedelta,datetime,timezone
from src.config.database import Base,engine,Session
from src.models.entities import User,Event,TrainingInterval,IntervalState
from src.utils.security import hash_password
def day(offset):return (date(2026,9,21)+timedelta(days=offset)).isoformat()
def seed_intervals(s,start):
 """为演示学员登记按工号的参训区间：默认一段开区间；部分学员有离训空档或已离训。

 只补缺失工号，不覆盖人工修订过的区间；有新增时区间版本递增。
 """
 existing={r.learner for r in s.query(TrainingInterval).all()}
 added=0
 for i in range(200):
  learner=f'CQ-{i+1:03}';first=i//25;arrive=first*7-2;leave=first*7+61
  if learner in existing:continue
  created=datetime.now(timezone.utc).isoformat(timespec='seconds')
  if i%29==0:
   gap_start=first*7+18;gap_end=gap_start+12
   s.add(TrainingInterval(learner=learner,start_date=day(arrive),end_date=day(gap_start),created_at=created))
   s.add(TrainingInterval(learner=learner,start_date=day(gap_end),end_date=None,created_at=created));added+=2
  elif i%31==0:
   s.add(TrainingInterval(learner=learner,start_date=day(arrive),end_date=day(first*7+20),created_at=created));added+=1
  else:
   s.add(TrainingInterval(learner=learner,start_date=day(arrive),end_date=day(leave) if i%4==0 else None,created_at=created));added+=1
 state=s.get(IntervalState,1)
 if not state:s.add(IntervalState(id=1,version=1 if added else 0))
 elif added:state.version=int(state.version or 0)+1
def seed():
 Base.metadata.create_all(engine);rng=random.Random(3114);start=date(2026,9,21)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   email=role+'@demo.local'
   if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
  for i in range(200):
   first=i//25;learner=f'CQ-{i+1:03}'
   for w in range(first,9):
    if w!=first and rng.random()>.82-.07*(w-first):continue
    day_=start+timedelta(weeks=w,days=1+i%3);stamp=day_.isoformat()+'T02:00:00+00:00'
    code=f'{learner}-W{w}'
    if not s.query(Event).filter_by(code=code).first():s.add(Event(code=code,learner=learner,occurred_at=stamp,course=('数据素养','服务沟通','安全规范')[i%3],note='学习平台正常上报'))
    if i%17==0:
     code+='-DUP'
     if not s.query(Event).filter_by(code=code).first():s.add(Event(code=code,learner=learner,occurred_at=day_.isoformat()+'T04:00:00+00:00',course='数据素养',note='同周重复回访，不重复计人数'))
  seed_intervals(s,start)
  s.commit();print({'users':s.query(User).count(),'events':s.query(Event).count(),'learners':len({r.learner for r in s.query(Event).all()}),'intervals':s.query(TrainingInterval).count(),'interval_version':s.get(IntervalState,1).version if s.get(IntervalState,1) else None})
if __name__=='__main__':seed()
