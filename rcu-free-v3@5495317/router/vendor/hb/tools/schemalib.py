"""Schema validation for hb artefacts: $ref inlining over standards/schemas + the router v2 jsonschema_lite validator."""
import os, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hblib2 as L  # noqa: E402

_REG = {}


def registry(schema_dir=None):
    d = schema_dir or os.path.join(L.HB, "standards", "schemas")
    if d not in _REG:
        _REG[d] = {}
        for f in sorted(os.listdir(d)):
            if f.endswith(".schema.json"):
                s = L.jload(os.path.join(d, f))
                _REG[d][s["$id"]] = s
    return _REG[d]


def inline(s, reg):
    if isinstance(s, dict):
        if "$ref" in s:
            ref = s["$ref"]
            if "#" in ref:
                doc, frag = ref.split("#", 1)
            else:
                doc, frag = ref, ""
            t = reg[doc]
            for part in [p for p in frag.split("/") if p]:
                t = t[part]
            return inline(t, reg)
        return {k: inline(v, reg) for k, v in s.items() if k not in ("$schema", "$id", "$defs")}
    if isinstance(s, list):
        return [inline(v, reg) for v in s]
    return s


def validate(obj, schema_id, schema_dir=None):
    reg = registry(schema_dir)
    lite = L.load_mod(L.SUBJECT, "tools/jsonschema_lite.py")
    return lite.validate(obj, inline(reg[schema_id], reg))
