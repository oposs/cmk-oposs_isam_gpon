# cmk-oposs_isam_gpon

Checkmk SNMP plugin for Nokia ISAM GPON equipment.
Migrated from oegig-plugins to Checkmk 2.3.x v2 API.

## Components

- `local/lib/python3/cmk_addons/plugins/oposs_isam_gpon/agent_based/oposs_isam_gpon.py` -- SNMP sections + check plugins (Linecard + GPON)
- `local/lib/python3/cmk_addons/plugins/oposs_isam_gpon/graphing/isam_gpon.py` -- metric, graph definitions
- `.mkp-builder.ini` -- MKP packaging config
- `.github/workflows/release.yml` -- automated release workflow

## Architecture

- Two SNMP sections with shared detection: `contains(".1.3.6.1.2.1.1.1.0", "NOKIA ISAM")`
- **Linecard** (`oposs_isam_linecard`): 1 SNMP tree, per-slot discovery, availability-based state
- **GPON** (`oposs_isam_gpon`): 7 SNMP trees, per-port discovery, admin/oper status comparison
- GPON parse merges data from multiple trees using different OID-to-key mappings:
  - Enterprise inventory: `id2gpon()` (cardId.port notation)
  - PM/description/IF tables: `id2name()` (bit-packed interface index, PON entries only)
- Discovery filters: only `lt:*` keys (line card ports)
- Metric prefix: `oposs_isam_`
- GPON yields SFP optics metrics (conditionally available) + traffic byte/utilization metrics

## OID-to-Key Mapping

The Nokia ISAM uses different index schemes across MIBs:
- Enterprise GPON MIB: composite OID `cardId.port` -> `id2gpon()` -> `lt:1/1/{slot}/{port}`
- PM/Standard MIBs: bit-packed integer -> `id2name()` -> `lt:1/1/{slot}/{pon}` (PON type only)
