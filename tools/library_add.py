#!/usr/bin/env python3
"""Ajoute une nouvelle idee de sortie a la bibliotheque privee (boucle de retour).

C'est l'etape qui fait grossir la bibliotheque : quand une idee nouvelle (trouvee
sur le web, verifiee) n'existe pas encore, on l'ecrit ici. Elle devient alors un
candidat reel pour les futurs lots (plus besoin de la re-trouver / re-inventer).

Respecte les 25 colonnes du CSV existant. La source web est rangee dans
`notes_privees` (le CSV n'a pas de colonne URL dediee). Marque par defaut
`fiabilite_statut=a_verifier`, `visibilite=prive`.

Usage :
  python tools/library_add.py --nom "Lac du Salagou" --zone "Salagou / Clermont-l'Herault" \\
      --nature nature --tags "nature,eau,baignade,panorama,exterieur" \\
      --temps-montpellier "50 min" --budget-min 0 --budget-max 10 \\
      --duree "Demi-journee" --effort Faible --meteo exterieur --saison toute_saison \\
      --reservation non --source "https://..." --notes "Baignade surveillee l'ete."
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY = ROOT / "_bibliotheque_privee" / "bibliotheque_sorties.csv"

COLUMNS = [
    "id", "nom", "titre_lot", "zone", "depart_reference",
    "temps_depuis_montpellier", "temps_depuis_sommieres", "equilibre_trajet",
    "nature_principale", "tags", "budget_min_eur", "budget_max_eur",
    "budget_detail", "duree", "effort", "meteo", "saison", "reservation",
    "fiabilite_statut", "date_derniere_verification", "visibilite",
    "lots_utilises", "source_locale", "source_ids", "notes_privees",
]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower() or "lieu"


def existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["id"] for r in csv.DictReader(fh)}


def build_row(args) -> dict:
    tags = "|".join(t.strip() for t in re.split(r"[,|]", args.tags) if t.strip())
    notes = args.notes or ""
    if args.source:
        notes = (notes + " " if notes else "") + f"source: {args.source}"
    return {
        "id": args.id or slugify(args.nom),
        "nom": args.nom,
        "titre_lot": args.titre_lot or "",
        "zone": args.zone,
        "depart_reference": args.depart,
        "temps_depuis_montpellier": args.temps_montpellier,
        "temps_depuis_sommieres": args.temps_sommieres or "",
        "equilibre_trajet": "",
        "nature_principale": args.nature,
        "tags": tags,
        "budget_min_eur": args.budget_min,
        "budget_max_eur": args.budget_max,
        "budget_detail": args.budget_detail or "",
        "duree": args.duree,
        "effort": args.effort,
        "meteo": args.meteo,
        "saison": args.saison,
        "reservation": args.reservation,
        "fiabilite_statut": args.fiabilite,
        "date_derniere_verification": dt.date.today().isoformat(),
        "visibilite": "prive",
        "lots_utilises": "",
        "source_locale": "web",
        "source_ids": "",
        "notes_privees": notes,
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Ajoute une idee a la bibliotheque privee.")
    p.add_argument("--nom", required=True)
    p.add_argument("--zone", required=True)
    p.add_argument("--nature", required=True,
                   help="nature/patrimoine/mer/culture/activite/village/marche/...")
    p.add_argument("--tags", required=True, help="separes par , ou |")
    p.add_argument("--temps-montpellier", required=True, dest="temps_montpellier")
    p.add_argument("--budget-min", required=True, dest="budget_min")
    p.add_argument("--budget-max", required=True, dest="budget_max")
    p.add_argument("--duree", required=True)
    p.add_argument("--effort", required=True)
    p.add_argument("--meteo", required=True)
    p.add_argument("--saison", default="toute_saison")
    p.add_argument("--reservation", default="non")
    p.add_argument("--source", help="URL de la source web")
    p.add_argument("--notes", help="note privee")
    p.add_argument("--id", help="slug (defaut: depuis --nom)")
    p.add_argument("--titre-lot", dest="titre_lot")
    p.add_argument("--budget-detail", dest="budget_detail")
    p.add_argument("--temps-sommieres", dest="temps_sommieres")
    p.add_argument("--depart", default="Montpellier")
    p.add_argument("--fiabilite", default="a_verifier",
                   help="a_verifier (defaut) / verifie_web")
    p.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv or sys.argv[1:])

    row = build_row(args)
    ids = existing_ids(args.library)
    if row["id"] in ids:
        raise SystemExit(f"id deja present : {row['id']} (choisir --id different).")

    if args.dry_run:
        print("DRY-RUN, ligne qui serait ajoutee :")
        for k in COLUMNS:
            print(f"  {k:28} {row[k]}")
        return

    new_file = not args.library.exists()
    args.library.parent.mkdir(parents=True, exist_ok=True)
    with open(args.library, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        if new_file:
            w.writeheader()
        w.writerow(row)
    print(f"OK -> ajoute '{row['id']}' a {args.library.name} "
          f"(total ideas: {len(ids) + 1}).")


if __name__ == "__main__":
    main()
