from sqlalchemy import Column,Integer,String,JSON,Text,ForeignKey,UniqueConstraint,Index
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True,nullable=False);password=Column(String(200));role=Column(String(20))
class Event(Base):
 __tablename__='events'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);learner=Column(String(60),nullable=False,index=True);occurred_at=Column(String(40),nullable=False);course=Column(String(40));note=Column(Text,default='')
class TrainingInterval(Base):
 __tablename__='training_intervals'
 __table_args__=(UniqueConstraint('learner','start_date',name='uq_interval_segment'),Index('ix_intervals_learner_start','learner','start_date'))
 id=Column(Integer,primary_key=True);learner=Column(String(60),nullable=False,index=True);start_date=Column(String(10),nullable=False);end_date=Column(String(10),nullable=True);revision_id=Column(Integer,ForeignKey('interval_revisions.id'),nullable=True);created_at=Column(String(40))
class IntervalState(Base):
 __tablename__='interval_state'
 id=Column(Integer,primary_key=True);version=Column(Integer,nullable=False,default=0)
class IntervalRevision(Base):
 __tablename__='interval_revisions'
 id=Column(Integer,primary_key=True);learner=Column(String(60),nullable=False,index=True);segments=Column(JSON,nullable=False);status=Column(String(20),default='processing');idempotency_key=Column(String(200),unique=True,nullable=False);fingerprint=Column(String(64),nullable=False);note=Column(Text,default='');requested_by=Column(String(100));created_at=Column(String(40));completed_at=Column(String(40),nullable=True);applied_version=Column(Integer,nullable=True);error=Column(Text,default='');result=Column(JSON,nullable=True)
class Cohort(Base):
 __tablename__='cohorts'
 id=Column(Integer,primary_key=True);name=Column(String(100));start_week=Column(String(10));end_week=Column(String(10));as_of=Column(String(10));horizon=Column(Integer);state=Column(String(20),default='queued');result=Column(JSON,nullable=True);error=Column(Text,default='');interval_version=Column(Integer,nullable=True)
class Intervention(Base):
 __tablename__='interventions'
 id=Column(Integer,primary_key=True);cohort_id=Column(Integer,ForeignKey('cohorts.id'));cohort_week=Column(String(10));week_index=Column(Integer);note=Column(Text);members=Column(JSON);status=Column(String(20),default='draft');interval_version=Column(Integer,nullable=True);recheck=Column(JSON,nullable=True)
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
