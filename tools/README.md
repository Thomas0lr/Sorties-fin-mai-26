# Pipeline de génération des lots (LLM local)

## Source primaire : la bibliothèque privée (recommandé)

Avant de demander quoi que ce soit à un LLM, on pioche dans
`_bibliotheque_privee/bibliotheque_sorties.csv` (~111 lieux réels, tagués). C'est
le remède n°1 à l'hallucination : les lieux sont **vrais**, le LLM ne fait plus
qu'écrire la prose.

| Outil | Rôle |
|---|---|
| `tools/library.py` | Charge/filtre/classe le CSV (profils de thème, distance, budget). Lançable seul pour tester un filtre. |
| `tools/compose_lot.py` | **Compose un lot depuis la biblio** : sélection → rédaction LLM (prose sur faits réels) → géocodage → lot JSON. |
| `tools/library_add.py` | **Boucle de retour** : ajoute une idée nouvelle (trouvée sur le web, vérifiée) au CSV. |

```bash
python tools/compose_lot.py --theme "anti-chaleur" --dates "30-31 mai 2026" \
    --slug soleil --count 10 --model gemma4:12b
# si _review affiche GAP : recherche web -> library_add.py -> recomposer
python tools/build.py data/lot-soleil.json index.html
```

**Privé/public** : `_bibliotheque_privee/` est gitignoré et ne doit JAMAIS être
publié ; seul le sous-ensemble public des champs part dans le lot.

`generate_lot.py` (ci-dessous, pur LLM) reste un repli pour un thème sans
couverture biblio — il invente des lieux, donc vérification lourde.

---

# Générateur pur LLM (repli) — generate_lot.py

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

## Réglages & retour d'expérience (tests réels gemma3:12b)

- **Temps de génération** : ~4-5 min pour 10-12 sorties sur RX 6900 XT (16 Go).
- **Itérer sans repayer le modèle** : le brut est mis en cache dans
  `data/.raw-<slug>.json`. `--from-raw` rejoue géocodage + post-traitement en
  quelques secondes (utile pour ajuster `--max-km`, etc.).
- **Hallucinations de lieux** : un 12B invente des sites obscurs quand `--count`
  est élevé (testé : ~3 lieux inventés sur 12). Ils sont **toujours attrapés**
  par le géocodage + le garde-fou distance et listés en `!! EXISTENCE A VERIFIER`.
  Pour en réduire le nombre : baisser `--count` (8-10), puis compléter à la main.
- **Garde-fou distance** (`--max-km`, défaut 250) : rejette les homonymes
  lointains. Exemple réel rattrapé : « Fontaine Audierne » géocodée en Bretagne,
  « Jardin Smith » à Tahiti.
- **Ne pas forcer la région** dans le géocodage : le modèle propose souvent des
  lieux des départements voisins (Gard, Bouches-du-Rhône) ; `commune + France`
  désambiguïse mieux qu'un hint de région erroné.
- **Choix du modèle (testé en A/B, thème anti-chaleur, count 12)** :

  | | gemma3:12b | gemma4:12b (défaut) |
  |---|---|---|
  | Temps | ~5 min | **~2 min 45** |
  | Effectif livré | 11/12 | **12/12** |
  | Badges/pitchs uniques | 9-10/11 | **12/12** |
  | Lieux hallucinés | 3 | 4 |

  `gemma4:12b` rédige mieux et plus vite mais **hallucine un peu plus de lieux**
  (il a inventé une commune « Saint-Aygut »). **Conclusion : aucun 12B ne se
  suffit à lui-même** — la passe de vérification reste obligatoire. Le défaut est
  `gemma4:12b` (meilleure prose) ; basculer sur `gemma3:12b` si on préfère un peu
  moins d'élagage. Le script est agnostique : changer juste `--model`.
- **Modèles "thinking" (gemma4)** : le script désactive `think` automatiquement
  (via `/api/show`) — sinon le modèle consomme tout son budget en raisonnement et
  renvoie un contenu vide. `gemma4:12b` exige **Ollama ≥ 0.30** (sinon 412 au pull).
- **Troncature JSON** : `num_ctx=16384`, `num_predict=8192`. Si une sortie est
  quand même tronquée (`done_reason=length`), le brut est sauvé en `data/.debug-*`
  et il faut baisser `--count`.

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
