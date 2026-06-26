# ── Ligen Astralogie — Dockerfile multi-stage ─────────────────────────────────
# Stage 1 : build (éphémérides + dépendances)
# Stage 2 : runtime minimal

# ── STAGE 1 : builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Dépendances système pour WeasyPrint et CairoSVG
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libffi-dev \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir \
 && pip install --no-cache-dir -r requirements.txt

# Télécharger les éphémérides Swiss Ephemeris (fichier principal)
RUN mkdir -p /ephe && \
    python3 -c "\
import urllib.request, os; \
base = 'https://www.astro.com/ftp/swisseph/ephe'; \
files = ['seas_18.se1', 'semo_18.se1', 'sepl_18.se1']; \
[urllib.request.urlretrieve(f'{base}/{f}', f'/ephe/{f}') for f in files]; \
print('Ephemeris OK')" || echo "Warning: ephemeris download failed — using built-in"


# ── STAGE 2 : runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Fred Troussier <troussier.frederic@live.fr>"
LABEL description="Ligen Astralogie — API Flask + Swiss Ephemeris"
LABEL version="1.0.0"

WORKDIR /app

# Dépendances système runtime (sans gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copier les packages Python installés depuis le builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copier les éphémérides
COPY --from=builder /ephe /ephe

# Copier le code applicatif
COPY ligen/          ./ligen/
COPY pyproject.toml  .
COPY README.md       .

# Créer les dossiers de runtime
RUN mkdir -p /data/reports /data/db

# Utilisateur non-root
RUN useradd -r -u 1001 -m ligen && \
    chown -R ligen:ligen /app /data /ephe
USER ligen

# Variables d'environnement par défaut
ENV FLASK_ENV=production \
    LIGEN_DB_PATH=/data/db/ligen.db \
    LIGEN_EPHE_PATH=/ephe \
    SE_EPHE_PATH=/ephe \
    LIGEN_REPORTS_DIR=/data/reports \
    LIGEN_PROMPTS_DIR=/app/ligen/prompts/blocks \
    LIGEN_TEMPLATES_DIR=/app/ligen/reports/templates \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" \
    || exit 1

# Démarrage gunicorn
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "ligen.api.app:create_app()"]
