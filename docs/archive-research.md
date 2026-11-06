# Binance archive inspection

Inspected on November 6, 2026. This is a research and integration plan. The sampled archives were parsed in memory and were not imported into the live database.

## Source and sample coverage

[Binance's public-data repository](https://github.com/binance/binance-public-data) documents archive access and provides download helpers. ZIP/CSV datasets are served by data.binance.vision. The repository documents daily/monthly releases, checksum files and possible later archive revisions.

Four daily USD-M files dated November 5, 2026 were inspected, covering BTCUSDT and 1000PEPEUSDT, with one metrics file and one 5m kline file per contract. Each ZIP matched its published SHA-256 checksum. Each contained a header plus 288 records. Each dataset had 288 unique timestamps spanning 00:00 through 23:55 at five-minute intervals after sorting. Both metrics files were unsorted. These results describe these four samples and do not establish completeness for every archive date.

All 1,152 sampled records passed the existing normalization functions after an in-memory field adapter. This checks structural compatibility. Archive/live semantic equivalence still requires an overlap comparison before production import, particularly the timezone and observation meaning of the timezone-free `create_time` field.

## Kline shape

The sampled CSV has twelve fields in this order, matching the USD-M REST kline layout:

```text
open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
```

The samples use Unix milliseconds. Convert open/close time and trade count to validated integers. Keep prices and volumes as decimal strings. The adapter can then call `normalize_kline`. Its exclusive-end join key is open time plus 300,000 milliseconds. Preserve the ignored final field in the original archive even though it is not stored in the normalized candle table.

The repository separately notes a microsecond change for spot data. Dataset identity and timestamp units must therefore be validated explicitly when adding any other archive type.

## OI metrics shape

The sampled CSV fields are:

```text
create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio
```

| Archive field | Proposed normalized destination | Rule |
|---|---|---|
| create_time | source_timestamp_ms | Sample strings resemble `2026-11-05 00:10:00`. The research adapter interpreted them as UTC. Confirm with overlapping live observations before importing. |
| symbol | symbol | Validate against the requested archive contract. |
| sum_open_interest | oi_quantity | Preserve native decimal text and units. |
| sum_open_interest_value | oi_notional_quote | Preserve the reported value without repricing. |
| Four ratio columns | Future metrics table if needed | Retain in the raw CSV meanwhile. Do not overload OI fields. |
| No CMC supply field | cmc_supply = NULL | Missing supply must remain missing. |

Sorting reveals the expected five-minute sequence in these samples. Missing rows, duplicate timestamps and conflicting duplicate values must still be checked on each future import.

## Proposed integration boundary

1. Download archive ZIP and CHECKSUM into a dedicated immutable archive area. Record URL, retrieval time, checksum, market type, dataset, interval and covered dates. Preserve revisions by checksum rather than replacing earlier source bytes.
2. Introduce an archive adapter that validates CSV headers and timestamp units and emits the existing normalized row shapes. Keep the live request path independently executable.
3. Extend source provenance through a schema migration. The current `raw_files` loader accepts named JSON lists and assumes retrieval time can be parsed from those names. A ZIP/CSV cannot simply be dropped there.
4. Reuse normalization and natural-key deduplication. Compare numeric values with Decimal when reconciling overlap, because archive decimal formatting can have extra trailing zeros. Equal observations deduplicate. Conflicting observations require an explicit resolution policy and recorded evidence before any overwrite.
5. Retain multiple source references where both archive and live data corroborate a record. The current single `raw_file_id` records only the first accepted source and is insufficient for full multi-source lineage.
6. Report coverage before and after import over a fixed requested range. Keep unrecoverable gaps visible. Archive corrections and empty/missing source responses require explicit status rather than silently counting a window as complete.

Live collection remains the next implementation priority. Archives can later seed older history and repair gaps while live collection continues to append recent observations.

## Verified sample URLs and checksums

- [BTCUSDT metrics daily sample](https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-11-05.zip)
  SHA-256 `e6f82a426f535b4b2f91e799dde6ddd721fd5cd4876ebbe63ae41bffb0919a9f`

- [BTCUSDT klines daily sample](https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-11-05.zip)
  SHA-256 `43650f8c98cf1ac74bea72a5c4799a22b1e448d394f0760df111d60b21ce8f03`

- [1000PEPEUSDT metrics daily sample](https://data.binance.vision/data/futures/um/daily/metrics/1000PEPEUSDT/1000PEPEUSDT-metrics-2026-11-05.zip)
  SHA-256 `ca15749db2cf735ca8723e7741040750d799d0cb0f66ff3408eefffd1602df55`

- [1000PEPEUSDT klines daily sample](https://data.binance.vision/data/futures/um/daily/klines/1000PEPEUSDT/5m/1000PEPEUSDT-5m-2026-11-05.zip)
  SHA-256 `73bdf15590697a7b3e30657b9ae8a2b3930118963090ca14cf60123937db7ded`
