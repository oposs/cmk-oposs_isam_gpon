#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""
Graphing definitions for Nokia ISAM GPON monitoring.
Defines metrics, graphs, and perfometers for SFP optics and traffic stats.
"""

from cmk.graphing.v1 import Title
from cmk.graphing.v1.metrics import (
    Color,
    DecimalNotation,
    IECNotation,
    Metric,
    Unit,
)
from cmk.graphing.v1.graphs import Graph

# Units
unit_amperes = Unit(DecimalNotation("A"))
unit_dbm = Unit(DecimalNotation("dBm"))
unit_volts = Unit(DecimalNotation("V"))
unit_celsius = Unit(DecimalNotation("\u00b0C"))
unit_percent = Unit(DecimalNotation("%"))
unit_bytes_per_sec = Unit(IECNotation("B/s"))
unit_count = Unit(DecimalNotation(""))

# ---------------------------------------------------------------------------
# SFP optics metrics
# ---------------------------------------------------------------------------

metric_oposs_isam_bias_current = Metric(
    name="oposs_isam_bias_current",
    title=Title("Bias Current"),
    unit=unit_amperes,
    color=Color.ORANGE,
)

metric_oposs_isam_txpower = Metric(
    name="oposs_isam_txpower",
    title=Title("Tx Power"),
    unit=unit_dbm,
    color=Color.BLUE,
)

metric_oposs_isam_rxpower = Metric(
    name="oposs_isam_rxpower",
    title=Title("Rx Power"),
    unit=unit_dbm,
    color=Color.GREEN,
)

metric_oposs_isam_voltage = Metric(
    name="oposs_isam_voltage",
    title=Title("Supply Voltage"),
    unit=unit_volts,
    color=Color.PURPLE,
)

metric_oposs_isam_temperature = Metric(
    name="oposs_isam_temperature",
    title=Title("SFP Temperature"),
    unit=unit_celsius,
    color=Color.RED,
)

# ---------------------------------------------------------------------------
# Traffic byte-rate metrics (bytes per second, derived from PM interval
# counters that reset every 15 min — see oposs_isam_gpon.py)
# ---------------------------------------------------------------------------

metric_oposs_isam_TxUcastBytesRate = Metric(
    name="oposs_isam_TxUcastBytesRate",
    title=Title("Tx Unicast"),
    unit=unit_bytes_per_sec,
    color=Color.BLUE,
)

metric_oposs_isam_TxMcastBytesRate = Metric(
    name="oposs_isam_TxMcastBytesRate",
    title=Title("Tx Multicast"),
    unit=unit_bytes_per_sec,
    color=Color.GREEN,
)

metric_oposs_isam_TxBcastBytesRate = Metric(
    name="oposs_isam_TxBcastBytesRate",
    title=Title("Tx Broadcast"),
    unit=unit_bytes_per_sec,
    color=Color.ORANGE,
)

metric_oposs_isam_TxTotalBytesRate = Metric(
    name="oposs_isam_TxTotalBytesRate",
    title=Title("Tx Total"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_BLUE,
)

metric_oposs_isam_RxTotalBytesRate = Metric(
    name="oposs_isam_RxTotalBytesRate",
    title=Title("Rx Total"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_GREEN,
)

metric_oposs_isam_TxUcastDropBytesRate = Metric(
    name="oposs_isam_TxUcastDropBytesRate",
    title=Title("Tx Unicast Drop"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_RED,
)

metric_oposs_isam_RxTotalDropBytesRate = Metric(
    name="oposs_isam_RxTotalDropBytesRate",
    title=Title("Rx Total Drop"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_ORANGE,
)

metric_oposs_isam_TxMcastDropBytesRate = Metric(
    name="oposs_isam_TxMcastDropBytesRate",
    title=Title("Tx Multicast Drop"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_YELLOW,
)

metric_oposs_isam_TxBcastDropBytesRate = Metric(
    name="oposs_isam_TxBcastDropBytesRate",
    title=Title("Tx Broadcast Drop"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_PINK,
)

metric_oposs_isam_TxTotalDropBytesRate = Metric(
    name="oposs_isam_TxTotalDropBytesRate",
    title=Title("Tx Total Drop"),
    unit=unit_bytes_per_sec,
    color=Color.DARK_CYAN,
)

# ---------------------------------------------------------------------------
# Utilization metrics
# ---------------------------------------------------------------------------

metric_oposs_isam_TxUcastUtil = Metric(
    name="oposs_isam_TxUcastUtil",
    title=Title("Tx Unicast Utilization"),
    unit=unit_percent,
    color=Color.BLUE,
)

metric_oposs_isam_TxMcastUtil = Metric(
    name="oposs_isam_TxMcastUtil",
    title=Title("Tx Multicast Utilization"),
    unit=unit_percent,
    color=Color.GREEN,
)

metric_oposs_isam_TxBcastUtil = Metric(
    name="oposs_isam_TxBcastUtil",
    title=Title("Tx Broadcast Utilization"),
    unit=unit_percent,
    color=Color.ORANGE,
)

metric_oposs_isam_TxTotalUtil = Metric(
    name="oposs_isam_TxTotalUtil",
    title=Title("Tx Total Utilization"),
    unit=unit_percent,
    color=Color.DARK_BLUE,
)

metric_oposs_isam_RxTotalUtil = Metric(
    name="oposs_isam_RxTotalUtil",
    title=Title("Rx Total Utilization"),
    unit=unit_percent,
    color=Color.DARK_GREEN,
)

# ---------------------------------------------------------------------------
# Other metrics
# ---------------------------------------------------------------------------

metric_oposs_isam_NumActiveOnts = Metric(
    name="oposs_isam_NumActiveOnts",
    title=Title("Active ONTs"),
    unit=unit_count,
    color=Color.CYAN,
)

metric_oposs_isam_RxDBACongestionTime = Metric(
    name="oposs_isam_RxDBACongestionTime",
    title=Title("DBA Congestion Time"),
    unit=unit_percent,
    color=Color.YELLOW,
)

# ---------------------------------------------------------------------------
# Graphs
# ---------------------------------------------------------------------------

graph_oposs_isam_power = Graph(
    name="oposs_isam_power",
    title=Title("ISAM SFP Power"),
    simple_lines=[
        "oposs_isam_txpower",
        "oposs_isam_rxpower",
    ],
)

graph_oposs_isam_traffic = Graph(
    name="oposs_isam_traffic",
    title=Title("ISAM GPON Traffic"),
    simple_lines=[
        "oposs_isam_TxTotalBytesRate",
        "oposs_isam_RxTotalBytesRate",
    ],
)

graph_oposs_isam_traffic_drops = Graph(
    name="oposs_isam_traffic_drops",
    title=Title("ISAM GPON Traffic Drops"),
    simple_lines=[
        "oposs_isam_TxTotalDropBytesRate",
        "oposs_isam_RxTotalDropBytesRate",
    ],
)

graph_oposs_isam_utilization = Graph(
    name="oposs_isam_utilization",
    title=Title("ISAM GPON Utilization"),
    simple_lines=[
        "oposs_isam_TxTotalUtil",
        "oposs_isam_RxTotalUtil",
    ],
)
