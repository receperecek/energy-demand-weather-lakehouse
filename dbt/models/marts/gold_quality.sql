select region_code,region_name,date(hour_utc) as utc_date,
    count(*) as expected_hours,count(demand_mwh) as observed_demand_hours,
    count(net_generation_mwh) as observed_generation_hours,
    count(case when weather_complete then 1 end) as complete_weather_hours,
    count(case when generation_share_eligible then 1 end) as generation_share_eligible_hours,
    max(generation_reconciliation_gap_mwh) as max_generation_gap_mwh,
    sum(coalesce(invalid_energy_records,0)) as invalid_energy_records,
    sum(coalesce(negative_generation_records,0)) as negative_generation_records
from {{ ref('gold_hourly') }}
group by region_code,region_name,date(hour_utc)
