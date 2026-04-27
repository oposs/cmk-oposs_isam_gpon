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
        "isam_TxUcastBytes": translations.RenameTo("oposs_isam_TxUcastBytes"),
        "isam_TxMcastBytes": translations.RenameTo("oposs_isam_TxMcastBytes"),
        "isam_TxBcastBytes": translations.RenameTo("oposs_isam_TxBcastBytes"),
        "isam_TxTotalBytes": translations.RenameTo("oposs_isam_TxTotalBytes"),
        "isam_RxTotalBytes": translations.RenameTo("oposs_isam_RxTotalBytes"),
        "isam_TxUcastDropBytes": translations.RenameTo("oposs_isam_TxUcastDropBytes"),
        "isam_RxTotalDropBytes": translations.RenameTo("oposs_isam_RxTotalDropBytes"),
        "isam_TxMcastDropBytes": translations.RenameTo("oposs_isam_TxMcastDropBytes"),
        "isam_TxBcastDropBytes": translations.RenameTo("oposs_isam_TxBcastDropBytes"),
        "isam_TxTotalDropBytes": translations.RenameTo("oposs_isam_TxTotalDropBytes"),
        "isam_TxUcastUtil": translations.RenameTo("oposs_isam_TxUcastUtil"),
        "isam_TxMcastUtil": translations.RenameTo("oposs_isam_TxMcastUtil"),
        "isam_TxBcastUtil": translations.RenameTo("oposs_isam_TxBcastUtil"),
        "isam_TxTotalUtil": translations.RenameTo("oposs_isam_TxTotalUtil"),
        "isam_RxTotalUtil": translations.RenameTo("oposs_isam_RxTotalUtil"),
        "isam_NumActiveOnts": translations.RenameTo("oposs_isam_NumActiveOnts"),
        "isam_RxDBACongestionTime": translations.RenameTo("oposs_isam_RxDBACongestionTime"),
    },
)
