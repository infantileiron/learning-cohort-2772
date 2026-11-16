from datetime import date,timedelta

def to_date(value):
 if isinstance(value,date):return value
 return date.fromisoformat(str(value)[:10])

def week_end(week_start):return to_date(week_start)+timedelta(days=6)

def monday(day):return day-timedelta(days=day.weekday())

def normalize_segments(items,error=ValueError):
 parsed=[]
 for item in items:
  start=to_date(item['start_date']);end=item.get('end_date')
  end=to_date(end) if end else None
  if end and end<start:raise error('参训区间结束日不能早于开始日')
  parsed.append({'start_date':start.isoformat(),'end_date':end.isoformat() if end else None})
 parsed.sort(key=lambda x:x['start_date'])
 for a,b in zip(parsed,parsed[1:]):
  if b['start_date']<=(a['end_date'] or '9999-12-31'):raise error('同工号参训区间不允许重叠')
 return parsed

def segment_end(segment):
 return to_date(segment['end_date']) if segment['end_date'] else date.max

def coverage_days(segments,week_start):
 covered=set();start=to_date(week_start);end=week_end(start)
 for s in segments:
  a=max(to_date(s['start_date']),start);b=min(segment_end(s),end)
  if a<=b:
   covered.update(a+timedelta(days=offset) for offset in range((b-a).days+1))
 return len(covered)

def still_in_training(segments,as_of):
 return any(to_date(s['start_date'])<=as_of<=segment_end(s) for s in segments)
