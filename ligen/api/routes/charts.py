"""
ligen/api/routes/charts.py
Ligen API — Routes /api/charts

POST /api/charts          — Calcule et persiste un thème natal
GET  /api/charts          — Liste tous les thèmes
GET  /api/charts/:id      — Thème complet (positions + aspects)
GET  /api/charts/:id/wheel — SVG de la roue natale
DELETE /api/charts/:id    — Supprime un thème

Payload POST /api/charts
------------------------
{
  "name":        "Fred",
  "birth_date":  "1983-05-28",     // ISO 8601
  "birth_time":  "12:40",          // UT
  "birth_place": "Sallanches, France",
  "latitude":    45.9376,
  "longitude":   6.6289,
  "altitude":    550,              // optionnel, défaut 0
  "house_system": "campanus"       // optionnel, défaut config
}
"""

from __future__ import annotations

import datetime
import warnings
from pathlib import Path

from flask import Blueprint, request, current_app, send_file
import tempfile, os

try:
    from ligen.api.app import get_db, ok, err
    from ligen.core.engine import compute_natal_chart
    from ligen.data.repository import ChartRepo
    from ligen.charts.wheel import NatalWheel
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from ligen.api.app import get_db, ok, err
    from ligen.core.engine import compute_natal_chart
    from ligen.data.repository import ChartRepo
    from ligen.charts.wheel import NatalWheel

charts_bp = Blueprint("charts", __name__)


def _parse_birth_datetime(date_str: str, time_str: str) -> datetime.datetime:
    """
    Convertit 'YYYY-MM-DD' + 'HH:MM' ou 'HH:MM:SS' en datetime UT.
    Lève ValueError si le format est invalide.
    """
    try:
        date = datetime.date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"birth_date invalide : '{date_str}' (format attendu : YYYY-MM-DD)")

    time_str = time_str.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.time.fromisoformat(time_str)
            return datetime.datetime.combine(date, t)
        except ValueError:
            continue
    raise ValueError(f"birth_time invalide : '{time_str}' (format attendu : HH:MM ou HH:MM:SS)")


def _validate_coords(lat: float, lon: float) -> None:
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude invalide : {lat}")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitude invalide : {lon}")


# ── POST /api/charts ──────────────────────────────────────────────────────────

@charts_bp.post("/")
def create_chart():
    """Calcule un thème natal et le persiste en base."""
    body = request.get_json(silent=True)
    if not body:
        return err("Corps JSON requis", 400)

    # Champs obligatoires
    required = ["name", "birth_date", "birth_time", "latitude", "longitude"]
    missing = [f for f in required if f not in body]
    if missing:
        return err("Champs manquants", 400, detail=f"Requis : {missing}")

    try:
        birth_dt = _parse_birth_datetime(body["birth_date"], body["birth_time"])
        lat = float(body["latitude"])
        lon = float(body["longitude"])
        _validate_coords(lat, lon)
    except (ValueError, TypeError) as exc:
        return err(str(exc), 422)

    alt          = float(body.get("altitude", 0))
    house_system = body.get("house_system", current_app.config["HOUSE_SYSTEM_DEFAULT"])
    birth_place  = body.get("birth_place", "")
    ephe_path    = current_app.config["EPHE_PATH"]

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            chart = compute_natal_chart(
                name=body["name"],
                birth_dt_ut=birth_dt,
                lat=lat, lon=lon, alt=alt,
                house_system=house_system,
                ephe_path=ephe_path,
            )
    except Exception as exc:
        return err("Erreur calcul Swiss Ephemeris", 500, detail=str(exc))

    try:
        db = get_db()
        repo = ChartRepo(db)
        chart_id = repo.save_from_natal_chart(chart, birth_place=birth_place)
    except Exception as exc:
        return err("Erreur persistance", 500, detail=str(exc))

    return ok({
        "id":           chart_id,
        "name":         chart.name,
        "birth_date":   body["birth_date"],
        "birth_time":   body["birth_time"],
        "birth_place":  birth_place,
        "house_system": chart.house_system,
        "asc":          round(chart.asc, 4),
        "mc":           round(chart.mc, 4),
        "planets_count": len(chart.planets),
        "aspects_count": len(chart.aspects),
    }, 201)


# ── GET /api/charts ───────────────────────────────────────────────────────────

@charts_bp.get("/")
def list_charts():
    """Liste tous les thèmes natals (sans positions détaillées)."""
    db = get_db()
    repo = ChartRepo(db)
    records = repo.list_all()
    return ok([{
        "id":           r.id,
        "name":         r.name,
        "birth_date":   r.birth_date,
        "birth_place":  r.birth_place,
        "house_system": r.house_system,
        "asc_lon":      r.asc_lon,
        "mc_lon":       r.mc_lon,
        "created_at":   r.created_at,
    } for r in records])


