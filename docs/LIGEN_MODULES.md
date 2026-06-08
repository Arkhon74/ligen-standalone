# Ligen Astralogie — Modules

**Ancienne référence :** AstroFlow Modules  
**Date :** 01.06.2026

---

## Architecture modulaire

### Ligen Core (`ligen/core/`)
Moteur central. Orchestration des calculs, gestion du pipeline strict, routing vers les modules.
- Swiss Ephemeris (pyswisseph)
- Calcul positions planétaires, maisons, aspects
- Validation des entrées (date, heure, lieu)

### Ligen Prompts (`ligen/prompts/`)
Référentiel canonique. **Seule source autorisée pour les appels LLM.**
- Blocs A1→C6 en fichiers `.txt` ou `.md` nommés par ID
- Loader strict avec vérification d'intégrité
- Aucun prompt inline dans le code applicatif

### Ligen Charts (`ligen/charts/`)
Rendu graphique des thèmes et cartes.
- Thème natal (roue)
- Synastrie / composite
- Carte de lignée multi-générations

### Ligen Lineage (`ligen/lineage/`)
**Module différenciateur.** Logique multi-générationnelle.
- Gestion de profils familiaux
- Détection de patterns transmis
- Noeuds / axes de transmission

### Ligen Synastry (`ligen/synastry/`)
Comparaisons relationnelles.
- Synastrie classique (2 personnes)
- Synastrie familiale (N personnes)
- Composite / Davison

### Ligen Reports (`ligen/reports/`)
Génération de rapports texte.
- Injection des blocs B1→B6
- Assemblage par type de rapport
- Paramètres de longueur / profondeur

### Ligen Layout (`ligen/layout/`)
Mise en page et export.
- Blocs C1→C6
- Export PDF
- Templates rapport standard / premium

### Ligen Data (`ligen/data/`)
Stockage local.
- Profils natals (JSON)
- Cache de calculs
- Paramètres utilisateur
- Pas de cloud — standalone uniquement
