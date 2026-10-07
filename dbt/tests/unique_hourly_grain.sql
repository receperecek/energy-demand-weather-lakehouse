select region_code,hour_utc,count(*) as records from {{ ref('gold_hourly') }} group by 1,2 having count(*)!=1
