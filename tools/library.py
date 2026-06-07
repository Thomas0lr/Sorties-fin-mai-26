#!/usr/bin/env python3
"""Chargeur de la bibliotheque privee de sorties (`bibliotheque_sorties.csv`).

Source de verite PRIVEE : ~111 idees reelles, taguees, autour de Montpellier.
Elle sert de source PRIMAIRE au generateur de lots : on y pioche de vrais lieux
(zero hallucination) avant de demander de nouvelles idees au web/LLM.

Ce module ne fait que lire, filtrer et classer. Il NE redige pas la prose
(pitch, itineraire) : c'est le role du LLM en aval. Il n'ecrit jamais de donnee
privee dans un lot public (seul un sous-ensemble de champs factuels est exporte).
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Emplacement par defaut : bibliotheque privee a la racine du projet (hors depot).
DEFAULT_LIBRARY = Path("_bibliotheque_privee") / "bibliotheque_sorties.csv"


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", strip_accents(text)).strip("-").lower()
    return text or "lieu"


def first_variant(value: str) -> str:
    """Les doublons fusionnes stockent les variantes avec '|' ; on prend la 1ere."""
    return (value or "").split("|")[0].strip()


def parse_minutes(text: str) -> int | None:
    """'45 min' -> 45 ; '1h20 a 1h30' -> 80 (premiere valeur)."""
    text = first_variant(text).lower()
    m = re.search(r"(\d+)\s*h\s*(\d+)?", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    m = re.search(r"(\d+)\s*min", text)
    if m:
        return int(m.group(1))
    return None


def theme_class(nature: str, tags: set[str]) -> str:
    """Classe de theme (couleur/template) deduite de la nature + des tags."""
    if tags & {"grotte"}:
        return "theme-cave"
    if tags & {"musee", "expo", "art_contemporain", "patrimoine_scientifique",
               "mediatheque", "astronomie", "industrie"}:
        return "theme-museum"
    if tags & {"jardin", "botanique", "parc", "domaine", "vignoble"}:
        return "theme-garden"
    if tags & {"mer", "lagune", "bassin_thau", "salins", "aquarium", "sete",
               "marais", "petite_camargue"} or nature == "mer":
        return "theme-sea"
    # eau douce / baignade : nature, meme si un tag patrimoine traine
    if tags & {"baignade", "riviere", "source", "cascade", "lac"}:
        return "theme-nature"
    if nature in ("patrimoine", "village", "culture", "marche") or tags & {
        "patrimoine", "archeologie", "chateau", "abbaye", "ville_close",
        "antique", "aqueduc", "village", "grand_site", "capitelles", "moulins",
    }:
        return "theme-heritage"
    return "theme-nature"


# Profils de filtrage par theme de lot. 'prefer' = tags qui font monter le score ;
# 'meteo_ok' = valeurs de la colonne meteo qui collent ; 'avoid' = exclusion dure.
THEME_PROFILES: dict[str, dict] = {
    "anti-chaleur": {
        "prefer": {"eau", "mer", "grotte", "ombre", "jardin", "aquarium",
                   "lagune", "source", "abrite", "abrite_partiel", "bassin_thau",
                   "botanique", "marais"},
        "meteo_ok": {"abrite", "abrite_partiel", "ombre", "hors_grosse_chaleur"},
        "avoid": {"chaleur"},
    },
    "fraicheur": {"alias": "anti-chaleur"},
    "soleil-doux": {"alias": "anti-chaleur"},
    "patrimoine": {
        "prefer": {"patrimoine", "archeologie", "musee", "village", "abbaye",
                   "chateau", "antique", "aqueduc", "ville_close", "grand_site",
                   "capitelles", "moulins"},
        "meteo_ok": set(), "avoid": set(),
    },
    "nature": {
        "prefer": {"nature", "balade", "panorama", "garrigue", "jardin",
                   "randonnee", "eau", "oiseaux", "pic_saint_loup"},
        "meteo_ok": set(), "avoid": set(),
    },
    "mer": {
        "prefer": {"mer", "lagune", "bassin_thau", "sete", "aquarium",
                   "salins", "petite_camargue"},
        "meteo_ok": set(), "avoid": set(),
    },
    "famille": {
        "prefer": {"famille", "aquarium", "base_loisirs", "jardin", "insolite",
                   "grotte", "accessible"},
        "meteo_ok": set(), "avoid": set(),
    },
    "insolite": {
        "prefer": {"insolite", "spectaculaire", "panorama", "grotte",
                   "astronomie", "immersif"},
        "meteo_ok": set(), "avoid": set(),
    },
    "petit-budget": {
        "prefer": {"budget_gratuit", "petit_budget"},
        "meteo_ok": set(), "avoid": set(),
    },
}


@dataclass
class Candidate:
    id: str
    nom: str
    zone: str
    nature: str
    tags: list[str]
    drive: str
    drive_minutes: int | None
    budget_min: str
    budget_max: str
    budget_detail: str
    duree: str
    effort: str
    meteo: str
    saison: str
    reservation: str
    fiabilite: str
    lots_utilises: str
    score: float = 0.0
    theme: str = field(default="theme-nature")

    @property
    def geocode_place(self) -> str:
        return first_variant(self.zone.split("/")[0])


def load_candidates(csv_path: Path) -> list[Candidate]:
    out: list[Candidate] = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            tags = [t for t in r.get("tags", "").split("|") if t]
            out.append(Candidate(
                id=slugify(r["id"]),
                nom=r.get("nom", "").strip(),
                zone=r.get("zone", "").strip(),
                nature=r.get("nature_principale", "").strip(),
                tags=tags,
                drive=first_variant(r.get("temps_depuis_montpellier", "")),
                drive_minutes=parse_minutes(r.get("temps_depuis_montpellier", "")),
                budget_min=first_variant(r.get("budget_min_eur", "")),
                budget_max=first_variant(r.get("budget_max_eur", "")),
                budget_detail=first_variant(r.get("budget_detail", "")),
                duree=first_variant(r.get("duree", "")),
                effort=first_variant(r.get("effort", "")),
                meteo=first_variant(r.get("meteo", "")),
                saison=r.get("saison", "").strip(),
                reservation=first_variant(r.get("reservation", "")),
                fiabilite=r.get("fiabilite_statut", "").strip(),
                lots_utilises=r.get("lots_utilises", "").strip(),
            ))
    return out


def resolve_profile(theme: str) -> dict:
    """Map un theme libre vers un profil de filtrage."""
    key = slugify(theme)
    prof = THEME_PROFILES.get(key)
    if prof and "alias" in prof:
        prof = THEME_PROFILES[prof["alias"]]
    if prof:
        return prof
    # Fallback : construire un profil a partir des mots du theme qui sont des tags.
    words = set(strip_accents(theme).lower().replace("-", " ").split())
    return {"prefer": words, "meteo_ok": set(), "avoid": set()}


def score_candidate(c: Candidate, profile: dict) -> float:
    tagset = set(c.tags)
    if tagset & profile.get("avoid", set()):
        return -1.0
    score = 2.0 * len(tagset & profile.get("prefer", set()))
    if c.meteo in profile.get("meteo_ok", set()):
        score += 2.0
    # petit bonus pour les sorties proches (logistique plus simple)
    if c.drive_minutes is not None and c.drive_minutes <= 45:
        score += 0.5
    return score


def select(csv_path: Path, theme: str, count: int,
           max_minutes: int | None = None,
           exclude_ids: set[str] | None = None) -> list[Candidate]:
    """Renvoie jusqu'a `count` candidats pertinents, classes, varies en theme."""
    profile = resolve_profile(theme)
    exclude = exclude_ids or set()
    pool = []
    for c in load_candidates(csv_path):
        if c.id in exclude:
            continue
        if max_minutes is not None and c.drive_minutes is not None \
                and c.drive_minutes > max_minutes:
            continue
        c.score = score_candidate(c, profile)
        c.theme = theme_class(c.nature, set(c.tags))
        if c.score < 0:
            continue
        pool.append(c)
    pool.sort(key=lambda x: x.score, reverse=True)

    # Diversite : on evite de prendre 10 fois le meme theme-* d'affilee.
    selected, per_theme = [], {}
    for c in pool:
        if len(selected) >= count:
            break
        if per_theme.get(c.theme, 0) >= max(2, count // 3):
            continue
        selected.append(c)
        per_theme[c.theme] = per_theme.get(c.theme, 0) + 1
    # completer si la contrainte de diversite a trop reduit
    if len(selected) < count:
        for c in pool:
            if len(selected) >= count:
                break
            if c not in selected:
                selected.append(c)
    return selected[:count]


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Teste le filtrage de la bibliotheque.")
    p.add_argument("--theme", default="anti-chaleur")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--max-minutes", type=int, default=None)
    p.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    args = p.parse_args()
    res = select(args.library, args.theme, args.count, args.max_minutes)
    print(f"{len(res)} candidats pour '{args.theme}' :")
    for c in res:
        print(f"  [{c.score:4.1f}] {c.theme:14} {c.drive:>10}  {c.nom}")
        print(f"         tags: {'|'.join(c.tags[:8])}")
