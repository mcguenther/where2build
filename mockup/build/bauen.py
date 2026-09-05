#!/usr/bin/env python3
"""Assemble mockup/standort-mockup.html from the fragments beside this script.

The mockup is one file so it can be published as an artifact, but editing a
830 kB file with a base64 aerial photograph inside it by hand is how fixes get
lost. Everything is edited here and assembled by running this.

    python3 mockup/build/bauen.py

`daten.json` holds what was fetched from ALKIS, the noise survey and the aerial
photo service; it is not generated here, because building the page must not
depend on those services being up.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "standort-mockup.html"


def main() -> None:
    read = lambda name: (HERE / name).read_text(encoding="utf-8")
    counters, checks = read("pruefliste.html").split("\n@@@\n")
    body = (read("koerper.html")
            .replace("@@ZAEHLBAND@@", counters)
            .replace("@@PRUEFLISTE@@", checks))
    data = json.loads(read("daten.json"))

    page = (
        read("kopf.html")
        + body
        + '\n<script id="daten" type="application/json">'
        + json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        + "</script>\n"
        + "<script>\n" + read("karte.js") + "\n</script>\n"
        + "<script>\n" + read("suche.js") + "\n</script>\n"
    )
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT.relative_to(HERE.parent.parent)}: {len(page) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
