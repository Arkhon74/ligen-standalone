# Ligen

> Astrologie de la lignée — application standalone

**Ancien nom :** AstroFlow Pro (historique uniquement)  
**Date de renommage :** 01.06.2026  
**Statut :** développement actif

---

## Positionnement

Ligen est une application astrologique standalone orientée **lecture multi-générationnelle et cartographie de la lignée familiale**. Elle n'est pas une app de thème natal générique. Son différenciateur central est l'analyse systémique des patterns transmis de génération en génération.

---

## Architecture

```
ligen/
├── core/           # Ligen Core — moteur calcul / orchestration
├── prompts/        # Ligen Prompts — référentiel canonique A1→C6 (MODE STRICT)
├── charts/         # Ligen Charts — thèmes / cartes / roues
├── lineage/        # Ligen Lineage — logique lignée / multi-générationnel
├── synastry/       # Ligen Synastry — comparaisons / relations / synastries
├── reports/        # Ligen Reports — génération de rapports
├── layout/         # Ligen Layout — mise en page / export PDF
└── data/           # Ligen Data — stockage local / profils / paramètres
```

---

## Mode Strict Prompts

Ligen tourne exclusivement en **MODE STRICT PROMPTS**.

Sources autorisées :
- Blocs canoniques **A1 → C6** issus des Spaces Synastrie Familiale RPG, Astro-Scripteur / Astro RPG et Astro Mise en Page
- Aucun prompt maison dans le code
- Aucune improvisation côté app

Toute exécution d'un bloc non présent dans `/prompts/` doit lever une erreur dure.

---

## Docs

- [Documentation canonique](docs/LIGEN_CANON_V4.md)
- [Roadmap](docs/LIGEN_ROADMAP.md)
- [Modules](docs/LIGEN_MODULES.md)
- [Branding & UI](docs/LIGEN_BRANDING.md)
- [Historique AstroFlow](docs/LEGACY_ASTROFLOW.md)

---

## Stack

- Python 3.11+
- Swiss Ephemeris (pyswisseph)
- Mode standalone (pas de dépendance cloud)

---

*ex-AstroFlow Pro — renommé Ligen le 01.06.2026*