# ── GET /api/charts/:id ───────────────────────────────────────────────────────

@charts_bp.get("/<int:chart_id>")
def get_chart(chart_id: int):
    """Retourne un thème complet avec positions et aspects."""
    db = get_db()
    repo = ChartRepo(db)
    rec = repo.get_by_id(chart_id)
    if not rec:
        return err("Chart introuvable", 404)

    positions = repo.get_positions(chart_id)
    aspects   = repo.get_aspects(chart_id)

    return ok({
        "id":           rec.id,
        "name":         rec.name,
        "birth_date":   rec.birth_date,
        "birth_time_ut": rec.birth_time_ut,
        "birth_place":  rec.birth_place,
        "latitude":     rec.latitude,
        "longitude":    rec.longitude,
        "altitude":     rec.altitude,
        "house_system": rec.house_system,
        "asc_lon":      rec.asc_lon,
        "mc_lon":       rec.mc_lon,
        "created_at":   rec.created_at,
        "planets": [{
            "name":       p.planet,
            "sign":       p.sign,
            "degree":     round(p.sign_degree, 4),
            "house":      p.house,
            "retrograde": p.retrograde,
            "longitude":  round(p.longitude, 4),
            "speed":      round(p.speed, 6),
        } for p in positions],
        "aspects": [{
            "planet_a": a.planet_a,
            "planet_b": a.planet_b,
            "aspect":   a.aspect,
            "orb":      round(a.orb, 3),
            "applying": a.applying,
        } for a in aspects],
    })


# ── GET /api/charts/:id/raw ───────────────────────────────────────────────────

@charts_bp.get("/<int:chart_id>/raw")
def get_chart_raw(chart_id: int):
    """Retourne le dict NatalChart brut (raw_json)."""
    db = get_db()
    repo = ChartRepo(db)
    data = repo.restore_natal_chart(chart_id)
    if data is None:
        return err("Chart introuvable", 404)
    return ok(data)


# ── GET /api/charts/:id/wheel ─────────────────────────────────────────────────

@charts_bp.get("/<int:chart_id>/wheel")
def get_wheel(chart_id: int):
    """
    Génère et retourne la roue natale SVG du thème.
    Query params : size (int, défaut 900), format (svg|png)
    """
    import json, base64, importlib

    db = get_db()
    repo = ChartRepo(db)
    data = repo.restore_natal_chart(chart_id)
    if data is None:
        return err("Chart introuvable", 404)

    size   = int(request.args.get("size", 900))
    fmt    = request.args.get("format", "svg").lower()
    size   = max(400, min(1800, size))

    # Reconstruire un NatalChart depuis le dict
    try:
        from ligen.core.engine import NatalChart, PlanetPosition, HouseCusp, AspectResult
        from dataclasses import fields

        planets = [PlanetPosition(**p) for p in data["planets"]]
        houses  = [HouseCusp(**h)      for h in data["houses"]]
        aspects = [AspectResult(**a)   for a in data["aspects"]]
        chart = NatalChart(
            name=data["name"],
            birth_dt_ut=data["birth_dt_ut"],
            latitude=data["latitude"],
            longitude_geo=data["longitude_geo"],
            altitude=data["altitude"],
            house_system=data["house_system"],
            asc=data["asc"], mc=data["mc"],
            planets=planets, houses=houses, aspects=aspects,
        )
    except Exception as exc:
        return err("Erreur reconstruction chart", 500, detail=str(exc))

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        svg_path = tmp.name

    try:
        wheel = NatalWheel(chart, size=size, show_aspects=True)
        wheel.render(svg_path)

        if fmt == "svg":
            return send_file(
                svg_path,
                mimetype="image/svg+xml",
                as_attachment=False,
                download_name=f"wheel_{chart.name.lower()}_{chart_id}.svg",
            )
        elif fmt == "png":
            try:
                import cairosvg
                png_path = svg_path.replace(".svg", ".png")
                cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=150)
                return send_file(
                    png_path, mimetype="image/png",
                    download_name=f"wheel_{chart.name.lower()}_{chart_id}.png",
                )
            except ImportError:
                return err("cairosvg non installé — utilisez format=svg", 501)
        else:
            return err(f"Format '{fmt}' non supporté (svg|png)", 400)
    except Exception as exc:
        return err("Erreur génération roue", 500, detail=str(exc))
    finally:
        if os.path.exists(svg_path):
            os.unlink(svg_path)


# ── DELETE /api/charts/:id ────────────────────────────────────────────────────

@charts_bp.delete("/<int:chart_id>")
def delete_chart(chart_id: int):
    """Supprime un thème natal et toutes ses données liées."""
    db = get_db()
    repo = ChartRepo(db)
    if not repo.get_by_id(chart_id):
        return err("Chart introuvable", 404)
    repo.delete(chart_id)
    return ok({"deleted": chart_id})
