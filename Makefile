# ── Ligen Astralogie — Makefile ────────────────────────────────────────────────
# Usage : make <cible>
# Requiert : Python 3.11, pip, docker (optionnel)

.PHONY: help install install-dev run test test-cov lint fmt check docker-build \
        docker-run docker-stop clean ephe

PYTHON   := python3
PIP      := pip
APP      := ligen.api.app:create_app()
PORT     := 5000
WORKERS  := 2
IMAGE    := ligen-astralogie:latest
DB_PATH  := ligen.db

# ── Aide ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Ligen Astralogie — commandes disponibles"
	@echo "  ─────────────────────────────────────────"
	@echo "  make install      Installer les dépendances production"
	@echo "  make install-dev  Installer les dépendances dev + test"
	@echo "  make run          Démarrer le serveur Flask (dev)"
	@echo "  make run-prod     Démarrer avec Gunicorn (production)"
	@echo "  make test         Lancer la suite de tests"
	@echo "  make test-cov     Tests avec rapport de couverture"
	@echo "  make lint         Analyser le code (ruff)"
	@echo "  make fmt          Formater le code (ruff format)"
	@echo "  make check        lint + tests complets"
	@echo "  make docker-build Construire l'image Docker"
	@echo "  make docker-run   Démarrer le conteneur Docker"
	@echo "  make docker-stop  Arrêter le conteneur Docker"
	@echo "  make ephe         Télécharger les éphémérides Swiss Ephemeris"
	@echo "  make clean        Nettoyer les fichiers temporaires"
	@echo ""

# ── Installation ──────────────────────────────────────────────────────────────
install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

# ── Serveur ───────────────────────────────────────────────────────────────────
run:
	@echo "Démarrage Flask (dev) sur http://localhost:$(PORT)"
	FLASK_ENV=development $(PYTHON) -m flask \
		--app $(APP) \
		run --host=0.0.0.0 --port=$(PORT) --debug

run-prod:
	@echo "Démarrage Gunicorn sur http://0.0.0.0:$(PORT)"
	gunicorn "$(APP)" \
		--bind 0.0.0.0:$(PORT) \
		--workers $(WORKERS) \
		--timeout 120 \
		--access-logfile - \
		--error-logfile -

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	SE_EPHE_PATH=$${LIGEN_EPHE_PATH:-/home/user/ephe} \
	$(PYTHON) -m pytest tests/ -v --tb=short

test-cov:
	SE_EPHE_PATH=$${LIGEN_EPHE_PATH:-/home/user/ephe} \
	$(PYTHON) -m pytest tests/ -v --tb=short \
		--cov=ligen \
		--cov-report=term-missing \
		--cov-report=html:htmlcov

test-api:
	SE_EPHE_PATH=$${LIGEN_EPHE_PATH:-/home/user/ephe} \
	$(PYTHON) -m pytest tests/test_api.py -v --tb=short

test-core:
	SE_EPHE_PATH=$${LIGEN_EPHE_PATH:-/home/user/ephe} \
	$(PYTHON) -m pytest tests/test_core.py tests/test_wheel.py -v --tb=short

# ── Qualité code ──────────────────────────────────────────────────────────────
lint:
	ruff check ligen/ tests/

fmt:
	ruff format ligen/ tests/

check: lint test
	@echo ""
	@echo "✓ Lint OK | Tests OK"

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run -d \
		--name ligen \
		-p $(PORT):5000 \
		-v ligen-data:/data \
		-e LIGEN_SECRET_KEY=$${LIGEN_SECRET_KEY:-change-me} \
		$(IMAGE)
	@echo "Ligen démarré → http://localhost:$(PORT)"

docker-stop:
	docker stop ligen && docker rm ligen

docker-logs:
	docker logs -f ligen

# ── Éphémérides ───────────────────────────────────────────────────────────────
EPHE_DIR := $(or $(LIGEN_EPHE_PATH),/home/user/ephe)

ephe:
	@echo "Téléchargement éphémérides Swiss Ephemeris dans $(EPHE_DIR)"
	@mkdir -p $(EPHE_DIR)
	$(PYTHON) - << 'EOF'
import urllib.request, os
base = "https://www.astro.com/ftp/swisseph/ephe"
ephe_dir = "$(EPHE_DIR)"
files = ["seas_18.se1", "semo_18.se1", "sepl_18.se1"]
for f in files:
    dest = os.path.join(ephe_dir, f)
    if not os.path.exists(dest):
        print(f"Téléchargement {f}...")
        try:
            urllib.request.urlretrieve(f"{base}/{f}", dest)
            print(f"  OK → {dest}")
        except Exception as e:
            print(f"  ERREUR : {e}")
    else:
        print(f"  Déjà présent : {dest}")
EOF

# ── Nettoyage ─────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache dist build
	@echo "Nettoyage terminé"

db-reset:
	@echo "Suppression de $(DB_PATH)..."
	rm -f $(DB_PATH)
	@echo "Base de données réinitialisée (sera recréée au prochain démarrage)"
