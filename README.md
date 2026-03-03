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
└── graphing/
    └── isam_gpon.py
```

## License

MIT - OETIKER+PARTNER AG
