# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### New

### Changed

### Fixed

## 0.3.0 - 2026-08-30
### Changed
- GPON byte-rate conversion now adapts to the poll cadence. When polls are
  frequent relative to the 5-minute PM window (e.g. a 60 s check interval)
  consecutive reads are differenced, which yields disjoint intervals so
  bursts are neither double counted nor smeared. When the counter was
  cleared in between, the new window's bytes are attributed to the whole
  span — an undercount bounded by the unmeasured tail, never an overshoot,
  because the divisor is always the real poll interval. At a poll interval
  close to the window length differencing is meaningless (both reads sit at
  almost the same point in the window), so the counter is instead read for
  what it is — bytes since the window boundary — and divided by the time
  elapsed since that boundary.
- Whether a counter clear falls between two readings is decided from the
  reading **timestamps** against the known 5-minute cycle boundaries, not
  from whether the value went backwards. Comparing values alone silently
  differences across a clear whenever a quiet cycle is followed by a burst
  right after the clear — the readings then still increase. Measured on the
  device model that case under-reported by 3x (0.83 MB/s for true
  2.50 MB/s); it is now exact. The value is still consulted inside the
  late-clear window, where the device has not cleared yet and the timestamps
  alone would be misleading.
- Measured byte-integral accuracy against the device model, as
  stored bytes / true bytes:

  | traffic shape         | 0.2.1 | this, 300 s | this, 60 s |
  |-----------------------|-------|-------------|------------|
  | steady                | 0.88  | 0.88        | 0.90       |
  | burst in 1st minute   | 2.00  | 1.99        | 0.88       |
  | burst in last minute  | 0.11  | 0.11        | 0.53       |
  | burst in the middle   | 0.70  | 0.70        | 1.00       |

  At a 60 s check interval the shape-dependent error collapses from an
  18x spread to about 2x, and no samples are dropped at all. The remaining
  loss is the tail between the last poll of a window and the counter clear;
  only the PM interval-history table could recover it.

### Fixed
- GPON traffic graphs no longer show impossible spikes far above the GPON
  line rate. Two facts broke the previous conversion. First, the PM
  current-interval window is **300 s, not 900 s** — verified on the device
  by observing a counter clear at a 5-minute boundary that is not a
  15-minute boundary, and by the interval-history table holding 288
  five-minute buckets (24 h). Second, the device clears the counter
  **1–3 s after** the wall-clock boundary, so a poll landing in that gap
  reads the *complete previous window* while `now % 900` reads as a
  fraction of a second. Dividing a full window by that produced rates of
  up to 3600x the line rate. Across 151 monitored ISAM hosts this affected
  141 hosts with 10,733 impossible samples in 40 days.
- GPON byte rates were also systematically **too low** between spikes.
  With a 300 s window and 300 s polling, consecutive polls sit at nearly
  the same point in the window, so their difference was noise rather than
  traffic. In simulation against the measured device behaviour the old
  code reported a median of 0.30 MB/s for steady 2.00 MB/s traffic; the
  new code reports 1.97 MB/s.
- Rates above the physical GPON line rate (2.488 Gbps downstream /
  1.244 Gbps upstream) are now discarded as impossible, and samples taken
  within 30 s of a window boundary are skipped rather than guessed at.
  Measured on the live site, the poll phase drifts through the 5-minute
  window about once an hour, so this drops roughly 1 sample in 10, spread
  evenly rather than in runs.

## 0.2.1 - 2026-06-01
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


