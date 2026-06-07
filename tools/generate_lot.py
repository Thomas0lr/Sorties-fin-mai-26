#!/usr/bin/env python3
"""Genere un brouillon de lot (data/lot-<slug>.json) avec un LLM local via Ollama.

Principe (important) :
  - Le LLM REDIGE (titres, pitchs, activites, itineraires, idees de creneaux).
  - Les FAITS VERIFIABLES ne viennent pas du LLM :
      * coordonnees GPS  -> geocodage OpenStreetMap / Nominatim
      * horaires & sources -> a confirmer a la main (champs marques "A VERIFIER")
  - Les images ne sont pas generables : placeholder a remplacer dans assets/.

Sortie : un JSON au meme format que data/lot-soleil-doux.json, pret pour build.py.

Pre-requis :
  - Ollama lance :  ollama serve
  - Un modele tire, ex. Gemma 12B (tient dans 16 Go VRAM) :
        ollama pull gemma3:12b        # ou gemma4:12b si Ollama est a jour
  - Connexion internet pour le geocodage (1 requete/seconde).

Usage :
  python tools/generate_lot.py --theme "anti-chaleur" --dates "30-31 mai 2026" \\
      --slug ete-frais --count 12 --region "Herault" --model gemma3:12b
  python tools/generate_lot.py --slug ete-frais --from-raw   # rejoue le post-traitement
  python tools/generate_lot.py --theme x --dry-run            # montre le prompt
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://localhost:11434/api/chat"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "sorties-lot-generator/1.0 (usage prive)"

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
                    "place": {"type": "string"},
                    "commune": {"type": "string"},
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
                "required": ["id", "title", "theme", "place", "commune", "drive",
                             "badges", "pitch", "subtitle", "budget", "budgetDetail",
                             "effort", "duration", "availability", "bestMoment",
                             "activities", "itinerary", "schedule_label",
                             "schedule_suggested"],
            },
        }
    },
    "required": ["outings"],
}

SYSTEM = (
    "Tu es un assistant local francais qui prepare des idees de sorties autour d'une "
    "ville. Tu rediges des fiches engageantes et concretes. Regles STRICTES :\n"
    "- Ne propose QUE des lieux celebres ou bien etablis, que tu connais avec "
    "  certitude. En cas de doute, choisis un lieu PLUS connu. N'invente jamais un "
    "  nom de lieu, de site ou de commune : un lieu invente est une faute grave.\n"
    "- 'place' = nom exact du lieu (ex: 'Grotte de Clamouse'). 'commune' = la ville "
    "  ou village REEL ou il se trouve (ex: 'Saint-Jean-de-Fos'). Ne repete pas le "
    "  lieu dans la commune.\n"
    "- 'id' = slug court en minuscules SANS accent ni espace (ex: 'clamouse-saint-guilhem').\n"
    "- THEME : choisis-le selon le lieu, sans tout mettre dans la meme categorie :\n"
    "    grotte/aven -> theme-cave ; musee/expo -> theme-museum ; monument antique ou "
    "    medieval, abbaye, village historique -> theme-heritage ; plage/mer/etang/port "
    "    -> theme-sea ; jardin/parc/arboretum -> theme-garden ; foret/riviere/sentier/"
    "    lac -> theme-nature.\n"
    "- UNICITE : chaque 'pitch' doit etre unique et commencer par un angle different "
    "  (sensation, histoire, surprise, defi, fraicheur...). N'emploie pas deux fois la "
    "  meme structure de phrase. Les 'badges' doivent differencier les sorties (pas le "
    "  meme trio partout). Chaque fiche doit dire concretement en quoi elle colle au "
    "  THEME DU LOT.\n"
    "- PAS DE FAUSSE PRECISION : n'invente aucune heure precise. 'availability' reste "
    "  'horaires a confirmer'. 'schedule_suggested' = un moment en mots (ex: 'matin', "
    "  'fin d'apres-midi'), jamais une heure chiffree. 'budget' reste general "
    "  (ex: 'gratuit', 'quelques euros').\n"
    "- Reponds UNIQUEMENT via le schema JSON demande."
)


META_ARGS = ("theme", "dates", "audience", "origin", "origin_coords",
             "region", "count", "day_start", "day_end")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "lieu"


def dedupe_destination(place: str, commune: str) -> str:
    place = (place or "").strip()
    commune = (commune or "").strip()
    if not commune or commune.lower() == place.lower() or commune.lower() in place.lower():
        return place or commune
    return f"{place}, {commune}"


def build_prompt(args) -> str:
    return (
        f"Ville de depart : {args.origin}.\n"
        f"Region : {args.region}.\n"
        f"Theme du lot : {args.theme}.\n"
        f"Dates : {args.dates}.\n"
        f"Public : {args.audience}.\n"
        f"Nombre de sorties a proposer : {args.count}.\n"
        "Chaque sortie combine un lieu a visiter ET une activite a faire, accessible "
        "en voiture (idealement moins d'1h) depuis la ville de depart, et doit "
        "repondre clairement au theme du lot. Varie vraiment les categories (mer, "
        "nature, patrimoine, grotte, jardin, musee) et les types d'activite. "
        "Privilegie des lieux connus et surs plutot que des sites obscurs. "
        "Classe-les de la plus pertinente a la moins pertinente pour le theme."
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
        "options": {"temperature": 0.5},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return json.loads(body["message"]["content"])


def haversine_km(a: list, b: list) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _nominatim(query: str, origin: list, max_km: float) -> list | None:
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM_URL}?{params}",
                                 headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            hits = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! geocodage erreur ({query}): {exc}", file=sys.stderr)
        return None
    time.sleep(1.1)  # politesse Nominatim : 1 req/s
    if not hits:
        return None
    coords = [round(float(hits[0]["lat"]), 5), round(float(hits[0]["lon"]), 5)]
    # Garde-fou : un meme nom existe ailleurs en France (ex: "Audierne" en Bretagne).
    if haversine_km(origin, coords) > max_km:
        print(f"  ! geocodage rejete (>{max_km:.0f} km) : {query} -> {coords}", file=sys.stderr)
        return None
    return coords


def geocode(place: str, commune: str, region: str,
            origin: list, max_km: float) -> tuple[list | None, bool]:
    """Renvoie (coords, precise). precise=False si on a du retomber sur la commune.

    On NE force PAS la region dans la requete principale : le modele propose
    souvent des lieux dans les departements voisins (Gard, Bouches-du-Rhone...),
    et un mauvais hint de region fait echouer le geocodage. La commune + 'France'
    suffit a desambiguiser ; la region ne sert que de repli.
    """
    precise_queries = [
        f"{place}, {commune}, France",
        f"{place}, France",
    ]
    for q in precise_queries:
        if place:
            coords = _nominatim(q, origin, max_km)
            if coords:
                return coords, True
    # repli : la commune seule (le lieu precis est peut-etre mal nomme/inexistant)
    for q in (f"{commune}, France", f"{commune}, {region}, France"):
        if commune:
            coords = _nominatim(q, origin, max_km)
            if coords:
                return coords, False
    return None, False


def assemble(raw: dict, args) -> dict:
    outings, schedule_plans, review = [], {}, []
    seen_ids: set[str] = set()
    for o in raw["outings"]:
        place = o.get("place", "").strip()
        commune = o.get("commune", "").strip()
        destination = dedupe_destination(place, commune)

        oid = slugify(o.get("id") or destination)
        base = oid
        n = 2
        while oid in seen_ids:
            oid = f"{base}-{n}"
            n += 1
        seen_ids.add(oid)

        if args.dry_run:
            coords, precise = list(args.origin_coords), True
        else:
            coords, precise = geocode(place, commune, args.region,
                                      list(args.origin_coords), args.max_km)
        if coords is None:
            review.append(f"!! EXISTENCE A VERIFIER (geocodage echoue) -> {oid} : {destination}")
            coords = list(args.origin_coords)
        elif not precise:
            review.append(f"!  coords approximatives (commune seule) -> {oid} : {destination}")

        outings.append({
            "id": oid,
            "title": o["title"],
            "emoji": "",
            "theme": o["theme"],
            "image": "assets/PLACEHOLDER.jpg",
            "imageLabel": destination,
            "drive": o["drive"],
            "destination": destination,
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
                "placeToVisit": {"name": place or destination, "sourceLabel": "A VERIFIER", "source": ""},
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
    p.add_argument("--region", default="Herault", help="region (repli de geocodage seulement)")
    p.add_argument("--max-km", type=float, default=250.0,
                   help="rayon max accepte autour de l'origine (rejette les faux positifs)")
    p.add_argument("--count", type=int, default=12)
    p.add_argument("--day-start", type=int, default=8)
    p.add_argument("--day-end", type=int, default=20)
    p.add_argument("--model", default="gemma3:12b",
                   help="tag Ollama (verifier avec `ollama list`)")
    p.add_argument("--brief", type=Path, help="fichier texte ajoute au prompt")
    p.add_argument("--dry-run", action="store_true",
                   help="affiche le prompt sans appeler le modele ni geocoder")
    p.add_argument("--from-raw", action="store_true",
                   help="rejoue le post-traitement depuis le cache brut, sans LLM")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv or sys.argv[1:])
    raw_cache = ROOT / f"data/.raw-{args.slug}.json"

    if args.dry_run:
        prompt = build_prompt(args)
        print("=== SYSTEM ===\n" + SYSTEM + "\n\n=== PROMPT ===\n" + prompt)
        print(f"\n(modele cible: {args.model} ; dry-run : aucun appel reseau)")
        return

    if args.from_raw:
        if not raw_cache.exists():
            raise SystemExit(f"cache brut absent : {raw_cache}")
        cached = json.loads(raw_cache.read_text(encoding="utf-8"))
        raw = {"outings": cached["outings"]}
        # Restaure le contexte (theme, dates...) capture lors de la generation,
        # pour que le rejeu reproduise le meme meta sans re-passer les flags.
        for key, val in cached.get("args", {}).items():
            setattr(args, key, val)
        print(f"-> rejeu depuis {raw_cache.name} ({len(raw['outings'])} sorties)", file=sys.stderr)
    else:
        prompt = build_prompt(args)
        if args.brief and args.brief.exists():
            prompt += "\n\nContraintes additionnelles :\n" + args.brief.read_text(encoding="utf-8")
        print(f"-> Appel Ollama ({args.model})...", file=sys.stderr)
        raw = call_ollama(args.model, prompt)
        cached = {"args": {k: getattr(args, k) for k in META_ARGS}, "outings": raw["outings"]}
        raw_cache.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> {len(raw['outings'])} sorties recues (brut: {raw_cache.name}), geocodage...",
              file=sys.stderr)

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
