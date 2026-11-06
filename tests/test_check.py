"""Tests for the Nokia ISAM check plugins: Linecard and GPON.

The string tables below have the shape the SNMP fetch of each section
delivers: one list of rows per SNMPTree, each row starting with the OIDEnd,
followed by the columns in the order of the tree's `oids`. OIDBytes columns
arrive as lists of byte values.
"""

import importlib.util
import pathlib
import sys

import pytest
from cmk.agent_based.v2 import Metric, Result, Service, State

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "local/lib/python3/cmk_addons/plugins/oposs_isam_gpon/agent_based/oposs_isam_gpon.py"

# A PM window boundary: T0 % 300 == 0.
T0 = 1_800_000_000
assert T0 % 300 == 0

GPON_DOWNSTREAM_BPS = 2_488_320_000
GPON_UPSTREAM_BPS = 1_244_160_000


@pytest.fixture(scope="module")
def check():
    name = "test_oposs_isam_gpon_check"
    spec = importlib.util.spec_from_file_location(name, CHECK)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


def ifindex(slot, pon):
    """The bit-packed ifIndex the ISAM uses for PON port lt:1/1/<slot>/<pon>.

    94371840 (0x5A00000) is lt:1/1/1/01 on a real ISAM.
    """
    return str(((slot + 1) << 25) | (0b1101 << 21) | ((pon - 1) << 16))


def octets(value):
    """An 8-byte counter as OIDBytes delivers it."""
    return list(value.to_bytes(8, "big"))


# ---------------------------------------------------------------------------
# Linecard
# ---------------------------------------------------------------------------

def _card(oid, availability, serial="YP1234567890", actual="FWLT-B"):
    # OIDEnd, serial, slotid, plannedtype, actualtype, slotpower,
    # adminstatus, operstatus, operror, availability, containerid,
    # containeroffset
    return [oid, serial, oid, actual, actual, "1", "1", "1", "1", availability, "1", "0"]


LINECARDS = [[
    _card("4352", "1", actual="RANT-A"),   # acu:1/1
    _card("4353", "1", actual="FANT-F"),   # nt-a:
    _card("4355", "1"),                    # lt:1/1/1 available
    _card("4356", "3"),                    # lt:1/1/2 failed
    _card("4357", "5", serial="", actual="EMPTY"),  # lt:1/1/3 not installed
    _card("4358", "6"),                    # lt:1/1/4 off-line
]]


def test_linecard_parse_maps_slot_ids(check):
    section = check._parse_linecard(LINECARDS)
    assert sorted(section) == ["acu:1/1", "lt:1/1/1", "lt:1/1/2", "lt:1/1/3", "lt:1/1/4", "nt-a:"]
    assert section["lt:1/1/1"]["serial"] == "YP1234567890"
    assert section["lt:1/1/1"]["availability"] == "1"


def test_linecard_parse_keeps_unknown_slot_id_as_is(check):
    section = check._parse_linecard([[_card("4400", "1")]])
    assert list(section) == ["4400"]
    assert list(check._discover_linecard(section)) == []


def test_linecard_discovers_only_line_terminal_cards(check):
    section = check._parse_linecard(LINECARDS)
    assert list(check._discover_linecard(section)) == [
        Service(item="lt:1/1/1"), Service(item="lt:1/1/2"),
        Service(item="lt:1/1/3"), Service(item="lt:1/1/4"),
    ]


@pytest.mark.parametrize("item, state, text", [
    ("lt:1/1/1", State.OK, "FWLT-B (YP1234567890) Status: Available"),
    ("lt:1/1/2", State.CRIT, "FWLT-B (YP1234567890) Status: Failed"),
    ("lt:1/1/3", State.OK, "EMPTY () Status: Not Installed"),
    ("lt:1/1/4", State.WARN, "FWLT-B (YP1234567890) Status: Off-Line"),
])
def test_linecard_state_follows_availability(check, item, state, text):
    section = check._parse_linecard(LINECARDS)
    assert list(check._check_linecard(item, section)) == [Result(state=state, summary=text)]


