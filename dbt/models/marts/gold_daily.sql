with totals as (
    select region_code,region_name,time_zone,local_date,
        count(*) as scoped_hours,count(demand_mwh) as valid_demand_hours,
        cast((unix_timestamp(to_utc_timestamp(cast(date_add(local_date,1) as timestamp),time_zone))
            -unix_timestamp(to_utc_timestamp(cast(local_date as timestamp),time_zone)))/3600 as int) as calendar_hours,
        sum(demand_mwh) as observed_demand_mwh,max(demand_mwh) as peak_hour_demand_mwh,
        count(case when weather_complete then 1 end) as complete_weather_hours,
        avg(case when weather_complete then proxy_temperature_c end) as mean_proxy_temperature_c,
        count(case when generation_share_eligible then 1 end) as eligible_generation_hours,
        sum(case when generation_share_eligible then wind_solar_mwh end) as eligible_wind_solar_mwh,
        sum(case when generation_share_eligible then net_generation_mwh end) as eligible_net_generation_mwh,
        count(case when high_demand_candidate then 1 end) as high_demand_candidate_hours,
        max(demand_deviation_score) as max_demand_deviation_score
    from {{ ref('gold_hourly') }}
    group by region_code,region_name,time_zone,local_date
)
select *,valid_demand_hours=calendar_hours and scoped_hours=calendar_hours as demand_day_complete,
    case when valid_demand_hours=calendar_hours and scoped_hours=calendar_hours then observed_demand_mwh end as complete_day_demand_mwh,
    eligible_wind_solar_mwh/nullif(eligible_net_generation_mwh,0) as observed_wind_solar_share
from totals
