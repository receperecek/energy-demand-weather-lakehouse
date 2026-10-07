with hours as (
    select distinct explode(sequence(cast(start_date as timestamp), cast(end_date as timestamp)-interval 1 hour, interval 1 hour)) as hour_utc
    from {{ source('silver','pipeline_runs') }}
), joined as (
    select r.*,h.hour_utc,from_utc_timestamp(h.hour_utc,r.time_zone) as local_hour,
        e.* except(region_code,hour_utc), w.* except(region_code,hour_utc),
        coalesce(w.weather_points,0)=r.expected_weather_points as weather_complete,
        abs(e.fuel_generation_mwh-e.net_generation_mwh) as generation_reconciliation_gap_mwh,
        e.net_generation_mwh>0 and e.fuel_categories_observed>0
          and e.wind_solar_categories_observed=2
          and abs(e.fuel_generation_mwh-e.net_generation_mwh)<=greatest(abs(e.net_generation_mwh)*0.01,1)
          and e.wind_solar_mwh between 0 and e.net_generation_mwh as generation_share_eligible
    from hours h cross join {{ ref('dim_region') }} r
    left join {{ ref('int_energy_hour') }} e on r.region_code=e.region_code and h.hour_utc=e.hour_utc
    left join {{ ref('int_weather_region') }} w on r.region_code=w.region_code and h.hour_utc=w.hour_utc
), baseline as (
    select *,date(local_hour) as local_date,hour(local_hour) as hour_of_day,dayofweek(local_hour) as day_of_week,
        count(demand_mwh) over reference_window as reference_observations,
        avg(demand_mwh) over reference_window as trailing_reference_mwh,
        stddev_samp(demand_mwh) over reference_window as trailing_reference_std_mwh
    from joined
    window reference_window as (partition by region_code,dayofweek(local_hour),hour(local_hour) order by hour_utc rows between 8 preceding and 1 preceding)
)
select *,
    case when generation_share_eligible then wind_solar_mwh/net_generation_mwh end as wind_solar_share,
    case when reference_observations>=4 and trailing_reference_std_mwh>0
         then (demand_mwh-trailing_reference_mwh)/trailing_reference_std_mwh end as demand_deviation_score,
    case when reference_observations>=4 and trailing_reference_std_mwh>0
         then demand_mwh>trailing_reference_mwh+3*trailing_reference_std_mwh else false end as high_demand_candidate
from baseline
