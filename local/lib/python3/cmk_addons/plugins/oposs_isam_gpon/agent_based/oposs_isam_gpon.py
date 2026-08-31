#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v3

"""
SNMP check plugin for Nokia ISAM GPON equipment.
Monitors line card availability and GPON port status including
SFP optics and traffic statistics.
"""

import time

from cmk.agent_based.v2 import (
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    Metric,
    OIDBytes,
    OIDEnd,
    Result,
    SNMPSection,
    SNMPTree,
    Service,
    State,
    contains,
    get_value_store,
)


# GPON line rates per ITU-T G.984 (bits per second).
# OLT Tx = downstream toward ONTs, OLT Rx = upstream from ONTs.
GPON_DOWNSTREAM_BPS = 2_488_320_000
GPON_UPSTREAM_BPS = 1_244_160_000

# Measured on the device: the PM current-interval window is 300 s (the
# interval-history table holds 288 entries = 24 h of 5-minute buckets), and the
# counter is cleared 1-3 s AFTER the wall-clock boundary.
_PM_WINDOW = 300

# Never divide by an elapsed time close to zero. Just after a boundary the
# counter may still hold the complete previous window while the elapsed time
# reads as a fraction of a second, which produced rates up to 3600x the line
# rate. Samples taken within this many seconds of a boundary are dropped.
# The poll phase drifts through the window about once an hour, so this costs
# roughly 1 sample in 10 and never a run of them. It also bounds the
# underestimate near the boundary: the device clears up to 3 s late, so the
# worst case is 3/30 = 10% low.
_MIN_PHASE = 30

# Two consecutive polls are only worth differencing when they are frequent
# relative to the PM window. At a poll interval close to the window length the
# two reads sit at almost the same point in the window, so their difference is
# noise whose sign is random - that was the 0.2.x failure mode.
_DIFF_MAX_DT = _PM_WINDOW * 0.8

# Never difference two polls that are almost simultaneous (a manual reschedule,
# a core restart). The line rate cap below is the second line of defence.
_MIN_DT = 10

# The device clears the counter 1-3 s AFTER the wall-clock boundary, and its
# clock is not ours. Inside this many seconds past a boundary a reading may
# still belong to the previous cycle, so there the value decides; outside it
# the timestamps decide. See _interval_rate().
_CLEAR_GRACE = 10

# Physical ceilings in bytes/s, used as a last-resort sanity net.
_MAX_TX_BYTES_PER_S = GPON_DOWNSTREAM_BPS / 8.0
_MAX_RX_BYTES_PER_S = GPON_UPSTREAM_BPS / 8.0

# Byte counters fetched from gponOltSidePonUtilPmCurrentIntervalTable.
# These are PM counters that the device clears at the start of every 5-minute
# window, so the check turns them into bytes/sec rates via _interval_rate().
_BYTE_COUNTER_FIELDS = [
    "TxUcastBytes", "TxMcastBytes", "TxBcastBytes",
    "TxTotalBytes", "RxTotalBytes",
    "TxUcastDropBytes", "RxTotalDropBytes",
    "TxMcastDropBytes", "TxBcastDropBytes", "TxTotalDropBytes",
]

# Metric name per byte counter. Deliberately NOT derived from the field name:
# these were renamed in 0.5.0 to orphan the RRD history written by 0.2.0-0.4.0,
# whose rate conversion was wrong (see CHANGES.md). No translation maps the old
# names onto these, so the series start empty. Keep them explicit so a field
# rename cannot silently resurrect an old metric name.
_RATE_METRIC = {
    "TxUcastBytes": "oposs_isam_tx_ucast_bytes_rate",
    "TxMcastBytes": "oposs_isam_tx_mcast_bytes_rate",
    "TxBcastBytes": "oposs_isam_tx_bcast_bytes_rate",
    "TxTotalBytes": "oposs_isam_tx_total_bytes_rate",
    "RxTotalBytes": "oposs_isam_rx_total_bytes_rate",
    "TxUcastDropBytes": "oposs_isam_tx_ucast_drop_bytes_rate",
    "RxTotalDropBytes": "oposs_isam_rx_total_drop_bytes_rate",
    "TxMcastDropBytes": "oposs_isam_tx_mcast_drop_bytes_rate",
    "TxBcastDropBytes": "oposs_isam_tx_bcast_drop_bytes_rate",
    "TxTotalDropBytes": "oposs_isam_tx_total_drop_bytes_rate",
}

