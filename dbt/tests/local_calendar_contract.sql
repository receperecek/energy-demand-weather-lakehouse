select region_code,local_date from {{ ref('gold_daily') }}
where calendar_hours not in (23,24,25) or scoped_hours>calendar_hours
   or valid_demand_hours>scoped_hours
   or (demand_day_complete and complete_day_demand_mwh is null)
   or (not demand_day_complete and complete_day_demand_mwh is not null)
