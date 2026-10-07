select region_code,hour_utc,
    count(distinct case when is_valid then location_id end) as weather_points,
    avg(case when is_valid then temperature_c end) as proxy_temperature_c,
    min(case when is_valid then temperature_c end) as min_point_temperature_c,
    max(case when is_valid then temperature_c end) as max_point_temperature_c,
    avg(case when is_valid then wind_speed_ms end) as proxy_wind_speed_ms,
    avg(case when is_valid then shortwave_wm2 end) as proxy_shortwave_wm2
from {{ source('silver','silver_weather') }}
group by region_code,hour_utc
