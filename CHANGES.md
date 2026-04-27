# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### New

### Changed

### Fixed

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


