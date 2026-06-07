#!/usr/bin/env python3
"""Compose un lot a partir de la BIBLIOTHEQUE privee (source primaire).

Flux :
  1. Selection : filtre/classe les vrais lieux de `bibliotheque_sorties.csv`.
  2. Redaction : le LLM ecrit la prose (pitch, sous-titre, activites, itineraire)
     UNIQUEMENT a partir des faits fournis. Il n'invente aucun lieu ni fait.
  3. Geocodage : sur des noms reels -> coordonnees fiables (garde-fou distance).
  4. Assemblage : lot JSON au format de build.py + liste `_review`.

Le gap-fill web/LLM (idees nouvelles) et la boucle de retour vers le CSV sont
des etapes ulterieures (voir --gap, a venir).

Usage :
  python tools/compose_lot.py --theme "anti-chaleur" --dates "30-31 mai 2026" \\
      --slug soleil --count 10 --model gemma4:12b
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import library
import generate_lot as g

ROOT = Path(__file__).resolve().parent.parent

PROSE_SCHEMA = {
    "type": "object",
    "properties": {
        "fiches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pitch": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "activities": {"type": "array", "items": {"type": "string"}},
                    "itinerary": {"type": "array", "items": {"type": "string"}},
                    "schedule_suggested": {"type": "string"},
                },
                "required": ["id", "pitch", "subtitle", "activities",
                             "itinerary", "schedule_suggested"],
            },
        }
    },
    "required": ["fiches"],
}

PROSE_SYSTEM = (
    "Tu es un redacteur francais de fiches de sorties. On te donne des lieux REELS "
    "avec leurs faits (lieu, trajet, budget, duree, meteo, tags). Ta SEULE tache "
    "est d'ecrire une prose engageante pour CHAQUE lieu fourni. Regles STRICTES :\n"
    "- N'invente AUCUN fait : pas d'horaire precis, pas de prix, pas de lieu "
    "  supplementaire. Sers-toi uniquement des infos donnees.\n"
    "- Garde le meme 'id' que celui fourni, pour chaque fiche.\n"
    "- 'pitch' (1-2 phrases) : unique, accroche differente a chaque fois, et dit "
    "  en quoi la sortie colle au theme du lot.\n"
    "- 'subtitle' : court complement concret, pas une repetition du titre.\n"
    "- 'activities' : 2-4 choses concretes a faire sur place.\n"
    "- 'itinerary' : 3-5 etapes simples de la journee.\n"
    "- 'schedule_suggested' : un moment en mots ('matin', 'fin d'apres-midi'), "
    "  jamais une heure chiffree.\n"
    "- Reponds UNIQUEMENT via le schema JSON, une entree par lieu fourni."
)


def facts_block(cands: list[library.Candidate]) -> str:
    lines = []
    for c in cands:
        lines.append(
            f"- id: {c.id}\n"
            f"  lieu: {c.nom}\n"
            f"  zone: {c.zone}\n"
            f"  trajet depuis Montpellier: {c.drive}\n"
            f"  budget: {c.budget_min}-{c.budget_max} EUR ({c.budget_detail})\n"
            f"  duree: {c.duree} ; effort: {c.effort} ; meteo: {c.meteo}\n"
            f"  tags: {', '.join(c.tags)}"
        )
    return "\n".join(lines)


def write_prose(model: str, theme: str, cands: list[library.Candidate]) -> dict:
    prompt = (
        f"Theme du lot : {theme}.\n"
        f"Redige une fiche pour chacun de ces {len(cands)} lieux reels "
        f"(garde les 'id') :\n\n{facts_block(cands)}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": PROSE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "format": PROSE_SCHEMA,
        "stream": False,
        "options": {"temperature": 0.6, "num_ctx": 16384, "num_predict": 8192},
    }
    if "thinking" in g.model_capabilities(model):
        payload["think"] = False
    body = g._ollama_post("/api/chat", payload, 1200)
    content = body["message"]["content"]
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        dbg = ROOT / "data" / f".debug-prose-{model.replace(':', '_')}.txt"
        dbg.write_text(content, encoding="utf-8")
        raise SystemExit(f"Prose non parsable ({exc}, done={body.get('done_reason')!r}). "
                         f"Brut: {dbg.name}. Baisser --count si tronque.") from exc
    return {f["id"]: f for f in data["fiches"]}


def badges_from_tags(c: library.Candidate) -> list[str]:
    pretty = {
        "budget_gratuit": "Gratuit", "petit_budget": "Petit budget",
        "abrite": "Abrite", "abrite_partiel": "Ombre partielle",
        "eau": "Eau", "mer": "Mer", "grotte": "Grotte fraiche",
        "famille": "Famille", "panorama": "Panorama", "musee": "Musee",
        "jardin": "Jardin", "village": "Village", "patrimoine": "Patrimoine",
        "randonnee": "Rando", "insolite": "Insolite", "aquarium": "Aquarium",
    }
    out = []
    for t in c.tags:
        if t in pretty and pretty[t] not in out:
            out.append(pretty[t])
        if len(out) >= 3:
            break
    return out or [c.nature.capitalize() or "Sortie"]


def compose(args) -> dict:
    cands = library.select(args.library, args.theme, args.count,
                           max_minutes=args.max_minutes)
    if not cands:
        raise SystemExit(f"Aucun candidat en bibliotheque pour '{args.theme}'.")
    print(f"-> {len(cands)} candidats bibliotheque ; redaction LLM ({args.model})...",
          file=sys.stderr)
    prose = write_prose(args.model, args.theme, cands)

    outings, schedule_plans, review = [], {}, []
    origin = list(args.origin_coords)
    for c in cands:
        p = prose.get(c.id, {})
        coords, precise = g.geocode(c.geocode_place, "", args.region, origin, args.max_km)
        if coords is None:
            review.append(f"!! coords introuvables -> {c.id} ({c.geocode_place})")
            coords = origin
        elif not precise:
            review.append(f"!  coords approximatives -> {c.id} ({c.geocode_place})")
        budget = (f"{c.budget_min}-{c.budget_max} EUR" if c.budget_min and c.budget_max
                  else (c.budget_min or "a preciser"))
        outings.append({
            "id": c.id, "title": c.nom, "emoji": "", "theme": c.theme,
            "image": "assets/PLACEHOLDER.jpg", "imageLabel": c.nom,
            "drive": c.drive or "a preciser", "destination": c.geocode_place,
            "coords": coords, "badges": badges_from_tags(c),
            "pitch": p.get("pitch", ""), "subtitle": p.get("subtitle", ""),
            "budget": budget, "budgetDetail": c.budget_detail or "a preciser",
            "effort": c.effort or "a preciser",
            "duration": c.duree or "a preciser",
            "availability": "horaires a confirmer",
            "bestMoment": p.get("schedule_suggested", ""),
            "activities": p.get("activities", []),
            "itinerary": p.get("itinerary", []),
            "proof": {
                "placeToVisit": {"name": c.nom, "sourceLabel": "A VERIFIER", "source": ""},
                "activityToDo": {"name": c.nom, "sourceLabel": "A VERIFIER", "source": ""},
            },
            "sources": [["A VERIFIER - source officielle", ""]],
        })
        schedule_plans[c.id] = {
            "windows": [[args.day_start, args.day_end]],
            "recommended": [[args.day_start, args.day_end]],
            "label": "horaires a confirmer",
            "suggested": p.get("schedule_suggested", ""),
        }
        review.append(f"horaires + source a confirmer -> {c.id}")
        review.append(f"image reelle a fournir -> {c.id} (assets/{c.id}.jpg)")
        if c.reservation and c.reservation.lower() not in ("non", ""):
            review.append(f"reservation : {c.reservation} -> {c.id}")

    return {
        "meta": {
            "slug": args.slug,
            "title": f"Lot {args.theme} - {args.dates}",
            "heading": f"Lot {args.theme} {args.dates}",
            "intro": f"Compose depuis la bibliotheque. {args.audience}, au depart de {args.origin}.",
            "sectionTitle": f"Les {len(outings)} sorties a choisir",
            "sectionIntro": "Lieux issus de la bibliotheque verifiee, prose redigee "
                            "sur faits reels ; horaires et sources a confirmer.",
            "note": "<strong>Brouillon a verifier :</strong> horaires, sources et "
                    "images a confirmer avant publication.",
            "origin": origin, "originLabel": args.origin,
            "dayStart": args.day_start, "dayEnd": args.day_end,
        },
        "outings": outings, "schedulePlans": schedule_plans,
        "_source": "bibliotheque", "_review": review,
    }


def parse_args(argv):
    p = argparse.ArgumentParser(description="Compose un lot depuis la bibliotheque.")
    p.add_argument("--theme", default="anti-chaleur")
    p.add_argument("--dates", default="a definir")
    p.add_argument("--slug", default="nouveau-lot")
    p.add_argument("--audience", default="Pour 2-3 personnes")
    p.add_argument("--origin", default="Montpellier")
    p.add_argument("--origin-coords", nargs=2, type=float, default=[43.6108, 3.8767])
    p.add_argument("--region", default="Herault")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--max-minutes", type=int, default=None)
    p.add_argument("--max-km", type=float, default=250.0)
    p.add_argument("--day-start", type=int, default=8)
    p.add_argument("--day-end", type=int, default=20)
    p.add_argument("--model", default="gemma4:12b")
    p.add_argument("--library", type=Path, default=ROOT / library.DEFAULT_LIBRARY)
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv or sys.argv[1:])
    lot = compose(args)
    out = ROOT / f"data/lot-{args.slug}.json"
    out.write_text(json.dumps(lot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nOK -> {out.relative_to(ROOT)} ({len(lot['outings'])} sorties)")
    print("\nA VERIFIER AVANT PUBLICATION :")
    for item in lot["_review"]:
        print("  - " + item)
    print(f"\nEnsuite : python tools/build.py {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
