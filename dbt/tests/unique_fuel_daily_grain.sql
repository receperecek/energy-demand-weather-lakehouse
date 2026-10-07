select region_code,local_date,fuel_code
from {{ ref('gold_fuel_daily') }}
group by region_code,local_date,fuel_code having count(*)>1
