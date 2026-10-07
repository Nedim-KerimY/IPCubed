"""Check a built PCM package the way KiCad's Plugin and Content Manager will: python tools/validate_package.py dist/IPCubed-x.y.z-pcm.zip

Fails (exit 1) on anything that would make "Install from File" reject or break the package:
- archive layout: metadata.json at the archive ROOT (a zip with one top-level folder, like GitHub's "Download ZIP", is rejected
  by KiCad with "The archive does not contain a valid metadata.json file"), only metadata.json + plugins/ + resources/
- metadata.json: UTF-8 without BOM, valid JSON, valid against KiCad's official PCM schema, no download_* keys inside the archive
- plugins/plugin.json: valid against KiCad's official API plugin schema, entrypoint and icons present in the archive
The schemas are downloaded from go.kicad.org (needs network; used by the release workflow).
"""
import io
import json
import re
import struct
import sys
import urllib.request
import zipfile

PCM_SCHEMA = "https://go.kicad.org/pcm/schemas/v1"
API_SCHEMA = "https://go.kicad.org/api/schemas/v1"
errors: list[str] = []


def fail(msg: str):
    errors.append(msg)
    print("  FAIL:", msg)


def ok(msg: str):
    print("  ok:  ", msg)


def schema(url: str, ref: str | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (IPCubed package validator)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            s = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: could not download KiCad's schema {url}: {e}")
        raise SystemExit(1)
    if ref and "$ref" not in s:
        s = {**s, "$ref": f"#/definitions/{ref}"}
    return s


def load_json(z: zipfile.ZipFile, name: str, what: str):
    raw = z.read(name)
    if raw.startswith(b"\xef\xbb\xbf"):
        fail(f"{what} starts with a UTF-8 BOM")
        raw = raw[3:]
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        fail(f"{what} is not valid UTF-8 JSON: {e}")
        return None


def validate(data, sch, what: str):
    import jsonschema
    v = jsonschema.Draft7Validator(sch)
    errs = sorted(v.iter_errors(data), key=lambda e: list(e.path))
    for e in errs:
        fail(f"{what}: {'/'.join(map(str, e.path)) or '(root)'}: {e.message}")
    if not errs:
        ok(f"{what} matches KiCad's official schema")


def png_size(raw: bytes):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", raw[16:24])


def main(path: str) -> int:
    print(f"Checking {path}")
    with open(path, "rb") as f:
        z = zipfile.ZipFile(io.BytesIO(f.read()))
    names = [n for n in z.namelist() if not n.endswith("/")]
    bad = [n for n in names if "\\" in n or n.startswith("/") or ".." in n.split("/")]
    if bad:
        fail(f"unsafe or Windows-style paths in the archive: {bad[:5]}")
    roots = {n.split("/", 1)[0] for n in names}
    if "metadata.json" not in names:
        fail("metadata.json is not at the archive root (KiCad: 'archive does not contain a valid metadata.json')")
    else:
        ok("metadata.json at the archive root")
    extra = roots - {"metadata.json", "plugins", "resources"}
    if extra:
        fail(f"unexpected top-level entries (KiCad expects metadata.json, plugins/, resources/): {sorted(extra)}")

    meta = load_json(z, "metadata.json", "metadata.json") if "metadata.json" in names else None
    if meta is not None:
        validate(meta, schema(PCM_SCHEMA, "Package"), "metadata.json")
        if meta.get("type") != "plugin":
            fail("metadata.json: type must be 'plugin'")
        for ver in meta.get("versions", []):
            leaked = [k for k in ver if k.startswith("download_")]
            if leaked:
                fail(f"metadata.json: {leaked} must only be in the repository metadata, not inside the package")
            if ver.get("runtime") != "ipc":
                fail("metadata.json: versions[].runtime must be 'ipc' for an IPC API plugin")
        if not re.fullmatch(r"[a-zA-Z][-_a-zA-Z0-9.]{0,98}[a-zA-Z0-9]", meta.get("identifier", "")):
            fail("metadata.json: invalid identifier")

    if "plugins/plugin.json" not in names:
        fail("plugins/plugin.json missing (KiCad would not find the plugin)")
    else:
        plug = load_json(z, "plugins/plugin.json", "plugin.json")
        if plug is not None:
            validate(plug, schema(API_SCHEMA, "Plugin"), "plugin.json")
            for act in plug.get("actions", []):
                for key in ("entrypoint",):
                    f = "plugins/" + act.get(key, "")
                    (ok if f in names else fail)(f"action '{act.get('identifier')}': {key} {f} " + ("present" if f in names else "missing"))
                for key in ("icons-light", "icons-dark"):
                    for ico in act.get(key, []):
                        f = "plugins/" + ico
                        if f not in names:
                            fail(f"action '{act.get('identifier')}': {key} {f} missing")
            if meta is not None and plug.get("identifier") != meta.get("identifier"):
                print(f"  note: plugin.json identifier '{plug.get('identifier')}' differs from metadata.json '{meta.get('identifier')}'")

    if "resources/icon.png" in names:
        sz = png_size(z.read("resources/icon.png"))
        if sz is None:
            fail("resources/icon.png is not a PNG")
        elif sz != (64, 64):
            print(f"  note: resources/icon.png is {sz[0]}x{sz[1]} (KiCad recommends 64x64)")
    print("RESULT:", "FAILED" if errors else "OK", f"({len(errors)} problem(s))" if errors else "")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