# Utilization metrics derived from the rates above: (metric, counter, line rate).
_UTIL_DERIVATIONS = [
    ("oposs_isam_tx_ucast_util", "TxUcastBytes", GPON_DOWNSTREAM_BPS),
    ("oposs_isam_tx_mcast_util", "TxMcastBytes", GPON_DOWNSTREAM_BPS),
    ("oposs_isam_tx_bcast_util", "TxBcastBytes", GPON_DOWNSTREAM_BPS),
    ("oposs_isam_tx_total_util", "TxTotalBytes", GPON_DOWNSTREAM_BPS),
    ("oposs_isam_rx_total_util", "RxTotalBytes", GPON_UPSTREAM_BPS),
]

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

# https://git.furworks.de/opensourcemirror/LibreNMS/commit/d60a0da7deae2f433b8cc1d22c79097662a1cf8c
SLOT_TABLE = {
    "4352": "acu:1/1",
    "4353": "nt-a:",
    "4354": "nt-b:",
    "4355": "lt:1/1/1",
    "4356": "lt:1/1/2",
    "4357": "lt:1/1/3",
    "4358": "lt:1/1/4",
    "4359": "lt:1/1/5",
    "4360": "lt:1/1/6",
    "4361": "lt:1/1/7",
    "4362": "lt:1/1/8",
}

PORT_TABLE_NT = {
    "257": "xfp:1",
    "258": "xfp:2",
    "259": "xfp:3",
    "260": "xfp:4",
}

OPER_STATUS = {
    "1": "Up",
    "2": "Down",
    "3": "Testing",
    "4": "Unknown",
    "5": "Dormant",
    "6": "Not Present",
    "7": "Lower Layer Down",
}

ADMIN_STATUS = {
    "1": "Up",
    "2": "Down",
    "3": "Testing",
}

AVAILABILITY = {
    "1": "Available",
    "2": "In Test",
    "3": "Failed",
    "4": "Power Off",
    "5": "Not Installed",
    "6": "Off-Line",
    "7": "Dependency",
}


# ---------------------------------------------------------------------------
# OID-to-key mapping helpers
# ---------------------------------------------------------------------------

def _id2card(idx):
    """Map slot OID end to human-readable card name."""
    return SLOT_TABLE.get(idx, idx)


def _id2gpon(idx):
    """Map enterprise GPON OID end (cardId.port) to interface path."""
    card_id, port = idx.split(".")
    return _id2card(card_id) + "/" + PORT_TABLE_NT.get(port, "%02d" % int(port))


def _id2name(idx):
    """Decode bit-packed interface index to path. Returns key only for PON type."""
    idx = int(idx)
    itype = (idx & ((1 << 25) - 1)) >> 21
    slot = "%d" % (((idx & ((1 << 30) - 1)) >> 25) - 1)
    pon = "%02d" % (((idx & ((1 << 21) - 1)) >> 16) + 1)
    if itype == 0b1101:  # PON
        return "lt:1/1/" + slot + "/" + pon
    return None


# ---------------------------------------------------------------------------
# Linecard section + check
# ---------------------------------------------------------------------------

_LINECARD_FIELDS = [
    "serial", "slotid", "plannedtype", "actualtype", "slotpower",
    "adminstatus", "operstatus", "operror", "availability",
    "containerid", "containeroffset",
]


def _parse_linecard(string_table):
    """Parse line card inventory from 1 SNMP tree."""
    result = {}
    for row in string_table[0]:
        oid = row[0]
        dic = dict(zip(_LINECARD_FIELDS, row[1:]))
        key = _id2card(oid)
        if key:
            result[key] = dic
    return result


def _discover_linecard(section) -> DiscoveryResult:
    for key in section:
        if key.startswith("lt:"):
            yield Service(item=key)


def _check_linecard(item, section) -> CheckResult:
    if item not in section:
        return
    dic = section[item]
    avail = dic["availability"]
    if avail == "1":  # Available
        state = State.OK
    elif avail == "5":  # Not Installed
        state = State.OK
    elif avail == "3":  # Failed
        state = State.CRIT
    else:
        state = State.WARN
    yield Result(
        state=state,
        summary="%s (%s) Status: %s" % (
            dic["actualtype"], dic["serial"], AVAILABILITY.get(avail, avail)),
    )


