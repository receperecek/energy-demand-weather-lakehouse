# Metric contracts

`hour_utc` always labels the beginning of a one-hour interval. EIA's source hour-ending labels are shifted minus one hour; NASA POWER's UTC labels already identify interval starts. Local dates and hours are derived only after this alignment.

| Metric | Grain and calculation | Eligibility and interpretation |
|---|---|---|
| Demand | One balancing authority × UTC hour; EIA type D, MWh | Finite positive source value. Missing or rejected demand stays null. |
| Observed daily demand | Authority × local date; sum of valid hourly MWh | A partial sum with explicit hour counts. |
| Complete-day demand | Observed daily demand | Requires all 23, 24 or 25 local-calendar hours and valid demand for each. UTC boundary days can be incomplete. |
| Peak hourly demand | Maximum valid hourly demand in a local day | MWh within the hour; numerically equal to hourly-average MW, not an instantaneous peak. |
| Net generation | EIA region-data type NG | Negative net generation is retained and flagged. |
| Fuel generation | Sum of valid fuel-type observations at the same UTC hour | Includes all known source categories, including storage. Unknown new categories are quarantined for review. |
| Wind + solar share | `(WND + SUN) / net_generation` | Both SUN and WND are reported and valid; net generation > 0; fuel totals reconcile within max(1 MWh, 1% of net generation); numerator in [0, denominator]. Ineligible share is null. |
| Reported fuel generation | Authority × local date × fuel; sum of signed valid MWh | Observed sum, with reported-hour and negative-hour counts. Missing categories are not inferred as zero. |
| Hybrid generation | SNB + WNB | Reported separately; never silently classed as pure solar or wind. |
| Daily observed wind + solar share | Sum of eligible hourly wind + solar / sum of eligible hourly net generation | Energy weighted, not the mean of hourly percentages. Eligible-hour coverage accompanies it. |
| Weather proxy | Equal-weight mean of three selected NASA POWER city grid cells | Complete only with all three valid points; not population/load/asset weighted. |
| Trailing demand reference | Mean/std of up to eight preceding observations with the same authority, local weekday and local hour | Needs at least four valid observations and nonzero std to calculate a deviation score. The repeated local hour on autumn DST is retained. |
| High-demand candidate | Demand > reference mean + 3 × reference sample std | Exploratory investigation flag. No claim of grid stress, scarcity, blackout probability or causation. |
| Source coverage | Observed valid hours / expected UTC hours | Grain is authority × UTC day. Expected-hour spine comes from completed ingestion windows, including gaps between disjoint windows only when explicitly requested. |

Hourly joins occur in UTC, which uniquely identifies autumn's repeated local hour. Local dates and schedules use each authority's IANA time zone. Weather-demand comparisons are descriptive and confounded by seasonality, economic activity, electrification, regional mix and other factors. Three city grid cells cannot represent an entire balancing authority or renewable fleet.
