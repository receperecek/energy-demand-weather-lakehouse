select region_code,region_name,local_date,peak_hour_demand_mwh,high_demand_candidate_hours,
    max_demand_deviation_score,mean_proxy_temperature_c,observed_wind_solar_share,
    demand_day_complete,complete_weather_hours,calendar_hours,eligible_generation_hours,
    case when not demand_day_complete then 'DATA_REVIEW'
         when high_demand_candidate_hours>0 and complete_weather_hours=calendar_hours then 'DEMAND_REVIEW'
         when high_demand_candidate_hours>0 then 'DEMAND_AND_DATA_REVIEW'
         else 'ROUTINE' end as review_priority
from {{ ref('gold_daily') }}
