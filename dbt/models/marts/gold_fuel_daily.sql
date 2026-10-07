select e.region_code,h.region_name,h.local_date,e.metric_code as fuel_code,
    sum(e.value_mwh) as observed_generation_mwh,
    count(*) as reported_hours,
    count(case when e.negative_net_generation then 1 end) as negative_generation_hours
from {{ source('silver','silver_energy') }} e
join {{ ref('gold_hourly') }} h on e.region_code=h.region_code and e.hour_utc=h.hour_utc
where e.source='fuel-type-data' and e.is_valid
group by e.region_code,h.region_name,h.local_date,e.metric_code
