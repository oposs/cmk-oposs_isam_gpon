#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""Metric translations for the Nokia ISAM GPON plugin rename.

The v1 check was registered as ``nokia_isam_gpon`` and emitted metrics
prefixed with ``isam_``.  The v2 plugin is ``oposs_isam_gpon`` and uses
the ``oposs_isam_`` prefix.  This translation lets Checkmk carry over
existing RRD data so historical graphs remain intact.

IMPORTANT: ``check_commands`` MUST reference the *new* check name
(``oposs_isam_gpon``), not the legacy ``nokia_isam_gpon``. Checkmk's
translation lookup
(``cmk/gui/graphing/_translated_metrics.py``,
``lookup_metric_translations_for_check_command``) is an exact dict-key
match on the live service's current check command. After the legacy
plugin is uninstalled no service has the legacy command attached, so an
entry keyed on it would never fire and the legacy ``isam_*.rrd`` files
in the per-service directory would stay orphaned.

Not migrated: the legacy ``isam_*Bytes`` and ``isam_*Util`` metrics.
Both were sourced from PM current-interval counters that reset every
15 minutes but were stored as gauges, so the historical values are
saw-tooth noise rather than real traffic. Their RRD files are left
orphaned intentionally; the new ``…BytesRate`` (B/s) and recomputed
``…Util`` (%) series start fresh.
"""

from cmk.graphing.v1 import translations

translation_oposs_isam_gpon = translations.Translation(
    name="oposs_isam_gpon",
    check_commands=[translations.PassiveCheck("oposs_isam_gpon")],
    translations={
        "isam_bias_current": translations.RenameTo("oposs_isam_bias_current"),
        "isam_txpower": translations.RenameTo("oposs_isam_txpower"),
        "isam_rxpower": translations.RenameTo("oposs_isam_rxpower"),
        "isam_voltage": translations.RenameTo("oposs_isam_voltage"),
        "isam_temperature": translations.RenameTo("oposs_isam_temperature"),
        "isam_NumActiveOnts": translations.RenameTo("oposs_isam_NumActiveOnts"),
        "isam_RxDBACongestionTime": translations.RenameTo("oposs_isam_RxDBACongestionTime"),
    },
)
