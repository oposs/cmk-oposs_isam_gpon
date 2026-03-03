#!/usr/bin/env python3
# Copyright (C) 2025 OETIKER+PARTNER AG - License: GNU General Public License v2

"""
SNMP check plugin for Nokia ISAM GPON equipment.
Monitors line card availability and GPON port status including
SFP optics and traffic statistics.
"""

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
)

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
        elif conv_type == "kpercent1000":
            for field in dic:
                dic[field] = float(dic[field]) / 1000.0
        elif conv_type == "kpercent100":
            for field in dic:
                dic[field] = float(dic[field]) / 100.0
        elif conv_type == "float":
            for field in dic:
                dic[field] = float(dic[field])
        result.setdefault(key, {}).update(dic)


def _parse_gpon(string_table):
    """Parse GPON data from 7 SNMP trees."""
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

    # Block 1: PM - NumActiveOnts, RxDBACongestionTime (float)
    _parse_bitmap_block(
        result, string_table[1],
        ["NumActiveOnts", "RxDBACongestionTime"], "float",
    )

    # Block 2: PM - TxUcastUtil, TxBcastUtil (kpercent1000)
    _parse_bitmap_block(
        result, string_table[2],
        ["TxUcastUtil", "TxBcastUtil"], "kpercent1000",
    )

    # Block 3: PM - TxMcastUtil, TxTotalUtil, RxTotalUtil (kpercent100)
    _parse_bitmap_block(
        result, string_table[3],
        ["TxMcastUtil", "TxTotalUtil", "RxTotalUtil"], "kpercent100",
    )

    # Block 4: PM - byte counters (8-byte big-endian)
    _parse_bitmap_block(
        result, string_table[4],
        [
            "TxUcastBytes", "TxMcastBytes", "TxBcastBytes",
            "TxTotalBytes", "RxTotalBytes", "TxUcastDropBytes",
            "RxTotalDropBytes", "TxMcastDropBytes", "TxBcastDropBytes",
            "TxTotalDropBytes",
        ],
        "8bytes",
    )

    # Block 5: Description
    _parse_bitmap_block(result, string_table[5], ["description"], "")

    # Block 6: Standard IF admin/oper status
    _parse_bitmap_block(result, string_table[6], ["adminstatus", "operstatus"], "")

    return result


def _discover_gpon(section) -> DiscoveryResult:
    for key in section:
        if key.startswith("lt:"):
            yield Service(item=key)


def _check_gpon(item, section) -> CheckResult:
    if item not in section:
        return
    dic = section[item]

    # Result: compare admin vs oper status
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

    # Traffic and utilization metrics
    for metric_key in [
        "TxUcastBytes", "TxMcastBytes", "TxBcastBytes",
        "TxTotalBytes", "RxTotalBytes", "TxUcastDropBytes",
        "RxTotalDropBytes", "TxMcastDropBytes", "TxBcastDropBytes",
        "TxTotalDropBytes",
        "TxUcastUtil", "TxMcastUtil", "TxBcastUtil",
        "TxTotalUtil", "RxTotalUtil",
        "NumActiveOnts", "RxDBACongestionTime",
    ]:
        if metric_key in dic:
            yield Metric("oposs_isam_%s" % metric_key, dic[metric_key])


snmp_section_oposs_isam_gpon = SNMPSection(
    name="oposs_isam_gpon",
    detect=contains(".1.3.6.1.2.1.1.1.0", "NOKIA ISAM"),
    parse_function=_parse_gpon,
    fetch=[
        # 0: Enterprise GPON inventory
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
        # 1: PM - NumActiveOnts, RxDBACongestionTime
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.21.57.1",
            oids=[
                OIDEnd(),
                "16",  # NumActiveOnts
                "17",  # RxDBACongestionTime
            ],
        ),
        # 2: PM - TxUcastUtil, TxBcastUtil
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.21.57.1",
            oids=[
                OIDEnd(),
                "2",  # TxUcastUtil
                "5",  # TxBcastUtil
            ],
        ),
        # 3: PM - TxMcastUtil, TxTotalUtil, RxTotalUtil
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.21.57.1",
            oids=[
                OIDEnd(),
                "4",  # TxMcastUtil
                "6",  # TxTotalUtil
                "7",  # RxTotalUtil
            ],
        ),
        # 4: PM - byte counters (8-byte OIDBytes)
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
        # 5: GPON descriptions
        SNMPTree(
            base=".1.3.6.1.4.1.637.61.1.35.11.2.1",
            oids=[
                OIDEnd(),
                "19",  # description
            ],
        ),
        # 6: Standard IF admin/oper status
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
    sections=["oposs_isam_gpon"],
    service_name="GPON %s",
    discovery_function=_discover_gpon,
    check_function=_check_gpon,
)
