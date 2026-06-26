"""
ligen/api/app.py
Ligen Astralogie — Factory Flask + configuration

Usage
-----
    # Développement
    from ligen.api.app import create_app
    app = create_app()
    app.run(debug=True, port=5000)

    # Production (gunicorn)
    gunicorn "ligen.api.app:create_app()" -b 0.0.0.0:5000

Variables d'environnement
-------------------------
    LIGEN_DB_PATH    : chemin SQLite (défaut: ligen.db)
    LIGEN_EPHE_PATH  : dossier éphémérides Swiss Ephemeris
    LIGEN_REPORTS_DIR: dossier de sortie des PDF (défaut: reports/)
    LIGEN_SECRET_KEY : clé secrète Flask (défaut: dev-key)
    FLASK_ENV        : development | production
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

from flask import Flask, jsonify

try:
    from ligen.data.db import Database
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.data.db import Database


# ── Configuration ─────────────────────────────────────────────────────────────

class Config:
    SECRET_KEY    = os.environ.get("LIGEN_SECRET_KEY", "ligen-dev-secret-key")
    DB_PATH       = os.environ.get("LIGEN_DB_PATH",    "ligen.db")
    EPHE_PATH     = os.environ.get("LIGEN_EPHE_PATH",  "/home/user/ephe")
    REPORTS_DIR   = os.environ.get("LIGEN_REPORTS_DIR","reports")
    PROMPTS_DIR   = os.environ.get("LIGEN_PROMPTS_DIR","ligen/prompts/blocks")
    TEMPLATES_DIR = os.environ.get("LIGEN_TEMPLATES_DIR","ligen/reports/templates")
    JSON_SORT_KEYS        = False
    JSON_ENSURE_ASCII     = False
    MAX_CONTENT_LENGTH    = 16 * 1024 * 1024   # 16 MB max upload
    HOUSE_SYSTEM_DEFAULT  = "campanus"


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    DEBUG   = True
    TESTING = True
    DB_PATH = ":memory:"


class ProductionConfig(Config):
    DEBUG   = False
    TESTING = False


_configs = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
}


# ── Factory ───────────────────────────────────────────────────────────────────

def _validate_config(app: Flask) -> None:
    """
    Valide la configuration au démarrage.
    Lève RuntimeError si un paramètre critique est manquant ou invalide.
    """
    import os
    warnings_list = []

    ephe = app.config.get("EPHE_PATH", "")
    if not ephe or not os.path.isdir(ephe):
        warnings_list.append(
            f"LIGEN_EPHE_PATH='{ephe}' inaccessible — "
            "calculs Swiss Ephemeris limités aux éphémérides intégrées"
        )

    prompts = app.config.get("PROMPTS_DIR", "")
    if prompts and not os.path.isdir(prompts):
        warnings_list.append(
            f"LIGEN_PROMPTS_DIR='{prompts}' introuvable — "
            "loader de blocs prompts non fonctionnel"
        )

    templates = app.config.get("TEMPLATES_DIR", "")
    if templates and not os.path.isdir(templates):
        raise RuntimeError(
            f"LIGEN_TEMPLATES_DIR='{templates}' introuvable — "
            "génération de rapports impossible. "
            "Vérifiez le chemin dans .env"
        )

    key = app.config.get("SECRET_KEY", "")
    if key == "ligen-dev-secret-key" and not app.config.get("TESTING"):
        warnings_list.append(
            "LIGEN_SECRET_KEY utilise la valeur par défaut — "
            "définir une clé unique en production"
        )

    for w in warnings_list:
        app.logger.warning("[config] %s", w)


def create_app(config_name: str | None = None) -> Flask:
    """
    Factory Flask.

    Paramètres
    ----------
    config_name : "development" | "testing" | "production" (défaut : FLASK_ENV)

    Retourne
    --------
    Flask app configurée avec blueprints et base de données initialisée.
    """
    env = config_name or os.environ.get("FLASK_ENV", "development")
    cfg = _configs.get(env, DevelopmentConfig)

    app = Flask(__name__)
    app.config.from_object(cfg)

    # ── Logging ───────────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ── Base de données ───────────────────────────────────────────────────────
    db = Database(app.config["DB_PATH"])
    db.initialize()
    app.extensions["db"] = db

    # ── Répertoire rapports ───────────────────────────────────────────────────
    reports_dir = Path(app.config["REPORTS_DIR"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    app.config["REPORTS_DIR"] = str(reports_dir.resolve())

    # ── Validation config au démarrage ───────────────────────────────────────
    _validate_config(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from ligen.api.routes.charts   import charts_bp
    from ligen.api.routes.sessions import sessions_bp
    from ligen.api.routes.reports  import reports_bp

    app.register_blueprint(charts_bp,   url_prefix="/api/charts")
    app.register_blueprint(sessions_bp, url_prefix="/api/sessions")
    app.register_blueprint(reports_bp,  url_prefix="/api/reports")

    # ── Routes utilitaires ────────────────────────────────────────────────────

    @app.get("/")
    def index():
        from ligen.api.app import ok as _ok
        return _ok({
            "app":     "Ligen Astralogie API",
            "version": "1.0.0",
            "status":  "ok",
            "routes": {
                "charts":   "/api/charts",
                "sessions": "/api/sessions",
                "reports":  "/api/reports",
            },
        })

    @app.get("/health")
    def health():
        try:
            db = app.extensions["db"]
            db.row_count("charts")
            return jsonify({"status": "ok", "db": "connected"})
        except Exception as exc:
            return jsonify({"status": "error", "detail": str(exc)}), 503

    # ── Gestionnaires d'erreurs ───────────────────────────────────────────────

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad Request", "detail": str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not Found"}), 404

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"error": "Unprocessable Entity", "detail": str(e)}), 422

    @app.errorhandler(500)
    def internal(e):
        app.logger.exception("Internal error")
        return jsonify({"error": "Internal Server Error"}), 500

    return app


# ── Helpers partagés ──────────────────────────────────────────────────────────

def get_db() -> Database:
    """Retourne la Database depuis les extensions Flask."""
    from flask import current_app
    return current_app.extensions["db"]


def ok(data: dict | list, status: int = 200):
    """Réponse JSON succès standardisée."""
    from flask import jsonify
    return jsonify({"ok": True, "data": data}), status


def err(message: str, status: int = 400, detail: str = ""):
    """Réponse JSON erreur standardisée."""
    from flask import jsonify
    payload = {"ok": False, "error": message}
    if detail:
        payload["detail"] = detail
    return jsonify(payload), status


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app("development")
    app.run(host="0.0.0.0", port=5000, debug=True)
