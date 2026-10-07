select region_code, hour_utc,
    max(case when source='region-data' and metric_code='D' and is_valid then value_mwh end) as demand_mwh,
    max(case when source='region-data' and metric_code='NG' and is_valid then value_mwh end) as net_generation_mwh,
    sum(case when source='fuel-type-data' and is_valid then value_mwh end) as fuel_generation_mwh,
    sum(case when source='fuel-type-data' and is_valid and metric_code in ('SUN','WND') then value_mwh else 0 end) as wind_solar_mwh,
    sum(case when source='fuel-type-data' and is_valid and metric_code in ('SNB','WNB') then value_mwh else 0 end) as hybrid_generation_mwh,
    count(case when source='fuel-type-data' and is_valid then 1 end) as fuel_categories_observed,
    count(case when source='fuel-type-data' and is_valid and metric_code in ('SUN','WND') then 1 end) as wind_solar_categories_observed,
    count(case when not is_valid then 1 end) as invalid_energy_records,
    count(case when negative_net_generation then 1 end) as negative_generation_records
from {{ source('silver','silver_energy') }}
group by region_code,hour_utc
