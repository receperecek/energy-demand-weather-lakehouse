# Data sources and responsible use

Policy review date: 2026-10-07. Review the linked policies before deploying an independent copy; service terms can change.

## U.S. Energy Information Administration

Source: U.S. Energy Information Administration, API v2, electricity/rto/region-data and electricity/rto/fuel-type-data. The selected balancing authorities are ERCO, CISO and NYIS. Query frequency is hourly in UTC. Source values are megawatthours, including the hourly demand measure.

The [official EIA-930 instructions](https://www.eia.gov/survey/form/eia_930/instructions.pdf) define timestamps as **hour ending**. All platform `hour_utc` values identify **interval starts**: EIA periods are shifted back one hour before joining NASA weather or deriving local calendar dates. For a platform window `[2024-02-01, 2024-03-01)`, EIA's inclusive query labels run from `2024-02-01T01` through `2024-03-01T00`. The original labels remain in immutable source snapshots.

The [EIA reuse policy](https://www.eia.gov/about/copyrights_reuse.php) permits reuse of its government information products and requests acknowledgment including dates. The [API agreement](https://www.eia.gov/opendata/terms-of-service.php) requires source identification and prohibits implying endorsement, unauthorized logo use, false source representation and circumventing access limits. This project uses no EIA logo. Aggregations, quality flags and derived measures are project calculations, rather than products endorsed by EIA.

The [API FAQ](https://www.eia.gov/opendata/faqs.php) describes approximate operating guidance rather than guaranteed quotas. This client uses sequential requests, at most one attempt per second per host, at most 1,000 attempts per host per process, four attempts per request, bounded delays for 429/5xx, and fails on exhausted budgets. No key rotation or parallel workers bypass source limits. A job permits only one concurrent run.

The source API caps each page at 5,000 rows. Pagination verifies the total and fails when it changes or a page is incomplete. A successful collection does not prove the provider contains every expected observation; expected-hour coverage is calculated separately. EIA request echoes are removed because they can contain the API key.

## NASA POWER

Weather and radiation source: [NASA Prediction Of Worldwide Energy Resources](https://power.larc.nasa.gov/), NASA Langley Research Center. Meteorology derives from MERRA-2 and radiation from CERES/POWER products; each acquired response retains its source names and API version. The [NASA POWER Team's official usage explanation](https://forum.earthdata.nasa.gov/viewtopic.php?t=82) states that POWER data are public domain and can be used in research, publications and commercial applications with acknowledgment. A [current NASA POWER impact story](https://power.larc.nasa.gov/article/smart-battery-optimization-creates-affordable-energy/) also describes commercial energy applications. No NASA logo or endorsement is asserted.

Parameters are T2M (degrees Celsius), WS10M (m/s), and ALLSKY_SFC_SW_DWN (Wh/m² over the source's one-hour interval). Dividing hourly irradiation by its one-hour duration gives the numerically equivalent mean irradiance in W/m² stored as `shortwave_wm2`. Wind is measured at 10 m and is a regional context variable, not a turbine-height output predictor.

The [hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/) defaults to local solar time; this client explicitly requests UTC and checks the returned hour keys. NASA's [time guidance](https://power.larc.nasa.gov/docs/faqs/other/) describes hourly timestamps as the beginning of the interval. The `-999` source fill value is treated as missing, never as a physical measurement.

Three selected cities per region are equal-weight proxies. NASA's [resolution and latency documentation](https://power.larc.nasa.gov/docs/faqs/data/) explains that the gridded values are spatial averages, rather than observations at the exact city coordinates. They do not measure every load centre or generating asset. The [download guidance](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/) discusses the coarser radiation/meteorology grids and later meteorological revisions. The project's locations are separated by more than one meteorological grid cell.

NASA [does not publish a fixed POWER rate limit](https://forum.earthdata.nasa.gov/viewtopic.php?t=4273) and can restrict excessive use. Requests are sequential and obey the same conservative application limits as EIA. Historical requests are partitioned by calendar year and incremental requests cover only a bounded lookback. Cached immutable snapshots support replay without calling the sources again.

## Publication boundaries

The repository contains original project code under MIT, technical documentation and attributed aggregate evidence. MIT does not replace the providers' usage policies. Credentials, authentication caches, full API dumps, local learning materials and workspace-specific deployment state are excluded. The published report must include retrieval dates, requested scope and transformations. Dashboard charts identify EIA and NASA POWER as sources.

Open-Meteo was evaluated but is not used by the delivered client: its [free API terms](https://open-meteo.com/en/terms) restrict commercial and promotional use. NASA POWER avoids depending on an interpretation of a personal portfolio's promotional purpose.

These checks document the implementation and identified source permissions; they are not a guarantee against every legal or security risk.
