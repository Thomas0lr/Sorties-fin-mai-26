#!/usr/bin/env python3
"""Construit un fichier HTML autonome a partir d'un lot JSON + template.html.

Usage:
    python tools/build.py                         # data/lot-soleil-doux.json -> index.html
    python tools/build.py data/lot-xyz.json out.html

Le HTML produit reste un fichier unique (les donnees sont injectees inline),
donc il s'ouvre directement (double-clic) ET fonctionne sur GitHub Pages.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEXT_PLACEHOLDERS = {
    "__TITLE__": "title",
    "__HEADING__": "heading",
    "__INTRO__": "intro",
    "__SECTION_TITLE__": "sectionTitle",
    "__SECTION_INTRO__": "sectionIntro",
    "__NOTE__": "note",
}

LINE_SEP = chr(0x2028)
PARA_SEP = chr(0x2029)


def build(lot_path: Path, out_path: Path) -> None:
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    lot = json.loads(lot_path.read_text(encoding="utf-8"))
    meta = lot["meta"]

    # 1) Textes statiques
    html = template
    for placeholder, key in TEXT_PLACEHOLDERS.items():
        if placeholder not in html:
            raise SystemExit(f"placeholder absent du template: {placeholder}")
        html = html.replace(placeholder, str(meta.get(key, "")))

    # 2) Donnees inline. On neutralise ce qui casserait le <script> :
    #    "</" (fermeture de balise) et les separateurs de ligne U+2028/U+2029.
    data = json.dumps(lot, ensure_ascii=False)
    data = data.replace("</", "<\\/")
    data = data.replace(LINE_SEP, "\\u2028").replace(PARA_SEP, "\\u2029")
    marker = "/*__LOT_JSON__*/ {}"
    if marker not in html:
        raise SystemExit("marqueur de donnees absent du template")
    html = html.replace(marker, f"/*__LOT_JSON__*/ {data}")

    out_path.write_text(html, encoding="utf-8")
    n = len(lot.get("outings", []))
    try:
        shown = out_path.relative_to(ROOT)
    except ValueError:
        shown = out_path
    print(f"OK: {n} sorties -> {shown} ({len(html)//1024} Ko)")


def main() -> None:
    args = sys.argv[1:]
    lot_path = ROOT / (args[0] if args else "data/lot-soleil-doux.json")
    out_path = ROOT / (args[1] if len(args) > 1 else "index.html")
    if not lot_path.exists():
        raise SystemExit(f"lot introuvable: {lot_path}")
    build(lot_path, out_path)


if __name__ == "__main__":
    main()
