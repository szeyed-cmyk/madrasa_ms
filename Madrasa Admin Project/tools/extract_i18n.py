"""1.0.5: rebuild app/locales/en.json from every t("key", "English") in templates and MA.t(...) in JavaScript.

Run after adding text: python tools/extract_i18n.py   (prints keys missing from bn.json / ar.json).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "app" / "locales"
# t('key', 'text') / t("key", "text") / MA.t('key', 'text') - text may contain the other quote kind
PATTERN = re.compile(r"""\bt\(\s*(['"])([a-z0-9_.-]+)\1\s*,\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
# keys kept in lists, e.g. ('dashboard', 'nav.dashboard', 'Dashboard') or ['nav.fees', 'Fees'], passed to t(key, label)
LISTED = re.compile(
    r"""[(\[,]\s*(['"])((?:nav|lp|dash|set|login|auth|common|top|demo|student|att|time)\.[a-z0-9_.]+)\1\s*,\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")"""
)


MA_T = re.compile(r"""MA\.t\(\s*(['"])([a-z0-9_.-]+)\1""")


def js_keys() -> list[str]:
    """Keys the browser needs (MA.t in templates, any t()/listed key in static/js): embedded in each page."""
    keys: set[str] = set()
    for path in sorted((ROOT / "templates").rglob("*.html")):
        keys |= {m.group(2) for m in MA_T.finditer(path.read_text(encoding="utf-8"))}
    for path in sorted((ROOT / "static" / "js").rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        keys |= {m.group(2) for m in [*PATTERN.finditer(text), *LISTED.finditer(text)]}
    return sorted(keys)


def extract() -> dict[str, str]:
    found: dict[str, str] = {}
    files = sorted((ROOT / "templates").rglob("*.html")) + sorted((ROOT / "static" / "js").rglob("*.js"))
    for path in files:
        text_all = path.read_text(encoding="utf-8")
        for m in [*PATTERN.finditer(text_all), *LISTED.finditer(text_all)]:
            key, text = m.group(2), m.group(3) if m.group(3) is not None else m.group(4)
            text = text.replace("\\'", "'").replace('\\"', '"')
            if key in found and found[key] != text:
                print(f"note: {key} has two English texts ({path.name}): {found[key]!r} / {text!r}")
            found.setdefault(key, text)
    return dict(sorted(found.items()))


def main() -> None:
    en = extract()
    (LOCALES / "en.json").write_text(json.dumps(en, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"en.json: {len(en)} keys")
    js = js_keys()
    (LOCALES / "_js_keys.json").write_text(json.dumps(js, indent=0) + "\n", encoding="utf-8")
    print(f"_js_keys.json: {len(js)} keys used by JavaScript")
    for code in ("bn", "ar"):
        path = LOCALES / f"{code}.json"
        have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        missing = [k for k in en if k not in have]
        extra = [k for k in have if k not in en and not k.startswith("_")]
        print(f"{code}.json: {len(have)} keys, missing {len(missing)}, unused {len(extra)}")
        for k in missing:
            print("  missing", k)


if __name__ == "__main__":
    main()
