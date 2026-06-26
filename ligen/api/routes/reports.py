"""
ligen/api/routes/reports.py
Ligen API — Routes /api/reports

POST /api/reports/natal          — Génère un rapport PDF natal
POST /api/reports/lineage        — Génère un rapport PDF de lignée
GET  /api/reports                — Liste des rapports
GET  /api/reports/:id/download   — Télécharger un rapport
DELETE /api/reports/:id          — Supprimer un rapport

Payload POST /api/reports/natal
--------------------------------
{
  "chart_id":     1,
  "session_id":   2,            // optionnel
  "active_blocks": ["A01","A02","A03","A06","A07"],
  "birth_place":  "Sallanches, France",
  "birth_date_fmt": "28/05/1983",
  "birth_time_fmt": "14h40 LT (12h40 UT)",
  "report_title": "Analyse Natale Ligen",
  "include_wheel": true,
  "wheel_size":   640,
  "extra_values": {}
}

Payload POST /api/reports/lineage
----------------------------------
{
  "lineage_id":    1,           // ID groupe existant OU
  "members": [                  // liste inline de chart_id + rôle
    {"chart_id": 1, "role": "self",    "link_to": "Olivia"},
    {"chart_id": 2, "role": "partner", "link_to": "Fred"}
  ],
  "include_wheels": true,
  "wheel_size":     480
}
"""

from __future__ import annotations

import datetime
import json
import os
import warnings
from pathlib import Path

from flask import Blueprint, request, send_file, current_app

try:
    from ligen.api.app import get_db, ok, err
    from ligen.core.engine import (
        NatalChart, PlanetPosition, HouseCusp, AspectResult, compute_natal_chart
    )
    from ligen.data.repository import ChartRepo, ReportRepo, LineageRepo
    from ligen.reports.generator import ReportGenerator, ReportConfig
    from ligen.reports.lineage_report import LineageReportGenerator
    from ligen.lineage.engine import LineageEngine, LineageMember
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from ligen.api.app import get_db, ok, err
    from ligen.core.engine import (
        NatalChart, PlanetPosition, HouseCusp, AspectResult, compute_natal_chart
    )
    from ligen.data.repository import ChartRepo, ReportRepo, LineageRepo
    from ligen.reports.generator import ReportGenerator, ReportConfig
    from ligen.reports.lineage_report import LineageReportGenerator
    from ligen.lineage.engine import LineageEngine, LineageMember