def test_linecard_unknown_availability_code_is_warn(check):
    section = check._parse_linecard([[_card("4355", "99")]])
    assert list(check._check_linecard("lt:1/1/1", section)) == [
        Result(state=State.WARN, summary="FWLT-B (YP1234567890) Status: 99")]


def test_linecard_vanished_item_yields_nothing(check):
    section = check._parse_linecard(LINECARDS)
    assert list(check._check_linecard("lt:1/1/8", section)) == []


def test_linecard_empty_walk(check):
    assert check._parse_linecard([[]]) == {}


# ---------------------------------------------------------------------------
# GPON: OID-to-item mapping
# ---------------------------------------------------------------------------

def test_real_isam_ifindex_is_first_pon_of_first_lt(check):
    assert ifindex(1, 1) == "94371840"
    assert check._id2name("94371840") == "lt:1/1/1/01"


@pytest.mark.parametrize("slot, pon", [(1, 1), (1, 16), (8, 3)])
def test_bitmap_index_decodes_pon_ports(check, slot, pon):
    assert check._id2name(ifindex(slot, pon)) == f"lt:1/1/{slot}/{pon:02d}"


def test_bitmap_index_ignores_non_pon_interfaces(check):
    # Same slot, other interface type (ethernet uplink, ...), and a plain
    # small ifIndex as on the NT.
    assert check._id2name(str((2 << 25) | (0b0001 << 21))) is None
    assert check._id2name("1") is None


@pytest.mark.parametrize("oid, item", [
    ("4355.1", "lt:1/1/1/01"),
    ("4362.16", "lt:1/1/8/16"),
    ("4353.257", "nt-a:/xfp:1"),
])
def test_enterprise_index_decodes(check, oid, item):
    assert check._id2gpon(oid) == item


def test_both_index_schemes_name_the_same_port(check):
    """The inventory and the PM tables must merge into one service per port."""
    for slot in range(1, 9):
        for pon in (1, 2, 16):
            assert check._id2gpon(f"{4354 + slot}.{pon}") == check._id2name(ifindex(slot, pon))


# ---------------------------------------------------------------------------
# GPON: sections
# ---------------------------------------------------------------------------

P1 = ifindex(1, 1)
P2 = ifindex(1, 2)


def _pm(oid, onts="12", congestion="0", counters=(0,) * 10):
    return [oid, onts, congestion], [oid, *(octets(c) for c in counters)]


def pm_section(*ports):
    gauges, bytes_ = zip(*ports)
    return [list(gauges), list(bytes_)]


def _optics(oid, tx="3.21 dBm", rx="not-available", bias="18.50 mA",
            voltage="3.28 VDC", temperature="41.0 degrees Celsius"):
    # logicalSlot, facePlateId, availability, signalStatus, faultStatus,
    # txPower, rxPower, biasCurrent, Voltage, Temperature
    return [oid, "1", "1", "1", "1", "1", tx, rx, bias, voltage, temperature]


INFO = [
    [_optics("4355.1"), _optics("4355.2", tx="not-available", bias="not-available",
                                voltage="not-available", temperature="not-available")],
    [[P1, "OLT Port Bahnhofstrasse"], [P2, "OLT Port Industrie"], ["1", "uplink"]],
    [[P1, "1", "1"], [P2, "1", "2"], ["1", "1", "1"]],
]


def test_gpon_info_parse_merges_three_trees(check):
    section = check._parse_gpon_info(INFO)
    assert sorted(section) == ["lt:1/1/1/01", "lt:1/1/1/02"]
    port = section["lt:1/1/1/01"]
    assert port["description"] == "OLT Port Bahnhofstrasse"
    assert port["adminstatus"] == "1"
    assert port["operstatus"] == "1"
    assert port["txpower"] == "3.21 dBm"


def test_gpon_pm_parse_converts_counters(check):
    section = check._parse_gpon(pm_section(
        _pm(P1, onts="12", congestion="7", counters=range(1, 11))))
    port = section["lt:1/1/1/01"]
    assert port["NumActiveOnts"] == 12.0
    assert port["RxDBACongestionTime"] == 7.0
    assert [port[f] for f in check._BYTE_COUNTER_FIELDS] == list(range(1, 11))