snmp_section_oposs_isam_linecard = SNMPSection(
    name="oposs_isam_linecard",
    detect=contains(".1.3.6.1.2.1.1.1.0", "NOKIA ISAM"),
    parse_function=_parse_linecard,
    fetch=[
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.23.3.1",
            oids=[
                OIDEnd(),
                "19",  # serial
                "1",   # slotid
                "2",   # plannedtype
                "3",   # actualtype
                "4",   # slotpower
                "5",   # adminstatus
                "6",   # operstatus
                "7",   # operror
                "8",   # availability
                "11",  # containerid
                "12",  # containeroffset
            ],
        ),
    ],
)

check_plugin_oposs_isam_linecard = CheckPlugin(
    name="oposs_isam_linecard",
    sections=["oposs_isam_linecard"],
    service_name="Linecard %s",
    discovery_function=_discover_linecard,
    check_function=_check_linecard,
)


# ---------------------------------------------------------------------------
# GPON section + check
# ---------------------------------------------------------------------------

def _parse_bitmap_block(result, rows, fields, conv_type):
    """Parse a bitmap-indexed SNMP block and merge into result dict."""
    for row in rows:
        oid = row[0]
        key = _id2name(oid)
        if not key:
            continue
        dic = dict(zip(fields, row[1:]))
        if conv_type == "8bytes":
            for field in list(dic):
                val = dic[field]
                if isinstance(val, list) and len(val) == 8:
                    dic[field] = int.from_bytes(val, "big")
                else:
                    del dic[field]
        elif conv_type == "float":
            for field in dic:
                dic[field] = float(dic[field])
        result.setdefault(key, {}).update(dic)


