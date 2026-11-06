# cmk-oposs_isam_gpon

Checkmk SNMP plugin for Nokia ISAM GPON equipment.
Migrated from oegig-plugins to Checkmk 2.3.x v2 API.

## Components

- `local/lib/python3/cmk_addons/plugins/oposs_isam_gpon/agent_based/oposs_isam_gpon.py` -- SNMP sections + check plugins (Linecard + GPON)
- `local/lib/python3/cmk_addons/plugins/oposs_isam_gpon/graphing/isam_gpon.py` -- metric, graph definitions
- `.mkp-builder.ini` -- MKP packaging config
- `.github/workflows/` -- repo-infra callers: `ci.yml` (ruff, pytest, MKP build), `changelog.yml`, `release-pr.yml`, `release-build.yml`, `release-publish.yml`
- `tests/` -- pytest against the real Checkmk 2.3.0 API (`tests/conftest.py` fetches it into `.cmk-api/`)

## Architecture

- Three SNMP sections with shared detection: `contains(".1.3.6.1.2.1.1.1.0", "NOKIA ISAM")`
- **Linecard** (`oposs_isam_linecard`): 1 SNMP tree, per-slot discovery, availability-based state
- **GPON** (check `oposs_isam_gpon`): two sections, `oposs_isam_gpon` (2 PM trees, fetched every run) and `oposs_isam_gpon_info` (3 trees: optics, descriptions, IF status; cacheable), per-port discovery, admin/oper status comparison
- GPON parse merges data from multiple trees using different OID-to-key mappings:
  - Enterprise inventory: `_id2gpon()` (cardId.port notation)
  - PM/description/IF tables: `_id2name()` (bit-packed interface index, PON entries only)
- Discovery filters: only `lt:*` keys (line card ports)
- Metric prefix: `oposs_isam_`
- GPON yields SFP optics metrics (conditionally available) + traffic byte/utilization metrics

## OID-to-Key Mapping

The Nokia ISAM uses different index schemes across MIBs:
- Enterprise GPON MIB: composite OID `cardId.port` -> `_id2gpon()` -> `lt:1/1/{slot}/{port}`
- PM/Standard MIBs: bit-packed integer -> `_id2name()` -> `lt:1/1/{slot}/{pon}` (PON type only)
