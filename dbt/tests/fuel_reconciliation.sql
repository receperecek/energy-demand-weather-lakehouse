with a as (
    select region_code,sum(value_mwh) as total
    from {{ source('silver','silver_energy') }} where source='fuel-type-data' and is_valid group by 1
), b as (
    select region_code,sum(observed_generation_mwh) as total from {{ ref('gold_fuel_daily') }} group by 1
)
select coalesce(a.region_code,b.region_code) from a full outer join b using(region_code)
where a.total is null or b.total is null or abs(a.total-b.total)>greatest(abs(a.total)*0.000000001,0.01)
