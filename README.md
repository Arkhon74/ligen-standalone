# Ligen Astralogie

Moteur de calcul astrologique professionnel — Swiss Ephemeris · Campanus · PDF · API REST.

**Stack** : Python 3.11 · Flask 3.1 · pyswisseph · WeasyPrint · SQLite · Docker

---

## Architecture

```
ligen/
├── core/           Calcul Swiss Ephemeris (positions, maisons, aspects)
├── charts/         Rendu SVG/PNG roue natale
├── prompts/        Loader strict MODE STRICT — blocs A01–A14, B01–B06, C01–C06
├── reports/        Générateur PDF (natal + lignée) — WeasyPrint + Jinja2
├── lineage/        Moteur transgénérationnel multi-membres
├── data/           Persistance SQLite (Database, Models, Repositories)
└── api/            API Flask REST

tests/              262 tests pytest (0 échec)
docs/               Documentation canonique
```

---

## Démarrage rapide

### Prérequis

- Python 3.11+
- Éphémérides Swiss Ephemeris (voir ci-dessous)
- Dépendances système WeasyPrint : `libpango`, `libcairo2`, `libgdk-pixbuf2.0`

### Installation

```bash
git clone https://github.com/Arkhon74/ligen-standalone.git
cd ligen-standalone

# Dépendances
pip install -r requirements.txt          # production
pip install -r requirements-dev.txt      # + tests/lint

# Configuration
cp .env.example .env
# Éditer .env : LIGEN_EPHE_PATH, LIGEN_SECRET_KEY

# Éphémérides
make ephe
```

### Démarrage

```bash
make run          # Flask dev  → http://localhost:5000
make run-prod     # Gunicorn   → http://0.0.0.0:5000
```

### Tests

```bash
make test         # suite complète (262 tests)
make test-cov     # + rapport de couverture HTML
make check        # lint + tests
```

---

## API REST — Référence rapide

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET`  | `/health` | État du service |
| `POST` | `/api/charts/` | Calculer + persister un thème natal |
| `GET`  | `/api/charts/` | Lister tous les thèmes |
| `GET`  | `/api/charts/:id` | Thème complet (positions + aspects) |
| `GET`  | `/api/charts/:id/wheel` | Roue natale SVG/PNG (`?format=svg&size=900`) |
| `DELETE` | `/api/charts/:id` | Supprimer un thème |
| `POST` | `/api/sessions/` | Créer une session |
| `POST` | `/api/sessions/:id/blocks` | Activer un bloc (A01–C06) |
| `POST` | `/api/sessions/:id/close` | Fermer la session |
| `POST` | `/api/reports/natal` | Générer PDF natal |
| `POST` | `/api/reports/lineage` | Générer PDF lignée multi-membres |
| `GET`  | `/api/reports/:id/download` | Télécharger un rapport PDF |

### Exemple — Calcul thème natal

```bash
curl -X POST http://localhost:5000/api/charts/ \
  -H "Content-Type: application/json" \
  -d '{
    "name":        "Fred",
    "birth_date":  "1983-05-28",
    "birth_time":  "12:40",
    "birth_place": "Sallanches, France",
    "latitude":    45.9376,
    "longitude":   6.6289,
    "altitude":    550,
    "house_system": "campanus"
  }'
```

### Exemple — Rapport PDF natal

```bash
curl -X POST http://localhost:5000/api/reports/natal \
  -H "Content-Type: application/json" \
  -d '{
    "chart_id":      1,
    "active_blocks": ["A01","A02","A03","A06","A07"],
    "birth_date_fmt": "28/05/1983",
    "birth_time_fmt": "14h40 LT",
    "birth_place":   "Sallanches, France",
    "include_wheel": true
  }'
```

---

## Paramètres astrologique par défaut

| Paramètre | Valeur |
|-----------|--------|
| Zodiaque | Tropical |
| Domification | Campanus |
| Nœuds | Vrais |
| Heures | UT (Universal Time) |
| Éphémérides | Swiss Ephemeris (pyswisseph) |

---

## Éphémérides Swiss Ephemeris

Les fichiers `.se1` doivent être présents dans `LIGEN_EPHE_PATH` :

| Fichier | Contenu |
|---------|---------|
| `seas_18.se1` | Astéroïdes principaux (Chiron, Cérès, Pallas, Junon, Vesta, Pholus) |
| `semo_18.se1` | Lune haute précision |
| `sepl_18.se1` | Planètes principales |

Téléchargement : `make ephe` ou depuis [astro.com/ftp/swisseph/ephe](https://www.astro.com/ftp/swisseph/ephe).

Pour les astéroïdes numérotés (Éros 433, Psyché 16...) : fichiers `se00NNNs.se1` dans le sous-dossier `asteroid/`.

---

## Docker

```bash
make docker-build              # Construire l'image
make docker-run                # Démarrer le conteneur
make docker-stop               # Arrêter
make docker-logs               # Suivre les logs
```

L'image utilise un build multi-stage — téléchargement automatique des éphémérides à la construction.

Données persistantes montées sur le volume `ligen-data` (`/data/db/` et `/data/reports/`).

---

## Structure des blocs prompts

Mode strict — 26 blocs canoniques. Aucun prompt inline dans le code.

| Série | Blocs | Domaine |
|-------|-------|---------|
| A | A01–A14 | Session astrologique complète |
| B | B01–B06 | Synastrie familiale |
| C | C01–C06 | Mise en page et exports |

Fichiers dans `ligen/prompts/blocks/`. Loader : `ligen/prompts/loader.py`.

---

## Charte qualité

- **Zéro pseudo-code** — tout code est directement exécutable
- **Zéro hallucination** — aucune fonction pyswisseph inexistante
- **Tests systématiques** — chaque module a son fichier `tests/test_*.py`
- **Erreurs typées** — `ValueError`, `RuntimeError`, codes HTTP explicites
- **Domification Campanus** par défaut — validé sur thème de référence (Fred 28/05/1983)
- **Sorties JSON sérialisables** — toutes les dataclasses exposent `.to_dict()`

---

## Roadmap modules

| Module | Statut |
|--------|--------|
| M1 core engine + prompts | ✅ 63 tests |
| M2 roue natale SVG | ✅ 27 tests |
| M3 rapport PDF natal | ✅ 37 tests |
| M4 moteur transgénérationnel | ✅ 47 tests |
| M5 persistance SQLite | ✅ 50 tests |
| M6 API Flask REST | ✅ 38 tests |
| M7 packaging production | ✅ ce fichier |
| M8 CLI (`ligen chart`, `ligen report`) | 🔲 à venir |
| M9 interface web React/Capacitor | 🔲 à venir |

---

*Ligen Astralogie · Python 3.11 · Swiss Ephemeris · Campanus · Protocole ASTRO-SCRIPTEUR v3.0*
