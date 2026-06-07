---
name: generer-lot
description: >-
  Génère, vérifie et publie un "lot" de sorties pour le site Sorties (pages de
  ~10-15 idées d'activités autour de Montpellier). Utilise cette compétence dès
  que l'utilisateur veut créer un nouveau lot, générer des sorties, produire une
  nouvelle page de week-end, lancer le générateur LLM local, ou publier un lot.
  Déclenche aussi s'il mentionne generate_lot.py, build.py, un thème de lot
  (anti-chaleur, patrimoine...), Ollama/Gemma pour ce projet, ou les dossiers
  data/ et tools/ de ce dépôt.
---

# Générer un lot de sorties

Pipeline **données / présentation séparées** : un lot = un JSON ; le HTML est
construit à partir d'un template. Un LLM local (Ollama) **rédige**, mais ne
fournit jamais les faits vérifiables (coordonnées → géocodage OSM ; horaires /
sources / images → vérification humaine).

## Étapes

1. **Pré-vol.** Vérifier qu'Ollama (≥ 0.30) répond
   (`curl -s http://localhost:11434/api/version`) et qu'un modèle ≤ ~13 Go est
   disponible (`ollama list`). Défaut : `gemma4:12b` (meilleure prose ; `gemma3:12b`
   en alternative). Le GPU (RX 6900 XT, 16 Go) ne tient pas les modèles > ~14 Go.

2. **Générer le brouillon** (~3 min avec gemma4, ~5 min avec gemma3) :
   ```
   python tools/generate_lot.py --theme "<thème>" --dates "<dates>" \
       --slug <slug> --count 10 --model gemma4:12b
   ```
   - `--count 10` plutôt que 15 : un 12B invente des lieux obscurs quand on lui
     en demande trop. Mieux vaut 10 fiables + en ajouter à la main.
   - Le brut du modèle est mis en cache dans `data/.raw-<slug>.json`. Pour
     re-jouer le post-traitement (géocodage, slugs) sans relancer le modèle :
     `python tools/generate_lot.py --slug <slug> --from-raw` (quelques secondes).

3. **Lire la liste `A VERIFIER` affichée + la clé `_review` du JSON.** C'est le
   cœur du travail. Pour chaque fiche :
   - `!! EXISTENCE A VERIFIER` → le géocodage a échoué : **le lieu est peut-être
     inventé**. Vérifier qu'il existe ; sinon supprimer la fiche.
   - `! coords approximatives` → coordonnées au niveau commune seulement ; ouvrir
     une carte et préciser `coords` si besoin.
   - Remplacer les `sources` "A VERIFIER" par les URLs officielles réelles.
   - Confirmer/affiner `availability` (horaires) et `budget`.
   - Fournir une vraie image `assets/<id>.jpg` et mettre à jour `image`
     (le générateur met `assets/PLACEHOLDER.jpg`). Compresser (cf. tools/README.md).

4. **Construire la page :**
   ```
   python tools/build.py data/lot-<slug>.json index.html
   ```
   (ou un autre nom de sortie pour ne pas écraser le lot publié).

5. **Vérifier le rendu** avant publication : servir le dossier
   (`python -m http.server 4185`) et contrôler que les fiches, cartes et images
   s'affichent, 0 erreur console.

6. **Publier** (demander confirmation à l'utilisateur avant le push) :
   ```
   git add -A && git commit -m "Publish lot <slug>" && git push origin HEAD:main
   ```
   Le site se reconstruit via GitHub Pages :
   https://thomas0lr.github.io/Sorties-fin-mai-26/

## Règles

- **Ne jamais publier un brouillon sans la passe de vérification** (étape 3) :
  les faits viennent du LLM et peuvent être faux.
- Le garde-fou `--max-km` (défaut 250) rejette les géocodages aberrants
  (homonymes lointains). Élargir seulement si l'origine n'est pas Montpellier.
- Détails et dépannage : `tools/README.md`.
