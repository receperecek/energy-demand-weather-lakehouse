select * from {{ ref('gold_hourly') }} where wind_solar_share<0 or wind_solar_share>1
