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

Not migrated, deliberately, in two generations:

* The legacy ``isam_*Bytes`` / ``isam_*Util`` metrics were sourced from
  PM current-interval counters but stored as gauges, so their history is
  saw-tooth noise rather than traffic.
* The ``oposs_isam_*BytesRate`` / ``oposs_isam_*Util`` metrics written by
  0.2.0 through 0.4.0 are also unusable: that rate conversion assumed a
  900 s PM window where the device uses 300 s, which produced spikes of
  up to 3600x the line rate and under-reported steady traffic by roughly
  6x. 0.5.0 renamed them to snake_case (``oposs_isam_tx_total_bytes_rate``
  and friends) precisely so the new series start empty.

No entry below maps either generation onto a current metric name, and
none must be added: a ``RenameTo`` would pull that bad history straight
into the new graphs, and the translation API has no way to filter it
(it offers only ``RenameTo``, ``ScaleBy`` and ``RenameToAndScaleBy``).
The orphaned data ages out of the RRDs on its own.

Only genuinely good series are carried over: the SFP optics readings and
the ONT counters, which no version got wrong.
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