def test_gpon_pm_parse_counts_large_counters_big_endian(check):
    big = 0x0102030405060708
    section = check._parse_gpon(pm_section(_pm(P1, counters=(big,) * 10)))
    assert section["lt:1/1/1/01"]["TxTotalBytes"] == big


def test_gpon_pm_parse_drops_counters_that_are_not_eight_bytes(check):
    gauges, counters = _pm(P1)
    counters[1] = []          # empty OIDBytes: the column was missing
    counters[4] = [0, 1, 2]   # truncated
    section = check._parse_gpon([[gauges], [counters]])
    port = section["lt:1/1/1/01"]
    assert "TxUcastBytes" not in port
    assert "TxTotalBytes" not in port
    assert "RxTotalBytes" in port


@pytest.mark.xfail(strict=True, reason="BUG: an empty PM gauge value makes the whole oposs_isam_gpon section fail to parse")
def test_gpon_pm_parse_survives_empty_gauge(check):
    # SNMP delivers "" for a column the device does not answer for an index.
    section = check._parse_gpon(pm_section(_pm(P1, congestion=""), _pm(P2)))
    assert sorted(section) == ["lt:1/1/1/01", "lt:1/1/1/02"]


def test_gpon_discovery_from_either_section(check):
    pm = check._parse_gpon(pm_section(_pm(P1), _pm(ifindex(2, 1))))
    info = check._parse_gpon_info(INFO)
    items = [s.item for s in check._discover_gpon(pm, info)]
    assert items == ["lt:1/1/1/01", "lt:1/1/1/02", "lt:1/1/2/01"]
    assert [s.item for s in check._discover_gpon(None, info)] == ["lt:1/1/1/01", "lt:1/1/1/02"]
    assert [s.item for s in check._discover_gpon(pm, None)] == ["lt:1/1/1/01", "lt:1/1/2/01"]
    assert list(check._discover_gpon(None, None)) == []


def test_gpon_discovery_skips_non_line_terminal_ports(check):
    info = check._parse_gpon_info([[_optics("4353.257")], [], []])
    assert list(check._discover_gpon(None, info)) == []


# ---------------------------------------------------------------------------
# GPON: check
# ---------------------------------------------------------------------------

@pytest.fixture
def poll(check, monkeypatch):
    """Run the GPON check at a given wall-clock time with a persistent value store."""
    store = {}
    monkeypatch.setattr(check, "get_value_store", lambda: store)

    def run(now, item, pm, info):
        monkeypatch.setattr(check.time, "time", lambda: now)
        return list(check._check_gpon(item, pm, info))

    run.store = store
    return run


def _metrics(results):
    return {r.name: r.value for r in results if isinstance(r, Metric)}


def _results(results):
    return [r for r in results if isinstance(r, Result)]


def test_gpon_ok_port_with_optics(check, poll):
    info = check._parse_gpon_info(INFO)
    out = poll(T0 + 150, "lt:1/1/1/01", None, info)
    assert _results(out) == [Result(
        state=State.OK,
        summary="OLT Port Bahnhofstrasse \u2013 OperStatus: Up, AdminStatus: Up")]
    assert _metrics(out) == {
        "oposs_isam_bias_current": pytest.approx(0.0185),
        "oposs_isam_txpower": 3.21,
        "oposs_isam_voltage": 3.28,
        "oposs_isam_temperature": 41.0,
    }


def test_gpon_not_available_optics_are_skipped(check, poll):
    info = check._parse_gpon_info(INFO)
    out = poll(T0 + 150, "lt:1/1/1/02", None, info)
    assert _metrics(out) == {}


def test_gpon_oper_down_is_crit(check, poll):
    info = check._parse_gpon_info(INFO)
    assert _results(poll(T0 + 150, "lt:1/1/1/02", None, info)) == [Result(
        state=State.CRIT,
        summary="OLT Port Industrie \u2013 OperStatus: Down, AdminStatus: Up")]


