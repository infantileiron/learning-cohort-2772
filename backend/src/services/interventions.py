from fastapi import HTTPException
from src.models.entities import Intervention
from src.services.intervals import current_version

def draft(s,cohort,data):
 """从冻结矩阵生成干预名单。成员只取当前仍在训的缺席者，并绑定当时区间版本。

 先锁区间版本行再校验方案版本与写入名单：与修订落库串行，避免名单带着已被
 修订淘汰的成员落库后永远无法重核。
 """
 version=current_version(s,lock=True)
 if cohort.state!='done':raise HTTPException(409,'队列计算完成后才能起草干预')
 if cohort.interval_version!=version:raise HTTPException(409,'参训区间已修订，该冻结方案版本落后；请新建方案后再起草干预')
 row=next((r for r in cohort.result['rows'] if r['cohort_week']==data.cohort_week),None)
 if not row:raise HTTPException(404,'所选首学队列不在该冻结方案中')
 cell=next((c for c in row['cells'] if c['week_index']==data.week_index),None)
 if not cell or not cell['mature']:raise HTTPException(409,'未成熟或超出观察范围的周禁止生成干预')
 members=list(cell.get('missing_current') or [])
 if not members:raise HTTPException(409,'该成熟周没有仍在训的缺席成员；已离训者只作删失记录，不进入干预')
 r=Intervention(**data.model_dump(),members=members,interval_version=version,recheck={'state':'fresh','version':version,'at_risk':cell['at_risk'],'censored':cell['censored']})
 s.add(r);s.commit();return r
