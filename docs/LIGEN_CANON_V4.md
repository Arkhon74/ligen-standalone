# Ligen — Documentation Canonique V4

**Statut :** source unique de vérité  
**Ancienne référence :** AstroFlow Canon V4  
**Date :** 01.06.2026

---

## Règles canoniques

1. Toute modification du canon passe d'abord ici, puis se propage aux sources secondaires.
2. Les blocs A1 → C6 sont la base exclusive pour les prompts de l'application.
3. Les IDs de blocs sont stables et ne doivent jamais être renommés sans mise à jour de toutes les références.
4. Les placeholders `{{...}}` ne doivent jamais être résolus en dur dans le code — ils sont injectés au runtime.

---

## Blocs canoniques

### Groupe A — Synastrie Familiale RPG

| ID    | Nom                         | Statut     |
|-------|-----------------------------|------------|
| A1    | Profil natal individuel     | Stable V1  |
| A2    | Analyse inter-générations   | Stable V1  |
| A3    | Patterns familiaux          | Stable V1  |
| A4    | Carte de lignée             | Stable V1  |
| A5    | Transmission symbolique     | Stable V1  |
| A6    | Noeuds karmiques lignée     | Stable V1  |
| A7    | Cycles collectifs famille   | Stable V1  |
| A8    | Tensions / répétitions      | Stable V1  |
| A9    | Seuils de rupture           | Stable V1  |
| A10   | Ressources héritées         | Stable V1  |
| A11   | Blessures transmises        | Stable V1  |
| A12   | Ancrage & guérison          | Stable V1  |
| A13   | Synthèse lignée complète    | Stable V1  |
| A14   | Rapport final famille       | Stable V1  |

### Groupe B — Astro-Scripteur

| ID    | Nom                         | Statut     |
|-------|-----------------------------|------------|
| B1    | Rédaction profil natal      | Stable V1  |
| B2    | Rédaction transits          | Stable V1  |
| B3    | Rédaction synastrie         | Stable V1  |
| B4    | Rédaction RS                | Stable V1  |
| B5    | Rédaction progressions      | Stable V1  |
| B6    | Rédaction rapport final     | Stable V1  |

### Groupe C — Astro Mise en Page

| ID    | Nom                         | Statut     |
|-------|-----------------------------|------------|
| C1    | Layout rapport standard     | Stable V1  |
| C2    | Layout rapport premium      | Stable V1  |
| C3    | Export PDF                  | Stable V1  |
| C4    | Mise en page lignée         | Stable V1  |
| C5    | Mise en page synastrie      | Stable V1  |
| C6    | Mise en page rapport final  | Stable V1  |

---

## Règle de mise à jour

Toute modification d'un bloc doit :
1. Incrémenter le numéro de version du bloc (`V1 → V2`).
2. Mettre à jour ce fichier.
3. Propager aux références dans `/prompts/`.
4. Invalider les caches de rendu si applicable.
