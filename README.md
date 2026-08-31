# Nokia ISAM GPON Checkmk Plugin

Checkmk SNMP plugin for monitoring Nokia ISAM GPON equipment.

## Features

| Check | Services | Data |
|-------|----------|------|
| Linecard | Per-slot availability | Planned/actual type, serial, availability state |
| GPON | Per-port status | Admin/oper status, SFP optics, traffic stats |

### GPON Metrics

- **SFP optics:** Tx/Rx power (dBm), bias current (A), voltage (V), temperature (C)
- **Traffic:** Tx/Rx bytes (unicast, multicast, broadcast, total, drops)
- **Utilization:** Tx/Rx utilization percentages
- **Other:** Active ONTs, DBA congestion time

## SNMP Detection

Detects Nokia ISAM devices where sysDescr contains `NOKIA ISAM`.

## Polling and Caching

The plugin provides two SNMP sections:

| Section | Contents | Cost per host | Cache it? |
|---------|----------|---------------|-----------|
| `oposs_isam_gpon` | PM traffic counters | ~1 s | **no** — must be fetched every run |
| `oposs_isam_gpon_info` | SFP optics, descriptions, interface status | ~11 s | **yes**, at 300 s |

The optics table is read from the SFP hardware on demand — about 23 ms per
row against 5.8 ms for the counters — so it dominates the host's SNMP fetch.
Splitting it out is what makes a short check interval affordable. Measured on
a 16-port OLT, per 300 s of wall time:

| Setup | SNMP per 300 s |
|-------|----------------|
| 300 s check interval (default) | 18 s |
| 60 s check interval, no caching | 68 s (3.8x) |
| 60 s check interval, `_info` cached at 300 s | 22 s (1.2x) |

The plugin works unchanged at the default interval. A 60 s interval mainly
improves how faithfully bursty traffic is represented, because the counters
are then differenced within one PM window instead of being read once per
window.

To enable it, two rules in Checkmk:

1. **Setup → Service monitoring rules → Service checks → "Normal check
   interval for service checks"** — set 1 minute for these hosts. Scoping the
   rule to the service `Check_MK$` is enough; that is the active check which
   drives the SNMP fetch.
2. **Setup → Agents → SNMP rules → "Fetch intervals for SNMP sections"** — add
   `oposs_isam_gpon_info` (and `oposs_isam_linecard`) at 300 s. Do **not** add
   `oposs_isam_gpon`. The internal name of this ruleset is still
   `snmp_check_interval`.

Install the package and activate before adding the rules, so the
`oposs_isam_gpon_info` section exists when it is referenced. Setting the
interval while an older, unsplit version is active is the 3.8x case.

## Upgrading to 0.5.0

The traffic rate and utilization metrics were renamed and **no translation
maps the old names onto the new ones**, so those graphs start empty. This is
deliberate: every value they held was written by 0.2.0 through 0.4.0, whose
rate conversion assumed a 900 s PM window where the device uses 300 s. That
produced spikes far above the GPON line rate and under-reported steady
traffic by roughly 6x, and filtering the spikes would leave a plausible-
looking graph that is still wrong by that factor.

The SFP optics metrics, active-ONT count and DBA congestion time keep their
names and their history.

## Installation

### MKP Package (recommended)

Download the latest `.mkp` file from the
[Releases](https://github.com/oposs/cmk-oposs_isam_gpon/releases) page and
install it:

```bash
mkp install oposs_isam_gpon-<version>.mkp
```

### Manual Installation

Copy the plugin files into your Checkmk site:

```
local/lib/python3/cmk_addons/plugins/oposs_isam_gpon/
├── agent_based/
│   └── oposs_isam_gpon.py
├── checkman/
│   └── oposs_isam_gpon
└── graphing/
    ├── isam_gpon.py
    └── translations.py
```

## License

GNU General Public License v3 - OETIKER+PARTNER AG. See [LICENSE](LICENSE).

v3 rather than v2 because `SLOT_TABLE` and `PORT_TABLE_NT` in
`agent_based/oposs_isam_gpon.py` are taken from LibreNMS, which is GPL v3;
see the commit link in the source. GPL v3 code cannot be relicensed to v2.
