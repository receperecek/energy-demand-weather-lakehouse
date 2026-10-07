with source_totals as (
    select region_code,sum(value_mwh) as demand from {{ source('silver','silver_energy') }}
    where source='region-data' and metric_code='D' and is_valid group by 1
), gold_totals as (
    select region_code,sum(demand_mwh) as demand from {{ ref('gold_hourly') }} group by 1
)
select coalesce(s.region_code,g.region_code) as region_code from source_totals s full join gold_totals g on s.region_code=g.region_code
where s.demand is null or g.demand is null or abs(s.demand-g.demand)>greatest(abs(s.demand)*0.000000001,0.01)
