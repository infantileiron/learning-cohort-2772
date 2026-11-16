export const routes=['事件台账','参训区间','队列配置','留存矩阵','干预清单'];export const page=()=>Math.min(routes.length-1,Math.max(0,Number(location.hash.slice(1)||0)));
