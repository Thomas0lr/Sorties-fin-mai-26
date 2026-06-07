#!/usr/bin/env python3
"""Genere un brouillon de lot (data/lot-<slug>.json) avec un LLM local via Ollama.

Principe (important) :
  - Le LLM REDIGE (titres, pitchs, activites, itineraires, idees de creneaux).
  - Les FAITS VERIFIABLES ne viennent pas du LLM :
      * coordonnees GPS  -> geocodage OpenStreetMap / Nominatim
      * horaires & sources -> a confirmer a la main (champs marques "verified": false)
  - Les images ne sont pas generables : placeholder a remplacer dans assets/.

Sortie : un JSON au meme format que data/lot-soleil-doux.json, pret pour build.py.

Pre-requis :
  - Ollama lance (https://ollama.com) :  ollama serve
  - Un modele tire, ex. Gemma 12B (tient dans 16 Go VRAM en Q4) :
        ollama pull gemma4:12b      # adapter le tag a `ollama list`
  - Connexion internet pour le geocodage (1 requete/seconde, cache local).

Usage :
  python tools/generate_lot.py --theme "anti-chaleur" --dates "30-31 mai 2026" \\
      --slug ete-frais --count 12 --model gemma4:12b
  python tools/generate_lot.py --brief tools/brief_exemple.txt --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://localhost:11434/api/chat"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "sorties-lot-generator/1.0 (usage prive)"

# Schema impose au modele : il DOIT renvoyer cette structure (sortie JSON Ollama).
OUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "outings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "theme": {
                        "type": "string",
                        "enum": ["theme-sea", "theme-nature", "theme-heritage",
                                 "theme-cave", "theme-garden", "theme-museum"],
                    },
                    "destination": {"type": "string"},
                    "geocode_query": {"type": "string"},
                    "drive": {"type": "string"},
                    "badges": {"type": "array", "items": {"type": "string"}},
                    "pitch": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "budget": {"type": "string"},
                    "budgetDetail": {"type": "string"},
                    "effort": {"type": "string"},
                    "duration": {"type": "string"},
                    "availability": {"type": "string"},
                    "bestMoment": {"type": "string"},
                    "activities": {"type": "array", "items": {"type": "string"}},
                    "itinerary": {"type": "array", "items": {"type": "string"}},
                    "schedule_label": {"type": "string"},
                    "schedule_suggested": {"type": "string"},
                },
                "required": ["id", "title", "theme", "destination", "geocode_query",
                             "drive", "badges", "pitch", "subtitle", "budget",
                             "budgetDetail", "effort", "duration", "availability",
                             "bestMoment", "activities", "itinerary",
                             "schedule_label", "schedule_suggested"],
            },
        }
    },
    "required": ["outings"],
}

SYSTEM = (
    "Tu es un assistant local francais qui prepare des idees de sorties autour d'une "
    "ville. Tu rediges des fiches engageantes et concretes. Regles STRICTES :\n"
    "- N'invente JAMAIS d'horaire precis, de prix exact, ni d'URL de source : reste "
    "  general (ex: 'horaires a confirmer', 'gratuit ou quelques euros').\n"
    "- 'geocode_query' = nom du lieu + commune, le plus precis possible pour une "
    "  recherche cartographique (ex: 'Grotte de Clamouse, Saint-Jean-de-Fos').\n"
    "- 'id' = slug minuscule sans accent ni espace (ex: 'clamouse-saint-guilhem').\n"
    "- Reponds UNIQUEMENT via le schema JSON demande."
)


def build_prompt(args) -> str:
    return (
        f"Ville de depart : {args.origin}.\n"
        f"Theme du lot : {args.theme}.\n"
        f"Dates : {args.dates}.\n"
        f"Public : {args.audience}.\n"
        f"Nombre de sorties a proposer : {args.count}.\n"
        "Chaque sortie combine un lieu a visiter ET une activite a faire, accessible "
        "en voiture depuis la ville de depart. Varie les themes (mer, nature, "
        "patrimoine, grotte, jardin, musee). Classe-les de la plus pertinente a la "
        "moins pertinente pour le theme."
    )


def call_ollama(model: str, prompt: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "format": OUTING_SCHEMA,
        "stream": False,
        "options": {"temperature": 0.6},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return json.loads(body["message"]["content"])


def geocode(query: str) -> list | None:
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM_URL}?{params}",
                                 headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            hits = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! geocodage echoue ({query}): {exc}", file=sys.stderr)
        return None
    if not hits:
        return None
    return [round(float(hits[0]["lat"]), 5), round(float(hits[0]["lon"]), 5)]


def assemble(raw: dict, args) -> dict:
    outings, schedule_plans, review = [], {}, []
    for o in raw["outings"]:
        oid = o["id"]
        coords = None if args.dry_run else geocode(o["geocode_query"])
        if not args.dry_run:
            time.sleep(1.1)  # politesse Nominatim : 1 req/s max
        if coords is None:
            review.append(f"coords manquantes -> {oid} ({o['geocode_query']})")
            coords = list(args.origin_coords)
        outings.append({
            "id": oid,
            "title": o["title"],
            "emoji": "",
            "theme": o["theme"],
            "image": "assets/PLACEHOLDER.jpg",
            "imageLabel": o["destination"],
            "drive": o["drive"],
            "destination": o["destination"],
            "coords": coords,
            "badges": o["badges"],
            "pitch": o["pitch"],
            "subtitle": o["subtitle"],
            "budget": o["budget"],
            "budgetDetail": o["budgetDetail"],
            "effort": o["effort"],
            "duration": o["duration"],
            "availability": o["availability"],
            "bestMoment": o["bestMoment"],
            "activities": o["activities"],
            "itinerary": o["itinerary"],
            "proof": {
                "placeToVisit": {"name": o["destination"], "sourceLabel": "A VERIFIER", "source": ""},
                "activityToDo": {"name": o["title"], "sourceLabel": "A VERIFIER", "source": ""},
            },
            "sources": [["A VERIFIER - ajouter la source officielle", ""]],
        })
        schedule_plans[oid] = {
            "windows": [[args.day_start, args.day_end]],
            "recommended": [[args.day_start, args.day_end]],
            "label": o["schedule_label"],
            "suggested": o["schedule_suggested"],
        }
        review.append(f"horaires + source a confirmer -> {oid}")
        review.append(f"image reelle a fournir -> {oid} (assets/{oid}.jpg)")

    return {
        "meta": {
            "slug": args.slug,
            "title": f"Lot {args.theme} - {args.dates}",
            "heading": f"Lot {args.theme} {args.dates}",
            "intro": f"Brouillon genere localement. {args.audience}, au depart de {args.origin}.",
            "sectionTitle": f"Les {len(outings)} sorties a choisir",
            "sectionIntro": "Chaque fiche combine un lieu a visiter et une activite, "
                            "avec budget, trajet et creneaux indicatifs.",
            "note": "<strong>Brouillon a verifier :</strong> horaires, sources et "
                    "images doivent etre confirmes avant publication.",
            "origin": list(args.origin_coords),
            "originLabel": args.origin,
            "dayStart": args.day_start,
            "dayEnd": args.day_end,
        },
        "outings": outings,
        "schedulePlans": schedule_plans,
        "_review": review,
    }


def parse_args(argv):
    p = argparse.ArgumentParser(description="Genere un brouillon de lot via Ollama.")
    p.add_argument("--theme", default="anti-chaleur")
    p.add_argument("--dates", default="a definir")
    p.add_argument("--slug", default="nouveau-lot")
    p.add_argument("--audience", default="Pour 2-3 personnes")
    p.add_argument("--origin", default="Montpellier")
    p.add_argument("--origin-coords", nargs=2, type=float, default=[43.6108, 3.8767],
                   metavar=("LAT", "LON"))
    p.add_argument("--count", type=int, default=12)
    p.add_argument("--day-start", type=int, default=8)
    p.add_argument("--day-end", type=int, default=20)
    p.add_argument("--model", default="gemma4:12b",
                   help="tag Ollama (verifier avec `ollama list`)")
    p.add_argument("--brief", type=Path, help="fichier texte ajoute au prompt")
    p.add_argument("--dry-run", action="store_true",
                   help="affiche le prompt sans appeler le modele ni geocoder")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv or sys.argv[1:])
    prompt = build_prompt(args)
    if args.brief and args.brief.exists():
        prompt += "\n\nContraintes additionnelles :\n" + args.brief.read_text(encoding="utf-8")

    if args.dry_run:
        print("=== SYSTEM ===\n" + SYSTEM + "\n\n=== PROMPT ===\n" + prompt)
        print(f"\n(modele cible: {args.model} ; dry-run : aucun appel reseau)")
        return

    print(f"-> Appel Ollama ({args.model})...", file=sys.stderr)
    raw = call_ollama(args.model, prompt)
    print(f"-> {len(raw['outings'])} sorties recues, geocodage...", file=sys.stderr)
    lot = assemble(raw, args)

    out = ROOT / f"data/lot-{args.slug}.json"
    out.write_text(json.dumps(lot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nOK -> {out.relative_to(ROOT)}")
    print("\nA VERIFIER AVANT PUBLICATION :")
    for item in lot["_review"]:
        print("  - " + item)
    print(f"\nEnsuite : python tools/build.py {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
