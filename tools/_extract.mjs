// One-shot: extrait les donnees JS de l'index.html actuel vers data/lot-soleil-doux.json
// Usage: node tools/_extract.mjs
import { readFileSync, writeFileSync } from "node:fs";

const html = readFileSync("index.html", "utf8");

function sliceLiteral(src, startAnchor, openChar) {
  const i = src.indexOf(startAnchor);
  if (i < 0) throw new Error("anchor introuvable: " + startAnchor);
  const start = src.indexOf(openChar, i);
  const close = openChar === "[" ? "]" : "}";
  let depth = 0, inStr = false, q = "";
  for (let j = start; j < src.length; j++) {
    const c = src[j];
    if (inStr) { if (c === q && src[j - 1] !== "\\") inStr = false; continue; }
    if (c === '"' || c === "'" || c === "`") { inStr = true; q = c; continue; }
    if (c === openChar) depth++;
    else if (c === close) { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error("literal non ferme: " + startAnchor);
}

const outings = eval("(" + sliceLiteral(html, "const outings =", "[") + ")");
const order = eval("(" + sliceLiteral(html, "const preferredOrder =", "[") + ")");
const schedulePlans = eval("(" + sliceLiteral(html, "const schedulePlans =", "{") + ")");

// Reordonne selon preferredOrder puis supprime le champ rank (recalcule au rendu)
outings.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
outings.forEach((o) => delete o.rank);

const lot = {
  meta: {
    slug: "soleil-doux",
    title: "Lot 15 soleil doux - 30 et 31 mai 2026",
    heading: "Lot soleil doux 30-31 mai 2026",
    intro: "Version publiée. Pour 2-3 personnes au départ de Montpellier, avec eau, ombre ou repli intérieur pour profiter du week-end sans subir la chaleur.",
    sectionTitle: "Les 15 sorties à choisir",
    sectionIntro: "Chaque fiche combine au moins un lieu à visiter et une activité à faire, avec budget par personne, sources, trajet depuis Montpellier et barre horaire standardisée.",
    note: "<strong>Ordre conseillé :</strong> les trois meilleurs choix anti-chaleur passent en tête : Clamouse, Grotte des Demoiselles puis Seaquarium. Ensuite, garder les options eau/ombre selon l'envie : Bouzigues, Valmagne, Frontignan, Aigues-Mortes ou Balaruc.",
    origin: [43.6108, 3.8767],
    originLabel: "Montpellier",
    dayStart: 8,
    dayEnd: 20
  },
  outings,
  schedulePlans
};

writeFileSync("data/lot-soleil-doux.json", JSON.stringify(lot, null, 2) + "\n", "utf8");
console.log(`OK: ${outings.length} sorties, ${Object.keys(schedulePlans).length} plannings -> data/lot-soleil-doux.json`);
