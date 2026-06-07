# Pipeline de génération des lots (LLM local)

Architecture **données / présentation séparées** : un lot = un fichier JSON ;
le HTML final est *construit* à partir d'un template réutilisable. Le HTML produit
reste **un fichier unique** (s'ouvre au double-clic et marche sur GitHub Pages).

```
data/lot-*.json   ──┐
                    ├──►  tools/build.py  ──►  index.html
template.html  ─────┘
        ▲
        │  généré (brouillon)
        │
tools/generate_lot.py  ──►  Ollama (LLM local)  +  géocodage OpenStreetMap
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `template.html` | Le gabarit : tout le CSS, le rendu JS et les cartes. Données remplacées par des placeholders. |
| `data/lot-*.json` | Un lot : `meta` (titres, intro, origine) + `outings[]` + `schedulePlans`. |
| `tools/build.py` | Fusionne un lot + le template → HTML autonome. |
| `tools/generate_lot.py` | Brouillon de lot via Ollama (rédaction) + Nominatim (coordonnées). |
| `tools/_extract.mjs` | One-shot : a servi à extraire le lot existant vers JSON. |
| `tools/_make_template.mjs` | One-shot : a servi à dériver `template.html` depuis `index.html`. |

## Workflow pour un nouveau lot

```bash
# 1. Brouillon généré localement (le LLM rédige, OSM géocode)
python tools/generate_lot.py --theme "anti-chaleur" --dates "30-31 mai 2026" \
    --slug ete-frais --count 12 --model gemma4:12b

# 2. VÉRIFICATION HUMAINE (cf. ci-dessous) — éditer data/lot-ete-frais.json

# 3. Construire la page
python tools/build.py data/lot-ete-frais.json index.html

# 4. Publier
git add -A && git commit -m "Publish lot ete-frais" && git push origin HEAD:main
```

Reconstruire le lot actuel : `python tools/build.py` (défaut = `data/lot-soleil-doux.json`).

## Modèle conseillé (contrainte 16 Go VRAM — RX 6900 XT)

- **Gemma 12B** (Q4) : ~8-9 Go en VRAM, le meilleur rapport qualité/français.
  `ollama pull gemma4:12b` (adapter le tag à ce que montre `ollama list`).
- Replis qui tiennent aussi dans 16 Go : `gemma4:e4b`, `llama3`, `qwen3-vl:8b`.
- À éviter sur cette carte : `gemma4:26b`/`31b` (17-19 Go → débordent sur le CPU, lent).

Le script impose une **sortie JSON structurée** (champ `format` d'Ollama) : le modèle
ne peut pas dévier du schéma, ce qui élimine la quasi-totalité des erreurs de format.

## Ce que le LLM ne fait PAS (par conception)

Un LLM hallucine les faits précis. Le script les neutralise :

| Donnée | D'où elle vient |
|---|---|
| Coordonnées GPS | **Géocodage Nominatim/OSM**, jamais le modèle |
| Horaires exacts | Laissés génériques → **à confirmer à la main** |
| URL des sources | Marquées `"A VERIFIER"` → **à remplir à la main** |
| Photos | `assets/PLACEHOLDER.jpg` → **fournir une vraie image** `assets/<id>.jpg` |

Le générateur écrit une liste `_review` en fin de JSON **et** l'affiche : ce sont les
points à valider avant publication. Ne jamais publier un brouillon sans cette passe.

> Politesse Nominatim : 1 requête/seconde max, User-Agent renseigné. Pour un gros
> volume, héberger son propre Nominatim ou utiliser un fournisseur dédié.

## Optimiser les images d'un nouveau lot

```bash
python - <<'PY'
from PIL import Image; import os
for f in os.listdir('assets'):
    p='assets/'+f; im=Image.open(p).convert('RGB')
    w,h=im.size; s=min(1, 1400/max(w,h))
    if s<1: im=im.resize((round(w*s),round(h*s)), Image.LANCZOS)
    im.save(p[:-4]+'.jpg','JPEG',quality=82,optimize=True,progressive=True)
PY
```
