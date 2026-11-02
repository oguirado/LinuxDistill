# Bundled engine

These files are bundled unchanged so a clean clone builds with no other checkout. They were written by the maintainer for earlier projects and are distributed here under this repository's licence, `GPL-2.0-only`.

| Path | Purpose |
|---|---|
| `hb/tools/hblib2.py` | Canonical JSON, hashes, tokeniser helpers, integer BM25F pieces |
| `hb/tools/schemalib.py` | Schema validation over `hb/standards/schemas` |
| `hb/subject/tools/route_v2.py` | Router tokeniser |
| `hb/subject/tools/jsonschema_lite.py` | Standard-library JSON Schema subset validator |
| `hb/standards/schemas/` | `hb.*.v2` record schemas |
| `mv/ref/router_index.metaviewer.py` | File-node compiler (`_derive_ids`, `compile_material`), from MetaViewer's router |
| `mv/kit/tools/jsonschema_lite.py` | Same validator, at the path the compiler expects |
| `mv/kit/standards/schemas/ctx.node.v2.schema.json` | File-node schema |

Do not edit these files: they feed the build, so a change alters the router output.
