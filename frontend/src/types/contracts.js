/** @typedef {{id:number,code:string,learner:string,occurred_at:string,course:string,note:string}} Event */
/** @typedef {{id:number,learner:string,start_date:string,end_date:string|null,revision_id:number|null}} TrainingInterval */
/** @typedef {{id:number,learner:string,segments:Array<{start_date:string,end_date:string|null}>,status:string,idempotency_key:string,applied_version:number|null,result:object|null,error:string}} IntervalRevision */
/** @typedef {{id:number,name:string,start_week:string,end_week:string,as_of:string,horizon:number,state:string,interval_version:number|null,result:object}} Cohort */
/** @typedef {{id:number,cohort_id:number,cohort_week:string,week_index:number,members:string[],note:string,status:string,interval_version:number|null,recheck:object|null}} Intervention */
