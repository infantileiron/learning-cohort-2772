from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
import hashlib,json
from src.services.calendar import to_date,week_end,monday,coverage_days,segment_end,still_in_training

TZ=ZoneInfo('Asia/Shanghai')

def _index_intervals(snapshot):
 by_learner=defaultdict(list)
 for item in snapshot.get('intervals',[]):
  by_learner[item['learner']].append(dict(id=item.get('id'),start_date=to_date(item['start_date']).isoformat(),end_date=to_date(item['end_date']).isoformat() if item.get('end_date') else None,revision_id=item.get('revision_id')))
 for learner in by_learner:by_learner[learner].sort(key=lambda s:(s['start_date'],s['id'] or 0))
 return by_learner

def _event_days(snapshot,as_of):
 days=defaultdict(set);future=0
 for event in snapshot['events']:
  ts=datetime.fromisoformat(event['occurred_at'].replace('Z','+00:00'))
  if ts.tzinfo is None:raise ValueError('事件缺少时区')
  day=ts.astimezone(TZ).date()
  if day>as_of:future+=1;continue
  days[event['learner']].add(day)
 return days,future

def _in_segment(segment,day):
 return to_date(segment['start_date'])<=day<=segment_end(segment)

def _visit_days(days,target,segment):
 return sum(1 for day in days if target<=day<=week_end(target) and _in_segment(segment,day))

def _censor_basis(segment,all_segments,target,as_of):
 start=target;end=week_end(target);start_bound=to_date(segment['start_date']);end_bound=segment_end(segment)
 if start_bound>end:
  return 'not_started',f'该周尚未入训；该段参训区间自 {start_bound.isoformat()} 开始'
 later=sorted((s for s in all_segments if to_date(s['start_date'])>end_bound),key=lambda s:s['start_date'])
 if later and to_date(later[0]['start_date'])<=as_of:
  return 'returned',f'该周全程离训；旧段于 {end_bound.isoformat()} 结束，返训另开新段（{later[0]["start_date"]} 起），旧段不复活'
 if later:
  return 'left',f'该周全程离训；参训区间于 {end_bound.isoformat()} 结束，截至 {as_of.isoformat()} 尚未返训'
 return 'left',f'该周全程离训；参训区间于 {end_bound.isoformat()} 结束'

def calculate(snapshot):
 """按冻结的参训区间与事件计算首学队列、风险人数、回访和删失。

 每名学员的每一段参训区间独立建队列：队列周=该段内首次“在训”学习所在 ISO 周一。
 目标周内只要还有一天在训就进入风险分母；整周全程离训才删失并记录依据。只有落在
 该段区间内的事件才计回访。返训只生成新段队列，旧段不会因返训复活。
 """
 cfg=snapshot['config'];as_of=date.fromisoformat(cfg['as_of']);start=date.fromisoformat(cfg['start_week']);end=date.fromisoformat(cfg['end_week']);horizon=cfg['horizon']
 by_learner=_index_intervals(snapshot)
 days,future=_event_days(snapshot,as_of)
 entries=defaultdict(lambda:defaultdict(list));unregistered=[]
 for learner in sorted(days):
  segments=by_learner.get(learner) or []
  if not segments:
   unregistered.append(learner);continue
  for segment in segments:
   first=next((day for day in sorted(days[learner]) if _in_segment(segment,day)),None)
   if first is None:continue
   week=monday(first)
   if not (start<=week<=end):continue
   bucket=entries[week][learner]
   if all(item['segment_id']!=segment['id'] for item in bucket):bucket.append({'learner':learner,'segment':segment,'segment_id':segment['id'],'first_day':first})
 if not entries:raise ValueError('所选首学周没有在训队列；请核对参训区间、事件与队列窗口')
 rows=[]
 for week in sorted(entries):
  cohort=entries[week]
  rows_cells=[]
  for i in range(horizon+1):
   target=week+timedelta(weeks=i);mature=target+timedelta(days=6)<=as_of
   cell=dict(week_index=i,target_week=target.isoformat(),mature=mature,size=len(cohort),at_risk=None,active=None,rate=None,visited=[],missing=[],missing_current=[],left_since=[],censored=0,censored_members=[])
   if mature:
    at_risk=[];visited_learners=[];censored=[]
    for learner in sorted(cohort):
     bucket=cohort[learner];covering=[item for item in bucket if coverage_days([item['segment']],target)>0]
     if not covering:
      before=[item for item in bucket if to_date(item['segment']['start_date'])<=week_end(target)]
      basis=(max(before,key=lambda item:(item['segment']['start_date'],str(item['segment_id']))) if before
             else min(bucket,key=lambda item:(item['segment']['start_date'],str(item['segment_id']))))
      reason,detail=_censor_basis(basis['segment'],by_learner[learner],target,as_of)
      censored.append({'learner':learner,'segment_id':basis['segment_id'],'segment_start':basis['segment']['start_date'],'segment_end':basis['segment']['end_date'],'reason':reason,'detail':detail})
      continue
     at_risk.append(learner)
     if any(_visit_days(days[learner],target,item['segment'])>0 for item in covering):visited_learners.append(learner)
    missing=[learner for learner in at_risk if learner not in visited_learners]
    missing_current=sorted(learner for learner in missing if still_in_training(by_learner[learner],as_of))
    cell.update(at_risk=len(at_risk),active=len(visited_learners),visited=visited_learners,missing=missing,missing_current=missing_current,left_since=sorted(set(missing)-set(missing_current)),rate=(len(visited_learners)/len(at_risk) if at_risk else None),censored=len(censored),censored_members=censored)
   rows_cells.append(cell)
  rows.append(dict(cohort_week=week.isoformat(),iso_label=f'{week.isocalendar().year}-W{week.isocalendar().week:02}',size=len(cohort),entries=sum(len(b) for b in cohort.values()),members=sorted(cohort),cells=rows_cells))
 return dict(rows=rows,learners=len({m for r in rows for m in r['members']}),cohort_entries=sum(r['entries'] for r in rows),unique_learners_before_cutoff=len(days),learners_without_interval=len(unregistered),unregistered_learners=unregistered,future_events_excluded=future,event_count=len(snapshot['events']),interval_count=len(snapshot.get('intervals',[])),interval_version=snapshot.get('interval_version'),as_of=cfg['as_of'],timezone='Asia/Shanghai',checksum=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),method='按Asia/Shanghai业务日归周；冻结参训区间与事件。每名学员的每段区间独立建队列，队列周=该段内首次在训学习所在ISO周一。目标周内任意一天在训即计入风险分母；整周全程离训才删失并给出依据。只有落在该段区间内的事件才计回访，每人每周最多1次。返训另开新段，旧段不复活。目标周周日≤截至日才成熟；未成熟不展示数字。')

def members_for_cell(result,cohort_week,week_index):
 row=next((r for r in result.get('rows',[]) if r['cohort_week']==cohort_week),None)
 if not row:return None
 return next((c for c in row['cells'] if c['week_index']==week_index),None)
