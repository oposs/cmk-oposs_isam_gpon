# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### New

### Changed

### Fixed
- GPON traffic graphs no longer show periodic gaps under 5-minute
  polling. The byte-rate conversion in 0.2.0 dropped any poll whose
  delta went negative, which is exactly the poll that straddles a
  15-minute PM counter reset (`:00/:15/:30/:45`) — so roughly one in
  three samples produced no metric and left a hole in the graph. The
  reset sample is now kept: its post-reset bytes are divided by the
  time since the boundary (`now % 900`), which yields the correct rate
  with no gap and no dip. Only the byte integral over the reset
  interval is marginally undercounted.

## 0.2.0 - 2026-05-28
### Changed
- Traffic byte metrics are now emitted as **bytes per second** rates
  instead of raw counters, and renamed with a `Rate` suffix
  (`oposs_isam_Tx*BytesRate`, `oposs_isam_Rx*BytesRate`,
  `oposs_isam_*DropBytesRate`). Graphing unit changed from `B` to `B/s`.
- Utilization metrics (`oposs_isam_*Util`) are now computed by the check
  from the byte rate divided by the GPON line rate (2.488 Gbps
  downstream / 1.244 Gbps upstream per ITU-T G.984). The corresponding
  SNMP OIDs (`gponOltSidePonUtil…Util` columns 2/4/5/6/7) are no longer
  fetched, reducing per-check SNMP traffic.

### Fixed
- GPON traffic byte values now reflect real throughput. They were
  sourced from `gponOltSidePonUtilPmCurrentIntervalTable`, a Nokia ISAM
  Performance Monitoring table whose counters reset at the start of
  every 15-minute PM window. Emitting them as plain gauges produced the
  characteristic saw-tooth pattern in the graphs (climb to ~400 MB,
  snap back to 0, repeat) that did not represent actual link traffic.
  The check now keeps the previous `(timestamp, value)` per metric in
  the value store, emits `(now - prev) / Δt` as the per-second rate,
  and drops the one sample per interval that shows a negative delta
  (the rollover). The same fix removes the equivalent distortion from
  the device-reported `*Util` percentages, which are now derived from
  the new rates.

## 0.1.1 - 2026-04-27
### Fixed
- Metric translation for the legacy `nokia_isam_gpon` history is now keyed
  on the new `oposs_isam_gpon` check command so it actually fires.
  Previously it was keyed on the now-uninstalled legacy command and
  Checkmk's translation lookup (an exact match on the live service's
  current check command) silently missed it — leaving the legacy
  `isam_*.rrd` files orphaned in the per-service directories. After
  upgrading and reloading (`cmk -R` / `omd restart apache`), graphs of
  the new `oposs_isam_*` metrics on hosts that previously ran the legacy
  `nokia_isam_gpon` check will show one continuous line spanning the
  pre- and post-upgrade history (assuming the service name was unchanged
  across the rename, which it is by default).

## 0.1.0 - 2026-03-04
### New
- Initial migration from oegig-plugins to Checkmk 2.3.x v2 API
- Linecard check: monitors slot availability and status
- GPON check: monitors port status, SFP optics, and traffic statistics
- Graphing definitions for SFP metrics, traffic bytes, and utilization
- Metric names prefixed with `oposs_isam_` for namespace isolation
- MKP packaging via oposs/mkp-builder GitHub Action