reports_bp = Blueprint("reports", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rebuild_chart(chart_id: int, chart_repo: ChartRepo) -> NatalChart | None:
    """Reconstruit un NatalChart depuis la base (raw_json)."""
    data = chart_repo.restore_natal_chart(chart_id)
    if not data:
        return None
    try:
        planets = [PlanetPosition(**p) for p in data["planets"]]
        houses  = [HouseCusp(**h)      for h in data["houses"]]
        aspects = [AspectResult(**a)   for a in data["aspects"]]
        return NatalChart(
            name=data["name"],
            birth_dt_ut=data["birth_dt_ut"],
            latitude=data["latitude"],
            longitude_geo=data["longitude_geo"],
            altitude=data["altitude"],
            house_system=data["house_system"],
            asc=data["asc"], mc=data["mc"],
            planets=planets, houses=houses, aspects=aspects,
        )
    except Exception:
        return None


def _pdf_path(name: str, report_type: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c for c in name if c.isalnum() or c in "_-")[:20]
    reports_dir = current_app.config["REPORTS_DIR"]
    return os.path.join(reports_dir, f"{report_type}_{safe}_{ts}.pdf")


# ── POST /api/reports/natal ───────────────────────────────────────────────────

@reports_bp.post("/natal")
def generate_natal():
    """Génère un rapport PDF natal depuis un chart_id."""
    body = request.get_json(silent=True)
    if not body:
        return err("Corps JSON requis", 400)
    if "chart_id" not in body:
        return err("chart_id requis", 400)

    db         = get_db()
    chart_repo = ChartRepo(db)
    report_repo = ReportRepo(db)

    chart_id = int(body["chart_id"])
    chart_rec = chart_repo.get_by_id(chart_id)
    if not chart_rec:
        return err("Chart introuvable", 404)

    chart = _rebuild_chart(chart_id, chart_repo)
    if not chart:
        return err("Impossible de reconstruire le chart depuis raw_json", 500)

    config = ReportConfig(
        subject_name=chart_rec.name,
        birth_date=body.get("birth_date_fmt", chart_rec.birth_date),
        birth_time=body.get("birth_time_fmt", chart_rec.birth_time_ut[:5] + " UT"),
        birth_place=body.get("birth_place", chart_rec.birth_place),
        active_blocks=body.get("active_blocks", ["A01", "A02", "A03"]),
        include_wheel=bool(body.get("include_wheel", True)),
        wheel_size=int(body.get("wheel_size", 640)),
        report_title=body.get("report_title", "Analyse Natale Ligen"),
        extra_values=body.get("extra_values", {}),
    )

    pdf_path = _pdf_path(chart_rec.name, "natal")

    try:
        gen = ReportGenerator(
            chart=chart,
            config=config,
            prompts_dir=current_app.config["PROMPTS_DIR"],
            templates_dir=current_app.config["TEMPLATES_DIR"],
            ephe_path=current_app.config["EPHE_PATH"],
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gen.render_pdf(pdf_path)
    except Exception as exc:
        return err("Erreur génération PDF", 500, detail=str(exc))

    report_id = report_repo.save(
        title=f"{config.report_title} — {chart_rec.name}",
        file_path=pdf_path,
        report_type="natal",
        format="pdf",
        session_id=body.get("session_id"),
        chart_id=chart_id,
    )

    size = os.path.getsize(pdf_path)
    return ok({
        "report_id":   report_id,
        "chart_id":    chart_id,
        "file_path":   pdf_path,
        "file_size":   size,
        "title":       f"{config.report_title} — {chart_rec.name}",
        "download_url": f"/api/reports/{report_id}/download",
    }, 201)


# ── POST /api/reports/lineage ─────────────────────────────────────────────────

@reports_bp.post("/lineage")
def generate_lineage():
    """Génère un rapport PDF de lignée multi-membres."""
    body = request.get_json(silent=True)
    if not body:
        return err("Corps JSON requis", 400)

    db          = get_db()
    chart_repo  = ChartRepo(db)
    report_repo = ReportRepo(db)
    lineage_repo = LineageRepo(db)

    # Résoudre les membres
    raw_members = body.get("members", [])
    if not raw_members and "lineage_id" in body:
        lid = int(body["lineage_id"])
        lmembers = lineage_repo.get_members(lid)
        raw_members = [
            {"chart_id": m.chart_id, "role": m.role, "link_to": m.link_to}
            for m in lmembers
        ]

    if len(raw_members) < 2:
        return err("Au minimum 2 membres requis", 400)

    members: list[LineageMember] = []
    for m in raw_members:
        cid   = int(m.get("chart_id", 0))
        chart = _rebuild_chart(cid, chart_repo)
        if not chart:
            return err(f"Chart {cid} introuvable", 404)
        members.append(LineageMember(
            chart=chart,
            role=m.get("role", ""),
            link_to=m.get("link_to", ""),
        ))

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            engine = LineageEngine(members)
            lineage_report = engine.analyze()
    except Exception as exc:
        return err("Erreur analyse lignée", 500, detail=str(exc))

    names = "_".join(m.chart.name[:8] for m in members)
    pdf_path = _pdf_path(names, "lineage")

    try:
        gen = LineageReportGenerator(
            lineage_report=lineage_report,
            members=members,
            templates_dir=current_app.config["TEMPLATES_DIR"],
            ephe_path=current_app.config["EPHE_PATH"],
            include_wheels=bool(body.get("include_wheels", True)),
            wheel_size=int(body.get("wheel_size", 480)),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gen.render_pdf(pdf_path)
    except Exception as exc:
        return err("Erreur génération PDF lignée", 500, detail=str(exc))

    title = f"Analyse de Lignée — {' · '.join(m.chart.name for m in members)}"
    report_id = report_repo.save(
        title=title,
        file_path=pdf_path,
        report_type="lineage",
        format="pdf",
    )

    size = os.path.getsize(pdf_path)
    return ok({
        "report_id":    report_id,
        "members":      [m.chart.name for m in members],
        "file_path":    pdf_path,
        "file_size":    size,
        "title":        title,
        "lineage_theme": lineage_report.lineage_theme,
        "download_url": f"/api/reports/{report_id}/download",
    }, 201)


# ── GET /api/reports ─────────────────────────────────────────────────────────

@reports_bp.get("/")
def list_reports():
    db   = get_db()
    repo = ReportRepo(db)
    limit = min(int(request.args.get("limit", 50)), 200)
    records = repo.list_all(limit)
    return ok([{
        "id":          r.id,
        "title":       r.title,
        "report_type": r.report_type,
        "format":      r.format,
        "file_size":   r.file_size,
        "chart_id":    r.chart_id,
        "session_id":  r.session_id,
        "created_at":  r.created_at,
        "download_url": f"/api/reports/{r.id}/download",
    } for r in records])


# ── GET /api/reports/:id/download ────────────────────────────────────────────

@reports_bp.get("/<int:report_id>/download")
def download_report(report_id: int):
    """Télécharge le fichier PDF d'un rapport."""
    db   = get_db()
    repo = ReportRepo(db)
    rec  = repo.get_by_id(report_id)
    if not rec:
        return err("Rapport introuvable", 404)
    if not rec.file_path or not os.path.exists(rec.file_path):
        return err("Fichier PDF non disponible sur disque", 404)

    filename = Path(rec.file_path).name
    return send_file(
        rec.file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# ── DELETE /api/reports/:id ───────────────────────────────────────────────────

@reports_bp.delete("/<int:report_id>")
def delete_report(report_id: int):
    delete_file = request.args.get("delete_file", "false").lower() == "true"
    db   = get_db()
    repo = ReportRepo(db)
    if not repo.get_by_id(report_id):
        return err("Rapport introuvable", 404)
    repo.delete(report_id, delete_file=delete_file)
    return ok({"deleted": report_id})