@pytest.mark.parametrize("admin, oper, state", [
    ("2", "2", State.OK),        # shut down on purpose
    ("1", "4", State.UNKNOWN),   # oper unknown
    ("1", "7", State.CRIT),      # lower layer down
    ("2", "1", State.CRIT),      # up although shut down
    ("1", "6", State.CRIT),      # not present
])
def test_gpon_admin_oper_comparison(check, poll, admin, oper, state):
    info = check._parse_gpon_info([[], [[P1, "x"]], [[P1, admin, oper]]])
    (result,) = _results(poll(T0 + 150, "lt:1/1/1/01", None, info))
    assert result.state == state


def test_gpon_status_unknown_without_info_section(check, poll):
    pm = check._parse_gpon(pm_section(_pm(P1)))
    assert _results(poll(T0 + 150, "lt:1/1/1/01", pm, None)) == [Result(
        state=State.UNKNOWN,
        summary="Port status unavailable (oposs_isam_gpon_info section missing)")]


def test_gpon_vanished_item_yields_nothing(check, poll):
    pm = check._parse_gpon(pm_section(_pm(P1)))
    info = check._parse_gpon_info(INFO)
    assert poll(T0 + 150, "lt:1/1/8/16", pm, info) == []


def test_gpon_garbage_optics_are_skipped(check, poll):
    info = check._parse_gpon_info([
        [_optics("4355.1", tx="3,21 dBm", bias="n/a", voltage="", temperature="12abc")],
        [], [[P1, "1", "1"]],
    ])
    assert _metrics(poll(T0 + 150, "lt:1/1/1/01", None, info)) == {}


@pytest.mark.xfail(strict=True, reason="BUG: negative optics readings (Rx power in dBm, sub-zero temperature) are dropped")
def test_gpon_negative_optics_are_recorded(check, poll):
    info = check._parse_gpon_info([
        [_optics("4355.1", rx="-18.40 dBm", temperature="-5.0 degrees Celsius")],
        [], [[P1, "1", "1"]],
    ])
    metrics = _metrics(poll(T0 + 150, "lt:1/1/1/01", None, info))
    assert metrics["oposs_isam_rxpower"] == -18.4
    assert metrics["oposs_isam_temperature"] == -5.0


def _traffic(tx_total, rx_total=0, onts="12"):
    counters = [0] * 10
    counters[3] = tx_total   # TxTotalBytes
    counters[4] = rx_total   # RxTotalBytes
    return [_pm(P1, onts=onts, congestion="3", counters=counters)]