def _interval_rate(value_store, key, now, value, max_rate):
    """Compute a per-second rate from a PM counter that clears every 5 minutes.

    The counter is the running total of the current PM window. Measured on the
    device: the window is 300 s, and the counter is cleared 1-3 s AFTER the
    wall-clock boundary, so a read inside that gap still returns the complete
    previous window.

    Two strategies, picked by how often we are polled:

    Polled well inside the window length (e.g. every 60 s) we difference
    consecutive reads. The intervals are then disjoint, so bursts are neither
    double counted nor smeared. When the counter has been cleared in between,
    the new window's bytes are attributed to the whole span: that undercounts
    by the unmeasured tail, but the divisor is always the real poll interval so
    it can never blow up. A read that lands in the late-clear gap is a bonus -
    it recovers that tail exactly.

    Polled at roughly the window length (the default 300 s) differencing is
    meaningless, because both reads sit at almost the same point in the window.
    There we fall back to reading the counter for what it is - bytes since the
    window boundary - divided by the time elapsed since that boundary, dropping
    samples too close to the boundary to be trusted. Dividing a complete window
    by a near-zero elapsed time is what produced graph spikes of up to 3600x
    the line rate.

    Anything still above the physical line rate is discarded as impossible.
    Returns None when the sample cannot be trusted.
    """
    prev = value_store.get(key)
    value_store[key] = (now, value)

    rate = None
    if prev is not None:
        prev_t, prev_v = prev
        dt = now - prev_t
        if _MIN_DT <= dt < _DIFF_MAX_DT:
            # Decide from the TIMESTAMPS whether a clear falls between the two
            # readings. Comparing the values alone is not enough: two readings
            # from different cycles can still be increasing (a quiet cycle
            # followed by a burst right after the clear), which would silently
            # difference across a clear.
            same_cycle = (prev_t // _PM_WINDOW) == (now // _PM_WINDOW)
            in_clear_gap = (now % _PM_WINDOW) < _CLEAR_GRACE
            if same_cycle or (in_clear_gap and value >= prev_v):
                # Same cycle, or the device has not cleared yet and the reading
                # still belongs to the previous cycle. The latter is a bonus: it
                # recovers the tail that is otherwise lost.
                delta = value - prev_v if value >= prev_v else value
            else:
                # A clear happened in between. Only the bytes since the clear
                # are known; attributing them to the whole span undercounts by
                # the unmeasured tail but can never overshoot.
                delta = value
            rate = delta / dt

    if rate is None:
        phase = now % _PM_WINDOW
        if phase < _MIN_PHASE:
            return None
        rate = value / phase

    if rate > max_rate:
        return None
    return rate


def _parse_gpon(string_table):
    """Parse the fast PM section: 2 SNMP trees, both under the PM table.

    This is the only GPON data that is worth fetching at a short interval, and
    it is cheap: measured on the device the PM table walks in ~1 s against the
    ~11 s of the inventory section. Keeping the two apart lets the slow half be
    cached (see the module docstring of _parse_gpon_info).
    """
    result = {}

    # Block 0: PM - NumActiveOnts, RxDBACongestionTime (float)
    _parse_bitmap_block(
        result, string_table[0],
        ["NumActiveOnts", "RxDBACongestionTime"], "float",
    )

    # Block 1: PM - byte counters (8-byte big-endian, cleared every 5-min PM
    # window — rate computation happens in the check function).
    _parse_bitmap_block(
        result, string_table[1],
        _BYTE_COUNTER_FIELDS,
        "8bytes",
    )

    return result


def _parse_gpon_info(string_table):
    """Parse the slow inventory section: 3 SNMP trees.

    SFP optics, port descriptions and interface status all change slowly, but
    the optics tree costs ~23 ms per row on the device (it reads the SFP
    hardware on demand) and dominates the whole host check. Split out so a
    "Fetch intervals for SNMP sections" rule can cache it while the PM
    counters above are fetched every check.
    """
    result = {}

    # Block 0: Enterprise GPON inventory
    gpon_fields = [
        "logicalslot", "faceplateid", "availability", "signalstatus",
        "faultstatus", "txpower", "rxpower", "biascurrent",
        "voltage", "temperature",
    ]
    for row in string_table[0]:
        oid = row[0]
        key = _id2gpon(oid)
        if key:
            result.setdefault(key, {}).update(dict(zip(gpon_fields, row[1:])))

    # Block 1: Description
    _parse_bitmap_block(result, string_table[1], ["description"], "")

    # Block 2: Standard IF admin/oper status
    _parse_bitmap_block(result, string_table[2], ["adminstatus", "operstatus"], "")

    return result


def _gpon_items(section_pm, section_info):
    """Every line-card port seen by either section, in a stable order."""
    keys = set()
    for section in (section_info, section_pm):
        if section:
            keys.update(k for k in section if k.startswith("lt:"))
    return sorted(keys)


def _discover_gpon(section_oposs_isam_gpon,
                   section_oposs_isam_gpon_info) -> DiscoveryResult:
    for key in _gpon_items(section_oposs_isam_gpon, section_oposs_isam_gpon_info):
        yield Service(item=key)


def _check_gpon(item, section_oposs_isam_gpon,
                section_oposs_isam_gpon_info) -> CheckResult:
    # The two sections are fetched on different intervals, so merge whichever
    # of them carries this item. Inventory first, PM data on top: no field
    # names overlap, but PM is the fresher of the two.
    dic = {}
    for section in (section_oposs_isam_gpon_info, section_oposs_isam_gpon):
        if section and item in section:
            dic.update(section[item])
    if not dic:
        return

    # Result: compare admin vs oper status. Both come from the slow section, so
    # they can be absent while traffic data is present - report that honestly
    # instead of comparing two empty strings and calling it OK.
    if "adminstatus" not in dic and "operstatus" not in dic:
        yield Result(
            state=State.UNKNOWN,
            summary="Port status unavailable (oposs_isam_gpon_info section missing)",
        )
    else:
        admin = dic.get("adminstatus", "")
        oper = dic.get("operstatus", "")
        if admin == oper:
            state = State.OK
        elif oper == "4":
            state = State.UNKNOWN
        else:
            state = State.CRIT
        yield Result(
            state=state,
            summary="%s \u2013 OperStatus: %s, AdminStatus: %s" % (
                dic.get("description", ""),
                OPER_STATUS.get(oper, oper),
                ADMIN_STATUS.get(admin, admin),
            ),
        )

    # SFP optics metrics (conditionally available)
    bc = dic.get("biascurrent", "not-available")
    if bc != "not-available":
        try:
            yield Metric("oposs_isam_bias_current", float(bc.split(" ")[0]) / 1000.0)
        except (ValueError, IndexError):
            pass

    for name, key in [
        ("oposs_isam_txpower", "txpower"),
        ("oposs_isam_rxpower", "rxpower"),
        ("oposs_isam_voltage", "voltage"),
        ("oposs_isam_temperature", "temperature"),
    ]:
        val = dic.get(key, "")
        if val and val[0:1].isdigit():
            try:
                yield Metric(name, float(val.split(" ")[0]))
            except (ValueError, IndexError):
                pass

    # Byte counters → bytes/sec rates. The raw values are PM current-interval
    # counters that the device clears every 5 min; _interval_rate() adapts to
    # the poll cadence, see its docstring.
    value_store = get_value_store()
    now = time.time()
    rates = {}
    for metric_key in _BYTE_COUNTER_FIELDS:
        if metric_key not in dic:
            continue
        max_rate = (_MAX_RX_BYTES_PER_S if metric_key.startswith("Rx")
                    else _MAX_TX_BYTES_PER_S)
        rate = _interval_rate(value_store, metric_key, now,
                              dic[metric_key], max_rate)
        if rate is not None:
            rates[metric_key] = rate
            yield Metric(_RATE_METRIC[metric_key], rate)

    # Utilization derived from byte rates against the GPON line rate.
    # Replaces the device-reported Util fields, which were also tied to
    # the resetting PM interval and so equally distorted.
    for util_metric, bytes_key, line_rate_bps in _UTIL_DERIVATIONS:
        if bytes_key in rates:
            util_pct = rates[bytes_key] * 8.0 / line_rate_bps * 100.0
            yield Metric(util_metric, util_pct)

    # Plain gauges from the same SNMP block.
    for metric_key in ["NumActiveOnts", "RxDBACongestionTime"]:
        if metric_key in dic:
            yield Metric("oposs_isam_%s" % metric_key, dic[metric_key])


# Fast section: the PM counters only. Left uncached so it is fetched on every
# check run; measured at ~1 s on the device.
snmp_section_oposs_isam_gpon = SNMPSection(
    name="oposs_isam_gpon",
    detect=contains(".1.3.6.1.2.1.1.1.0", "NOKIA ISAM"),
    parse_function=_parse_gpon,
    fetch=[
        # 0: PM - NumActiveOnts, RxDBACongestionTime
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.21.57.1",
            oids=[
                OIDEnd(),
                "16",  # NumActiveOnts
                "17",  # RxDBACongestionTime
            ],
        ),
        # 1: PM - byte counters (8-byte OIDBytes, cleared every 5 min;
        # check turns them into rates and derives utilization)
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.21.57.1",
            oids=[
                OIDEnd(),
                OIDBytes("8"),   # TxUcastBytes
                OIDBytes("10"),  # TxMcastBytes
                OIDBytes("11"),  # TxBcastBytes
                OIDBytes("12"),  # TxTotalBytes
                OIDBytes("13"),  # RxTotalBytes
                OIDBytes("14"),  # TxUcastDropBytes
                OIDBytes("15"),  # RxTotalDropBytes
                OIDBytes("18"),  # TxMcastDropBytes
                OIDBytes("19"),  # TxBcastDropBytes
                OIDBytes("20"),  # TxTotalDropBytes
            ],
        ),
    ],
)

