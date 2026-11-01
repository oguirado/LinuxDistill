#!/usr/bin/env python3
"""BT-LXR-02 gate: every FILE node validates the kit ctx.node.v2 schema, ids are unique, no string carries an
absolute /home/ path, and `lx_nodes.py --check` is byte-identical under another cwd, TZ and PYTHONHASHSEED.
must-FAIL: a synthetic node carrying a /home/ path (privacy law)."""
import importlib.util, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def check(path):
    spec = importlib.util.spec_from_file_location("kit_lite", os.path.join(L.MV_ROUTER, "kit", "tools", "jsonschema_lite.py"))
    lite = importlib.util.module_from_spec(spec); spec.loader.exec_module(lite)
    schema = L.jload(os.path.join(L.MV_ROUTER, "kit", "standards", "schemas", "ctx.node.v2.schema.json"))
    nodes = L.read_jsonl(path)
    invalid = [n.get("id") for n in nodes if lite.validate(n, schema)]
    ids = [n["id"] for n in nodes]
    leaks = [n["id"] for n in nodes if any("/home/" in s or s.startswith("/") for s in strings(n))]
    ok = bool(nodes) and not invalid and len(set(ids)) == len(ids) and not leaks
    return ok, f"nodes={len(nodes)} invalid={len(invalid)} dup_ids={len(ids)-len(set(ids))} home_paths={len(leaks)}"


def positive():
    ok, d = check(os.path.join(X, "nodes", "lx.jsonl"))
    env = dict(L.ENV, TZ="Asia/Tokyo", PYTHONHASHSEED="12345")
    p = subprocess.run([sys.executable, "-I", "-B", os.path.join(X, "tools", "lx_nodes.py"), "--check"], cwd="/", env=env, capture_output=True, text=True)
    return ok and p.returncode == 0, d + " check=" + p.stdout.strip()[:120]


def must_fail():
    return check(os.path.join(X, "fixtures", "lx", "nodes", "privacy_leak.jsonl"))


if __name__ == "__main__":
    main(positive, must_fail)
