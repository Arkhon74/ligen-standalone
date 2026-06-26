"""
ligen/api/routes/sessions.py
Ligen API — Routes /api/sessions

POST /api/sessions              — Créer une session
GET  /api/sessions              — Lister les sessions
GET  /api/sessions/:id          — Session détaillée + blocs
POST /api/sessions/:id/blocks   — Ajouter/mettre à jour un bloc
POST /api/sessions/:id/close    — Fermer la session
PATCH /api/sessions/:id         — Modifier notes / blocs
DELETE /api/sessions/:id        — Supprimer

Payload POST /api/sessions
--------------------------
{
  "title":        "Analyse Fred — Juin 2026",
  "subject_name": "Fred",
  "chart_id":     1,            // optionnel
  "active_blocks": ["A01","A02"],
  "birth_place":  "Sallanches",
  "birth_date_fmt": "28/05/1983",
  "birth_time_fmt": "14h40 LT",
  "notes":        ""
}

Payload POST /api/sessions/:id/blocks
--------------------------------------
{
  "block_id": "A03",
  "rendered": "Contenu rendu du bloc"  // optionnel
}
"""

from __future__ import annotations

from pathlib import Path
from flask import Blueprint, request

try:
    from ligen.api.app import get_db, ok, err
    from ligen.data.repository import SessionRepo
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from ligen.api.app import get_db, ok, err
    from ligen.data.repository import SessionRepo

sessions_bp = Blueprint("sessions", __name__)


# ── POST /api/sessions ────────────────────────────────────────────────────────

@sessions_bp.post("/")
def create_session():
    body = request.get_json(silent=True)
    if not body:
        return err("Corps JSON requis", 400)

    required = ["title", "subject_name"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return err("Champs manquants", 400, detail=str(missing))

    db   = get_db()
    repo = SessionRepo(db)

    try:
        sid = repo.create(
            title=body["title"],
            subject_name=body["subject_name"],
            chart_id=body.get("chart_id"),
            active_blocks=body.get("active_blocks", []),
            birth_place=body.get("birth_place", ""),
            birth_date_fmt=body.get("birth_date_fmt", ""),
            birth_time_fmt=body.get("birth_time_fmt", ""),
            notes=body.get("notes", ""),
        )
    except Exception as exc:
        return err("Erreur création session", 500, detail=str(exc))

    rec = repo.get_by_id(sid)
    return ok({
        "id":           rec.id,
        "title":        rec.title,
        "subject_name": rec.subject_name,
        "chart_id":     rec.chart_id,
        "session_date": rec.session_date,
        "active_blocks": rec.active_blocks,
        "is_open":      rec.is_open,
        "created_at":   rec.created_at,
    }, 201)


# ── GET /api/sessions ─────────────────────────────────────────────────────────

@sessions_bp.get("/")
def list_sessions():
    open_only = request.args.get("open", "false").lower() == "true"
    limit     = min(int(request.args.get("limit", 50)), 200)
    db   = get_db()
    repo = SessionRepo(db)

    records = repo.list_open() if open_only else repo.list_all(limit)
    return ok([{
        "id":           r.id,
        "title":        r.title,
        "subject_name": r.subject_name,
        "chart_id":     r.chart_id,
        "session_date": r.session_date,
        "active_blocks": r.active_blocks,
        "is_open":      r.is_open,
        "created_at":   r.created_at,
        "closed_at":    r.closed_at,
    } for r in records])


# ── GET /api/sessions/:id ─────────────────────────────────────────────────────

@sessions_bp.get("/<int:session_id>")
def get_session(session_id: int):
    db   = get_db()
    repo = SessionRepo(db)
    rec  = repo.get_by_id(session_id)
    if not rec:
        return err("Session introuvable", 404)

    blocks = repo.get_blocks(session_id)
    return ok({
        "id":            rec.id,
        "title":         rec.title,
        "subject_name":  rec.subject_name,
        "chart_id":      rec.chart_id,
        "session_date":  rec.session_date,
        "active_blocks": rec.active_blocks,
        "birth_place":   rec.birth_place,
        "birth_date_fmt": rec.birth_date_fmt,
        "birth_time_fmt": rec.birth_time_fmt,
        "notes":         rec.notes,
        "is_open":       rec.is_open,
        "created_at":    rec.created_at,
        "closed_at":     rec.closed_at,
        "blocks": [{
            "block_id":     b.block_id,
            "rendered":     b.rendered,
            "activated_at": b.activated_at,
        } for b in blocks],
    })


# ── POST /api/sessions/:id/blocks ─────────────────────────────────────────────

@sessions_bp.post("/<int:session_id>/blocks")
def add_block(session_id: int):
    db   = get_db()
    repo = SessionRepo(db)
    if not repo.get_by_id(session_id):
        return err("Session introuvable", 404)

    body = request.get_json(silent=True)
    if not body or not body.get("block_id"):
        return err("block_id requis", 400)

    block_id = body["block_id"].upper().strip()
    rendered = body.get("rendered", "")

    try:
        repo.add_block(session_id, block_id, rendered)
    except Exception as exc:
        return err("Erreur ajout bloc", 500, detail=str(exc))

    rec = repo.get_by_id(session_id)
    return ok({
        "session_id":    session_id,
        "block_id":      block_id,
        "active_blocks": rec.active_blocks,
    }, 201)


# ── POST /api/sessions/:id/close ──────────────────────────────────────────────

@sessions_bp.post("/<int:session_id>/close")
def close_session(session_id: int):
    db   = get_db()
    repo = SessionRepo(db)
    rec  = repo.get_by_id(session_id)
    if not rec:
        return err("Session introuvable", 404)
    if not rec.is_open:
        return err("Session déjà fermée", 409)

    repo.close(session_id)
    rec = repo.get_by_id(session_id)
    return ok({
        "id":        rec.id,
        "is_open":   rec.is_open,
        "closed_at": rec.closed_at,
    })


# ── PATCH /api/sessions/:id ───────────────────────────────────────────────────

@sessions_bp.patch("/<int:session_id>")
def update_session(session_id: int):
    db   = get_db()
    repo = SessionRepo(db)
    if not repo.get_by_id(session_id):
        return err("Session introuvable", 404)

    body = request.get_json(silent=True) or {}
    if "notes" in body:
        repo.update_notes(session_id, body["notes"])

    rec = repo.get_by_id(session_id)
    return ok({"id": rec.id, "notes": rec.notes})


# ── DELETE /api/sessions/:id ──────────────────────────────────────────────────

@sessions_bp.delete("/<int:session_id>")
def delete_session(session_id: int):
    db   = get_db()
    repo = SessionRepo(db)
    if not repo.get_by_id(session_id):
        return err("Session introuvable", 404)
    repo.delete(session_id)
    return ok({"deleted": session_id})