# Slow section: SFP optics, descriptions and interface status. All of it
# changes slowly, and the optics tree alone is roughly ten times the cost of
# the PM tree above, so give this section a "Fetch intervals for SNMP sections"
# rule (300 s) when the host is checked more often than that.
snmp_section_oposs_isam_gpon_info = SNMPSection(
    name="oposs_isam_gpon_info",
    detect=contains(".1.3.6.1.2.1.1.1.0", "NOKIA ISAM"),
    parse_function=_parse_gpon_info,
    fetch=[
        # 0: Enterprise GPON inventory (SFP optics) - the expensive one
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.56.5.1",
            oids=[
                OIDEnd(),
                "1",   # logicalSlot
                "2",   # facePlateId
                "3",   # availability
                "4",   # signalStatus
                "5",   # faultStatus
                "6",   # txPower
                "7",   # rxPower
                "8",   # biasCurrent
                "9",   # Voltage
                "10",  # Temperature
            ],
        ),
        # 1: GPON descriptions
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.11.2.1",
            oids=[
                OIDEnd(),
                "19",  # description
            ],
        ),
        # 2: Standard IF admin/oper status
        SNMPTree(
            base=".1.3.6.1.2.1.2.2.1",
            oids=[
                OIDEnd(),
                "7",  # adminStatus
                "8",  # operStatus
            ],
        ),
    ],
)

check_plugin_oposs_isam_gpon = CheckPlugin(
    name="oposs_isam_gpon",
    # With more than one section the discovery and check functions take one
    # `section_<name>` argument per entry, in this order.
    sections=["oposs_isam_gpon", "oposs_isam_gpon_info"],
    service_name="GPON %s",
    discovery_function=_discover_gpon,
    check_function=_check_gpon,
)