def test_gpon_first_poll_divides_by_time_since_boundary(check, poll):
    pm = check._parse_gpon(pm_section(*_traffic(150_000_000, 15_000_000)))
    metrics = _metrics(poll(T0 + 150, "lt:1/1/1/01", pm, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 1_000_000
    assert metrics["oposs_isam_rx_total_bytes_rate"] == 100_000
    assert metrics["oposs_isam_tx_total_util"] == pytest.approx(1_000_000 * 8 / GPON_DOWNSTREAM_BPS * 100)
    assert metrics["oposs_isam_rx_total_util"] == pytest.approx(100_000 * 8 / GPON_UPSTREAM_BPS * 100)
    assert metrics["oposs_isam_tx_ucast_bytes_rate"] == 0
    assert metrics["oposs_isam_NumActiveOnts"] == 12.0
    assert metrics["oposs_isam_RxDBACongestionTime"] == 3.0


def test_gpon_emits_every_traffic_metric_once(check, poll):
    pm = check._parse_gpon(pm_section(_pm(P1, counters=[1_000] * 10)))
    out = poll(T0 + 150, "lt:1/1/1/01", pm, None)
    names = [r.name for r in out if isinstance(r, Metric)]
    assert sorted(names) == sorted(
        list(check._RATE_METRIC.values())
        + [m for m, _, _ in check._UTIL_DERIVATIONS]
        + ["oposs_isam_NumActiveOnts", "oposs_isam_RxDBACongestionTime"])


def test_gpon_no_rate_close_after_the_boundary(check, poll):
    # The counter may still hold the full previous window here.
    pm = check._parse_gpon(pm_section(*_traffic(300_000_000)))
    metrics = _metrics(poll(T0 + 5, "lt:1/1/1/01", pm, None))
    assert "oposs_isam_tx_total_bytes_rate" not in metrics
    assert "oposs_isam_tx_total_util" not in metrics
    # The gauges do not depend on the window.
    assert metrics["oposs_isam_NumActiveOnts"] == 12.0


def test_gpon_rate_above_line_rate_is_discarded(check, poll):
    line_rate_bytes = GPON_DOWNSTREAM_BPS / 8
    pm = check._parse_gpon(pm_section(*_traffic(int(line_rate_bytes * 100 * 1.5))))
    assert "oposs_isam_tx_total_bytes_rate" not in _metrics(poll(T0 + 100, "lt:1/1/1/01", pm, None))


def test_gpon_frequent_polls_difference_within_a_window(check, poll):
    first = check._parse_gpon(pm_section(*_traffic(60_000_000)))
    second = check._parse_gpon(pm_section(*_traffic(180_000_000)))
    poll(T0 + 60, "lt:1/1/1/01", first, None)
    metrics = _metrics(poll(T0 + 120, "lt:1/1/1/01", second, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 2_000_000


def test_gpon_frequent_polls_across_a_clear(check, poll):
    # Cleared at the boundary T0+300; only the 7 MB since then are known,
    # spread over the whole 70 s poll interval.
    poll(T0 + 250, "lt:1/1/1/01", check._parse_gpon(pm_section(*_traffic(500_000_000))), None)
    after = check._parse_gpon(pm_section(*_traffic(7_000_000)))
    metrics = _metrics(poll(T0 + 320, "lt:1/1/1/01", after, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 100_000


def test_gpon_frequent_polls_across_a_quiet_clear_with_growing_value(check, poll):
    # A quiet window followed by a burst after the clear: the value grows,
    # but the timestamps show a boundary in between.
    poll(T0 + 250, "lt:1/1/1/01", check._parse_gpon(pm_section(*_traffic(1_000))), None)
    after = check._parse_gpon(pm_section(*_traffic(70_000_000)))
    metrics = _metrics(poll(T0 + 320, "lt:1/1/1/01", after, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 1_000_000


def test_gpon_poll_in_the_late_clear_gap_recovers_the_tail(check, poll):
    # The device clears 1-3 s after the boundary; a read at T0+305 that is
    # still growing belongs to the previous window.
    poll(T0 + 240, "lt:1/1/1/01", check._parse_gpon(pm_section(*_traffic(240_000_000))), None)
    gap = check._parse_gpon(pm_section(*_traffic(305_000_000)))
    metrics = _metrics(poll(T0 + 305, "lt:1/1/1/01", gap, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 1_000_000


def test_gpon_slow_polls_fall_back_to_time_since_boundary(check, poll):
    # At the default 300 s interval differencing is noise; the counter is
    # read as bytes since the window boundary instead.
    poll(T0 + 100, "lt:1/1/1/01", check._parse_gpon(pm_section(*_traffic(10_000_000))), None)
    later = check._parse_gpon(pm_section(*_traffic(20_000_000)))
    metrics = _metrics(poll(T0 + 400, "lt:1/1/1/01", later, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 200_000


def test_gpon_near_simultaneous_polls_fall_back_to_time_since_boundary(check, poll):
    poll(T0 + 100, "lt:1/1/1/01", check._parse_gpon(pm_section(*_traffic(10_000_000))), None)
    again = check._parse_gpon(pm_section(*_traffic(10_500_000)))
    metrics = _metrics(poll(T0 + 105, "lt:1/1/1/01", again, None))
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 100_000


def test_gpon_value_store_keeps_the_last_reading(check, poll):
    pm = check._parse_gpon(pm_section(*_traffic(60_000_000)))
    poll(T0 + 60, "lt:1/1/1/01", pm, None)
    assert poll.store["TxTotalBytes"] == (T0 + 60, 60_000_000)


def test_gpon_pm_merges_with_info(check, poll):
    pm = check._parse_gpon(pm_section(*_traffic(150_000_000)))
    info = check._parse_gpon_info(INFO)
    out = poll(T0 + 150, "lt:1/1/1/01", pm, info)
    assert _results(out)[0].state == State.OK
    metrics = _metrics(out)
    assert metrics["oposs_isam_txpower"] == 3.21
    assert metrics["oposs_isam_tx_total_bytes_rate"] == 1_000_000
