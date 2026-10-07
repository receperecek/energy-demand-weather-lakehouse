with a as (
    select region_code,hour_utc,count(distinct location_id) as points,
        avg(temperature_c) as mean_temperature
    from {{ source('silver','silver_weather') }} where is_valid group by 1,2
)
select h.region_code,h.hour_utc from {{ ref('gold_hourly') }} h left join a using(region_code,hour_utc)
where coalesce(h.weather_points,0)!=coalesce(a.points,0)
   or coalesce(abs(h.proxy_temperature_c-a.mean_temperature)>0.0000001,false)
   or h.weather_complete!=(coalesce(a.points,0)=h.expected_weather_points)
