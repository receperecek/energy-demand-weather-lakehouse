select region_code,local_date,count(*) as records from {{ ref('gold_daily') }} group by 1,2 having count(*)!=1
