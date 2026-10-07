with a as (select region_code,sum(demand_mwh) as total from {{ ref('gold_hourly') }} group by 1),
b as (select region_code,sum(observed_demand_mwh) as total from {{ ref('gold_daily') }} group by 1)
select a.region_code from a join b on a.region_code=b.region_code where abs(a.total-b.total)>greatest(abs(a.total)*0.000000001,0.01)
