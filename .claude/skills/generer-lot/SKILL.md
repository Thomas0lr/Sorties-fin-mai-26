---
name: generer-lot
description: >-
  Génère, vérifie et publie un "lot" de sorties pour le site Sorties (pages de
  ~10 idées d'activités autour de Montpellier). Utilise cette compétence dès que
  l'utilisateur veut créer un nouveau lot, composer des sorties, produire une
  nouvelle page de week-end, enrichir la bibliothèque, ou publier un lot.
  Déclenche aussi s'il mentionne compose_lot.py, library.py, library_add.py,
  generate_lot.py, build.py, la bibliothèque privée, un thème de lot
  (anti-chaleur, patrimoine...), Ollama/Gemma pour ce projet, ou les dossiers
  data/ et tools/ de ce dépôt.
---

# Générer un lot de sorties

Priorité : **la bibliothèque privée d'abord** (vrais lieux curés, zéro
hallucination), le web/LLM seulement en complément. Le LLM est **rédacteur**, pas
inventeur de faits. Le HTML final reste un fichier unique (template + données).

```
bibliotheque_sorties.csv  →(filtre)→  candidats réels
        │  (manque ?)  →  recherche WEB  →  library_add.py  →  enrichit la biblio
        ▼
   LLM = rédaction prose (sur faits réels)  →  géocodage  →  lot JSON  →  build.py  →  HTML
```

## Règle d'or : privé / public
La bibliothèque complète (`_bibliotheque_privee/`, ~111 idées) **reste privée et
n'est JAMAIS publiée** (elle est gitignorée). Seul le sous-ensemble public des
champs des 10 sorties retenues part dans le lot. Publication uniquement sur
demande explicite.

## Étapes

1. **Pré-vol.** Ollama (≥ 0.30) répond (`curl -s localhost:11434/api/version`),
   modèle dispo (`ollama list`, défaut `gemma4:12b`). La biblio est à
   `_bibliotheque_privee/bibliotheque_sorties.csv` (racine du dépôt principal).

2. **Composer depuis la bibliothèque** (~1-2 min, prose seulement) :
   ```
   python tools/compose_lot.py --theme "<thème>" --dates "<dates>" \
       --slug <slug> --count 10 --model gemma4:12b
   ```
   - Tester le filtre seul : `python tools/library.py --theme "<thème>" --count 10`.
   - Le mapping thème→tags est dans `library.py` (`THEME_PROFILES`) ; ajouter un
     profil si le thème est nouveau.

3. **Si le `_review` affiche un `GAP`** (la biblio n'a pas assez de candidats) :
   - **Recherche web** de vraies idées nouvelles pour le thème + sources.
   - Vérifier (existence, accès, période), puis **enrichir la bibliothèque** :
     ```
     python tools/library_add.py --nom "..." --zone "..." --nature nature \
         --tags "..." --temps-montpellier "..." --budget-min .. --budget-max .. \
         --duree "..." --effort .. --meteo .. --source "<url>" --id <slug-court>
     ```
   - Relancer `compose_lot.py` : la nouvelle idée est désormais un candidat.

4. **Traiter la liste `A VERIFIER` / `_review`** (le cœur du travail). Pour
   chaque fiche : confirmer horaires (`availability`), remplacer les `sources`
   "A VERIFIER" par les URLs officielles, vérifier les `coords` marquées
   approximatives/introuvables, gérer les réservations signalées, fournir une
   vraie image `assets/<id>.jpg` (mettre à jour `image`, compresser).

5. **Construire** : `python tools/build.py data/lot-<slug>.json index.html`
   (ou un autre nom de sortie pour ne pas écraser le lot publié).

6. **Vérifier le rendu** : `python -m http.server 4185`, contrôler 10 fiches,
   cartes, images, 0 erreur console, mobile.

7. **Publier** (après confirmation explicite) :
   `git add -A && git commit -m "Publish lot <slug>" && git push origin HEAD:main`
   → https://thomas0lr.github.io/Sorties-fin-mai-26/

## Replis
- Thème sans aucune couverture biblio → `generate_lot.py` (pur LLM, invente des
  lieux, à vérifier lourdement). À éviter si la biblio peut fournir.
- Détails, A/B des modèles, dépannage : `tools/README.md`.
