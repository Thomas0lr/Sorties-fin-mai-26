// One-shot: derive template.html depuis l'index.html actuel.
// Remplace le bloc de donnees JS et les textes statiques par des placeholders.
// Usage: node tools/_make_template.mjs
import { readFileSync, writeFileSync } from "node:fs";

let html = readFileSync("index.html", "utf8");

function literalSpan(src, startAnchor, openChar) {
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
    else if (c === close) { depth--; if (depth === 0) return [start, j + 1]; }
  }
  throw new Error("literal non ferme: " + startAnchor);
}

// 1) Remplace tout le bloc "const montpellier ... const schedulePlans = {...};"
const dataStart = html.indexOf("    const montpellier =");
const [, schedEnd] = literalSpan(html, "const schedulePlans =", "{");
const blockEnd = html.indexOf(";", schedEnd) + 1;
if (dataStart < 0 || blockEnd <= 0) throw new Error("bloc data introuvable");

const injectedJs =
`    const LOT = /*__LOT_JSON__*/ {};
    const montpellier = LOT.meta.origin;
    const dayStart = LOT.meta.dayStart;
    const dayEnd = LOT.meta.dayEnd;

    const outings = LOT.outings;
    outings.forEach((outing, index) => { outing.rank = index + 1; });

    const schedulePlans = LOT.schedulePlans;`;

html = html.slice(0, dataStart) + injectedJs + html.slice(blockEnd);

// 2) Placeholders pour les textes statiques (remplacement exact, 1 occurrence)
const subs = [
  ["<title>Lot 15 soleil doux - 30 et 31 mai 2026</title>", "<title>__TITLE__</title>"],
  ["<h1>Lot soleil doux 30-31 mai 2026</h1>", "<h1>__HEADING__</h1>"],
  ["<p>Version publiée. Pour 2-3 personnes au départ de Montpellier, avec eau, ombre ou repli intérieur pour profiter du week-end sans subir la chaleur.</p>", "<p>__INTRO__</p>"],
  ['<h2 id="propositions-title">Les 15 sorties à choisir</h2>', '<h2 id="propositions-title">__SECTION_TITLE__</h2>'],
  ["<p>Chaque fiche combine au moins un lieu à visiter et une activité à faire, avec budget par personne, sources, trajet depuis Montpellier et barre horaire standardisée.</p>", "<p>__SECTION_INTRO__</p>"],
  ["<p><strong>Ordre conseillé :</strong> les trois meilleurs choix anti-chaleur passent en tête : Clamouse, Grotte des Demoiselles puis Seaquarium. Ensuite, garder les options eau/ombre selon l'envie : Bouzigues, Valmagne, Frontignan, Aigues-Mortes ou Balaruc.</p>", "<p>__NOTE__</p>"]
];
for (const [from, to] of subs) {
  if (!html.includes(from)) throw new Error("texte introuvable: " + from.slice(0, 40));
  html = html.replace(from, to);
}

writeFileSync("template.html", html, "utf8");
console.log("OK -> template.html (" + html.length + " octets)");
