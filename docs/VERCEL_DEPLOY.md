# Déploiement Vercel — Ligen Astralogie UI

## URL de production

- **Vercel** : https://ligen-astralogie.vercel.app
- **pplx.app** : https://ligen-astralogie.pplx.app

## Architecture de déploiement

```
Frontend (React/Vite)     → Vercel (statique)
Backend (Flask/Python)    → À déployer (Railway / Render / VPS)
CLI (Click)               → Local / Docker
```

## Variables d'environnement Vercel

| Variable | Valeur | Description |
|----------|--------|-------------|
| `VITE_API_URL` | `https://api.ligen.app` | URL du backend Flask (à configurer) |

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

Déployer le backend Flask (`ligen/api/`) sur Railway ou Render,
puis configurer `VITE_API_URL` dans les variables Vercel.
