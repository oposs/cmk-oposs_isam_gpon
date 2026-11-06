"""Metric names: prefixed, declared, and translated from the legacy names."""

import importlib.util
import pathlib
import sys

import pytest
from cmk.agent_based.v2 import Metric
from cmk.graphing.v1 import graphs, metrics, perfometers, translations

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "local/lib/python3/cmk_addons/plugins/oposs_isam_gpon"

T0 = 1_800_000_000  # a PM window boundary


def _load(path):
    name = "test_graphing_" + path.stem + "_" + path.parent.name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check():
    return _load(PLUGIN / "agent_based/oposs_isam_gpon.py")


@pytest.fixture(scope="module")
def graphing_objects():
    objects = []
    for path in sorted((PLUGIN / "graphing").glob("*.py")):
        objects.extend(vars(_load(path)).values())
    return objects


@pytest.fixture(scope="module")
def declared(graphing_objects):
    return {o.name for o in graphing_objects if isinstance(o, metrics.Metric)}


@pytest.fixture(scope="module")
def emitted(check):
    """Every metric the GPON check yields for a port with all data present."""
    ifindex = str((2 << 25) | (0b1101 << 21))  # lt:1/1/1/01
    pm = check._parse_gpon([
        [[ifindex, "12", "3"]],
        [[ifindex, *([list((1000).to_bytes(8, "big"))] * 10)]],
    ])
    info = check._parse_gpon_info([
        [["4355.1", "1", "1", "1", "1", "1",
          "3.21 dBm", "1.50 dBm", "18.50 mA", "3.28 VDC", "41.0 degrees Celsius"]],
        [[ifindex, "port"]],
        [[ifindex, "1", "1"]],
    ])
    mp = pytest.MonkeyPatch()
    mp.setattr(check, "get_value_store", dict)
    mp.setattr(check.time, "time", lambda: T0 + 150)
    try:
        out = list(check._check_gpon("lt:1/1/1/01", pm, info))
    finally:
        mp.undo()
    return [m.name for m in out if isinstance(m, Metric)]


def test_every_emitted_metric_is_prefixed(emitted):
    assert emitted
    assert [n for n in emitted if not n.startswith("oposs_isam_")] == []


def test_every_emitted_metric_is_declared(emitted, declared):
    assert sorted(set(emitted) - declared) == []


def test_every_declared_metric_is_emitted(emitted, declared):
    assert sorted(declared - set(emitted)) == []


def test_each_metric_is_emitted_once(emitted):
    assert len(emitted) == len(set(emitted))


def test_every_declared_name_is_prefixed(graphing_objects):
    kinds = (metrics.Metric, graphs.Graph, perfometers.Perfometer)
    names = [o.name for o in graphing_objects if isinstance(o, kinds)]
    assert names
    assert [n for n in names if not n.startswith("oposs_isam_")] == []


def test_graphs_and_perfometers_use_declared_metrics(graphing_objects, declared):
    used = set()
    for o in graphing_objects:
        if isinstance(o, graphs.Graph):
            used.update(o.simple_lines)
            used.update(o.compound_lines)
        elif isinstance(o, perfometers.Perfometer):
            used.update(o.segments)
    assert used
    assert sorted(n for n in used if isinstance(n, str) and n not in declared) == []


def test_legacy_names_translate_to_declared_metrics(graphing_objects, declared):
    found = [o for o in graphing_objects if isinstance(o, translations.Translation)]
    assert len(found) == 1
    translation = found[0]
    # Keyed on the check command a live service runs today, not the legacy one.
    assert translation.check_commands == [translations.PassiveCheck("oposs_isam_gpon")]
    for old, rule in translation.translations.items():
        assert old.startswith("isam_")
        assert isinstance(rule, translations.RenameTo)
        assert rule.metric_name == "oposs_" + old
        assert rule.metric_name in declared


def test_no_translation_resurrects_the_bad_traffic_history(graphing_objects):
    """The traffic and utilization series were reset on purpose in 0.5.0."""
    (translation,) = [o for o in graphing_objects if isinstance(o, translations.Translation)]
    targets = {rule.metric_name for rule in translation.translations.values()}
    assert [t for t in targets if "bytes" in t.lower() or "util" in t.lower()] == []
