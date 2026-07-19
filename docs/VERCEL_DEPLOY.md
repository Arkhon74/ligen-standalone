# Déploiement Vercel — Ligen Astralogie UI

## URL de production

- **Vercel** : https://ligen-astralogie.vercel.app
- **pplx.app** : https://ligen-astralogie.pplx.app

## Architecture de déploiement

```
Frontend (React/Vite)     → Vercel (statique)
Backend (Flask/Python)    → Render (Docker, render.yaml)
CLI (Click)               → Local / Docker
```

## URLs de production

| Couche | URL |
|--------|-----|
| Frontend Vercel | https://ligen-astralogie.vercel.app |
| Frontend pplx.app | https://ligen-astralogie.pplx.app |
| Backend Render (cible) | https://ligen-astralogie-api.onrender.com |
| Backend healthcheck | https://ligen-astralogie-api.onrender.com/health |

## Variables d'environnement Vercel

| Variable | Valeur | Description |
|----------|--------|-------------|
| `VITE_API_URL` | `https://ligen-astralogie-api.onrender.com` | URL du backend Flask Render (configuré sur Vercel le 19 juil. 2026) |

## Déploiement

```bash
cd ligen-ui
npx vercel deploy --prod --yes --token $VERCEL_TOKEN
```

## Configuration vercel.json (frontend)

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist/public",
  "installCommand": "npm ci",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

## Prochaine étape

Backend Flask prêt pour Render (commit `48d50fe`) :
- `render.yaml` à la racine du dépôt (Docker + disque persistant `/data`)
- CORS configuré pour le frontend Vercel/pplx.app
- `VITE_API_URL` ajouté sur Vercel production

Action restante côté dashboard Render :
1. New → Blueprint → connecter `Arkhon74/ligen-standalone`
2. Render détecte `render.yaml` et crée `ligen-astralogie-api`
3. Plan Starter (7$/mois) requis pour le disque persistant SQLite ; Free = DB éphémère
4. Une fois déployé, vérifier `GET /health` puis redéployer le frontend Vercel pour propager `VITE_API_URL`
