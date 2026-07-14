"""
ligen/cli/cli.py
Ligen Astrologie — Interface en ligne de commande

Entry point : ligen (défini dans pyproject.toml)
Framework   : Click 8

Commandes
---------
  ligen chart create   — Calculer + persister un thème natal
  ligen chart list     — Lister les thèmes
  ligen chart show     — Afficher un thème (positions + aspects)
  ligen chart wheel    — Générer la roue SVG/PNG
  ligen chart delete   — Supprimer un thème

  ligen session create    — Créer une session
  ligen session list      — Lister les sessions
    ligen session show       — Afficher une session
  ligen session add-block  — Activer un bloc (A01–C06)
  ligen session close      — Fermer une session

  ligen report natal    — Générer un rapport PDF natal
  ligen report lineage  — Générer un rapport PDF de lignée

  ligen db init  — Initialiser la base de données
  ligen db info  — Statistiques de la base
  ligen db reset — Réinitialiser (avec confirmation)

  ligen audit    — Vérifie les 26 blocs, éphémérides et templates
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import warnings
from pathlib import Path

import click

# ── Résolution du chemin racine ───────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers UI ────────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    click.echo(click.style(f"  ✓ {msg}", fg="green"))

def _warn(msg: str) -> None:
    click.echo(click.style(f"  ⚠ {msg}", fg="yellow"))

def _err(msg: str) -> None:
    click.echo(click.style(f"  ✗ {msg}", fg="red"), err=True)

def _header(title: str) -> None:
    click.echo(click.style(f"\n── {title} ──", bold=True))

def _row(label: str, value: str, width: int = 18) -> None:
    click.echo(f"  {label:<{width}} {value}")


# ── Contexte partagé (DB + config) ────────────────────────────────────────────

class LigenContext:
    """Contexte Click partagé entre toutes les sous-commandes."""

    def __init__(self, db_path: str, ephe_path: str, reports_dir: str,
                 prompts_dir: str, templates_dir: str):
        self.db_path       = db_path
        self.ephe_path     = ephe_path
        self.reports_dir   = reports_dir
        self.prompts_dir   = prompts_dir
        self.templates_dir = templates_dir
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from ligen.data.db import Database
            self._db = Database(self.db_path)
            self._db.initialize()
        return self._db

    def chart_repo(self):
        from ligen.data.repository import ChartRepo
        return ChartRepo(self.db)

    def session_repo(self):
        from ligen.data.repository import SessionRepo
        return SessionRepo(self.db)

    def report_repo(self):
        from ligen.data.repository import ReportRepo
        return ReportRepo(self.db)

    def lineage_repo(self):
        from ligen.data.repository import LineageRepo
        return LineageRepo(self.db)


pass_ctx = click.make_pass_decorator(LigenContext)


# ── Groupe principal ──────────────────────────────────────────────────────────

@click.group()
@click.option("--db",       envvar="LIGEN_DB_PATH",       default="ligen.db",
              show_default=True, help="Chemin SQLite")
@click.option("--ephe",     envvar="LIGEN_EPHE_PATH",     default=os.path.expanduser("~/ephe"),
              show_default=True, help="Dossier éphémérides Swiss Ephemeris")
@click.option("--reports",  envvar="LIGEN_REPORTS_DIR",   default="reports",
              show_default=True, help="Dossier de sortie PDF")
@click.option("--prompts",  envvar="LIGEN_PROMPTS_DIR",   default="ligen/prompts/blocks",
              show_default=True, help="Dossier des blocs prompts")
@click.option("--templates",envvar="LIGEN_TEMPLATES_DIR", default="ligen/reports/templates",
              show_default=True, help="Dossier des templates Jinja2")
@click.version_option("1.0.0", prog_name="ligen")
@click.pass_context
def cli(ctx, db, ephe, reports, prompts, templates):
    """Ligen Astrologie — moteur de calcul et générateur de rapports."""
    ctx.ensure_object(dict)
    ctx.obj = LigenContext(
        db_path=db,
        ephe_path=ephe,
        reports_dir=reports,
        prompts_dir=prompts,
        templates_dir=templates,
    )


# ════════════════════════════════════════════════════════════════════════════════
# GROUPE chart
# ════════════════════════════════════════════════════════════════════════════════

@cli.group()
def chart():
    """Gestion des thèmes natals."""


@chart.command("create")
@click.option("--name",         required=True,  help="Prénom ou identifiant")
@click.option("--date",         required=True,  help="Date de naissance UT (YYYY-MM-DD)")
@click.option("--time",         required=True,  help="Heure UT (HH:MM ou HH:MM:SS)")
@click.option("--lat",          required=True,  type=float, help="Latitude GPS (N+, S-)")
@click.option("--lon",          required=True,  type=float, help="Longitude GPS (E+, W-)")
@click.option("--alt",          default=0.0,    type=float, help="Altitude en mètres")
@click.option("--place",        default="",     help="Lieu de naissance (texte libre)")
@click.option("--house-system", default="campanus",
              type=click.Choice(["campanus","placidus","koch","regiomontanus",
                                  "equal","whole_sign","porphyry","morinus","topocentric"]),
              help="Système de maisons")
@click.option("--json-out", is_flag=True, help="Sortie JSON brute")
@pass_ctx
def chart_create(ctx, name, date, time, lat, lon, alt, place, house_system, json_out):
    """Calcule et persiste un thème natal."""
    from ligen.core.engine import compute_natal_chart

    try:
        d = datetime.date.fromisoformat(date)
        t_parts = time.split(":")
        h, m, s = int(t_parts[0]), int(t_parts[1]), int(t_parts[2]) if len(t_parts) > 2 else 0
        birth_dt = datetime.datetime(d.year, d.month, d.day, h, m, s)
    except (ValueError, IndexError) as exc:
        _err(f"Format date/heure invalide : {exc}")
        sys.exit(1)

    if not json_out:
        click.echo(f"\nCalcul thème natal de {name}...")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            natal = compute_natal_chart(
                name=name, birth_dt_ut=birth_dt,
                lat=lat, lon=lon, alt=alt,
                house_system=house_system,
                ephe_path=ctx.ephe_path,
            )
        except Exception as exc:
            _err(f"Erreur Swiss Ephemeris : {exc}")
            sys.exit(1)

    chart_id = ctx.chart_repo().save_from_natal_chart(natal, birth_place=place)

    if json_out:
        click.echo(json.dumps({
            "id": chart_id, "name": name,
            "birth_date": date, "birth_time": time,
            "house_system": house_system,
            "asc": round(natal.asc, 4), "mc": round(natal.mc, 4),
        }))
        return

    from ligen.core.engine import SIGNS
    asc_sign = SIGNS[int(natal.asc / 30) % 12]
    mc_sign  = SIGNS[int(natal.mc  / 30) % 12]

    _header(f"Thème natal — {name}")
    _row("ID",           str(chart_id))
    _row("Naissance",    f"{date} {time} UT")
    if place:
        _row("Lieu",     place)
    _row("Lat / Lon",    f"{lat}° / {lon}°")
    _row("Domification", house_system.capitalize())
    _row("ASC",          f"{asc_sign} {natal.asc % 30:.2f}°")
    _row("MC",           f"{mc_sign} {natal.mc % 30:.2f}°")
    _row("Planètes",     str(len(natal.planets)))
    _row("Aspects",      str(len(natal.aspects)))
    click.echo()
    _ok(f"Thème persisté — ID {chart_id}")


@chart.command("list")
@click.option("--json-out", is_flag=True)
@pass_ctx
def chart_list(ctx, json_out):
    """Liste tous les thèmes natals."""
    records = ctx.chart_repo().list_all()
    if json_out:
        click.echo(json.dumps([{
            "id": r.id, "name": r.name,
            "birth_date": r.birth_date, "birth_place": r.birth_place,
            "house_system": r.house_system, "created_at": r.created_at,
        } for r in records]))
        return

    if not records:
        click.echo("  Aucun thème en base.")
        return

    _header(f"Thèmes natals ({len(records)})")
    for r in records:
        click.echo(f"  [{r.id:>3}]  {r.name:<20} {r.birth_date}  {r.birth_place}")


@chart.command("show")
@click.argument("chart_id", type=int)
@click.option("--aspects",  is_flag=True, help="Afficher aussi les aspects")
@click.option("--json-out", is_flag=True)
@pass_ctx
def chart_show(ctx, chart_id, aspects, json_out):
    """Affiche un thème natal complet."""
    repo = ctx.chart_repo()
    rec  = repo.get_by_id(chart_id)
    if not rec:
        _err(f"Thème ID {chart_id} introuvable")
        sys.exit(1)

    positions = repo.get_positions(chart_id)
    asp_list  = repo.get_aspects(chart_id) if aspects else []

    if json_out:
        click.echo(json.dumps({
            "chart": dict(rec.__dict__),
            "planets": [dict(p.__dict__) for p in positions],
            "aspects": [dict(a.__dict__) for a in asp_list],
        }, default=str))
        return

    _header(f"Thème : {rec.name}")
    _row("ID",           str(rec.id))
    _row("Naissance",    f"{rec.birth_date} {rec.birth_time_ut}")
    _row("Lieu",         rec.birth_place or "—")
    _row("Système",      rec.house_system)
    if rec.asc_lon:
        from ligen.core.engine import SIGNS
        _row("ASC",      f"{SIGNS[int(rec.asc_lon/30)%12]} {rec.asc_lon%30:.2f}°")
        _row("MC",       f"{SIGNS[int(rec.mc_lon/30)%12]} {rec.mc_lon%30:.2f}°")

    click.echo()
    click.echo(click.style("  Positions planétaires", bold=True))
    click.echo(f"  {'Planète':<14} {'Signe':<14} {'Degré':>7}  M   R")
    click.echo(f"  {'─'*14} {'─'*14} {'─'*7}  ─   ─")
    for p in positions:
        retro = "R" if p.retrograde else " "
        click.echo(f"  {p.planet:<14} {p.sign:<14} "
                   f"{int(p.sign_degree):02d}°{int((p.sign_degree%1)*60):02d}'  "
                   f"{p.house:<3} {retro}")

    if aspects and asp_list:
        click.echo()
        click.echo(click.style("  Aspects (triés par orbe)", bold=True))
        for a in asp_list[:15]:
            click.echo(f"  {a.planet_a:<12} {a.aspect:<12} {a.planet_b:<12} "
                       f"orbe {a.orb:.2f}°")


@chart.command("wheel")
@click.argument("chart_id", type=int)
@click.option("--output", "-o", default=None, help="Chemin de sortie (.svg)")
@click.option("--size",   default=900, type=int, show_default=True)
@click.option("--no-aspects", is_flag=True, help="Masquer les aspects")
@pass_ctx
def chart_wheel(ctx, chart_id, output, size, no_aspects):
    """Génère la roue natale SVG d'un thème."""
    from ligen.core.engine import NatalChart, PlanetPosition, HouseCusp, AspectResult
    from ligen.charts.wheel import NatalWheel

    repo = ctx.chart_repo()
    data = repo.restore_natal_chart(chart_id)
    if not data:
        _err(f"Thème ID {chart_id} introuvable")
        sys.exit(1)

    try:
        planets = [PlanetPosition(**p) for p in data["planets"]]
        houses  = [HouseCusp(**h)      for h in data["houses"]]
        asps    = [AspectResult(**a)   for a in data["aspects"]]
        natal = NatalChart(
            name=data["name"], birth_dt_ut=data["birth_dt_ut"],
            latitude=data["latitude"], longitude_geo=data["longitude_geo"],
            altitude=data["altitude"], house_system=data["house_system"],
            asc=data["asc"], mc=data["mc"],
            planets=planets, houses=houses, aspects=asps,
        )
    except Exception as exc:
        _err(f"Reconstruction chart : {exc}")
        sys.exit(1)

    if not output:
        safe = "".join(c for c in data["name"] if c.isalnum() or c in "_-")
        output = f"wheel_{safe}_{chart_id}.svg"

    wheel = NatalWheel(natal, size=size, show_aspects=not no_aspects)
    out_path = wheel.render(output)
    _ok(f"Roue générée → {out_path}")


@chart.command("delete")
@click.argument("chart_id", type=int)
@click.confirmation_option(prompt="Confirmer la suppression ?")
@pass_ctx
def chart_delete(ctx, chart_id):
    """Supprime un thème natal et toutes ses données liées."""
    repo = ctx.chart_repo()
    if not repo.get_by_id(chart_id):
        _err(f"Thème ID {chart_id} introuvable")
        sys.exit(1)
    repo.delete(chart_id)
    _ok(f"Thème {chart_id} supprimé")


# ════════════════════════════════════════════════════════════════════════════════
# GROUPE session
# ════════════════════════════════════════════════════════════════════════════════

@cli.group()
def session():
    """Gestion des sessions d'analyse."""


@session.command("create")
@click.option("--title",        required=True, help="Titre de la session")
@click.option("--subject",      required=True, help="Prénom du sujet")
@click.option("--chart-id",     default=None,  type=int, help="ID du thème lié")
@click.option("--birth-place",  default="",    help="Lieu de naissance")
@click.option("--birth-date",   default="",    help="Date lisible ex: 28/05/1983")
@click.option("--birth-time",   default="",    help="Heure lisible ex: 14h40 LT")
@click.option("--json-out",     is_flag=True)
@pass_ctx
def session_create(ctx, title, subject, chart_id, birth_place, birth_date, birth_time, json_out):
    """Crée une nouvelle session d'analyse."""
    repo = ctx.session_repo()
    sid = repo.create(
        title=title, subject_name=subject, chart_id=chart_id,
        birth_place=birth_place, birth_date_fmt=birth_date,
        birth_time_fmt=birth_time,
    )
    if json_out:
        click.echo(json.dumps({"id": sid, "title": title}))
        return
    _ok(f"Session créée — ID {sid} : {title}")


@session.command("list")
@click.option("--open-only", is_flag=True, help="Sessions ouvertes uniquement")
@click.option("--json-out",  is_flag=True)
@pass_ctx
def session_list(ctx, open_only, json_out):
    """Liste les sessions."""
    repo = ctx.session_repo()
    records = repo.list_open() if open_only else repo.list_all()
    if json_out:
        click.echo(json.dumps([{
            "id": r.id, "title": r.title, "subject_name": r.subject_name,
            "session_date": r.session_date, "is_open": r.is_open,
            "active_blocks": r.active_blocks,
        } for r in records]))
        return
    if not records:
        click.echo("  Aucune session.")
        return
    _header(f"Sessions ({len(records)})")
    for r in records:
        status = click.style("●", fg="green") if r.is_open else click.style("○", fg="white")
        blocks = ", ".join(r.active_blocks) if r.active_blocks else "—"
        click.echo(f"  {status} [{r.id:>3}]  {r.subject_name:<16} "
                   f"{r.session_date}  blocs: {blocks}")


@session.command("show")
@click.argument("session_id", type=int)
@click.option("--json-out", is_flag=True)
@pass_ctx
def session_show(ctx, session_id, json_out):
    """Affiche une session et ses blocs activés."""
    repo = ctx.session_repo()
    rec  = repo.get_by_id(session_id)
    if not rec:
        _err(f"Session {session_id} introuvable")
        sys.exit(1)
    blocks = repo.get_blocks(session_id)
    if json_out:
        click.echo(json.dumps({
            "session": rec.__dict__,
            "blocks": [b.__dict__ for b in blocks],
        }, default=str))
        return
    _header(f"Session {session_id} — {rec.title}")
    _row("Sujet",   rec.subject_name)
    _row("Date",    rec.session_date)
    _row("Statut",  "Ouverte" if rec.is_open else f"Fermée le {rec.closed_at}")
    _row("Chart ID", str(rec.chart_id) if rec.chart_id else "—")
    if rec.notes:
        _row("Notes", rec.notes)
    click.echo()
    if blocks:
        click.echo(click.style("  Blocs activés", bold=True))
        for b in blocks:
            click.echo(f"  [{b.block_id}]  {b.activated_at}")
    else:
        click.echo("  Aucun bloc activé.")


@session.command("add-block")
@click.argument("session_id", type=int)
@click.argument("block_id")
@click.option("--rendered", default="", help="Contenu rendu du bloc")
@pass_ctx
def session_add_block(ctx, session_id, block_id, rendered):
    """Active un bloc dans une session (A01–C06)."""
    repo = ctx.session_repo()
    if not repo.get_by_id(session_id):
        _err(f"Session {session_id} introuvable")
        sys.exit(1)
    repo.add_block(session_id, block_id.upper(), rendered)
    _ok(f"Bloc {block_id.upper()} activé dans la session {session_id}")


@session.command("close")
@click.argument("session_id", type=int)
@pass_ctx
def session_close(ctx, session_id):
    """Ferme une session en cours et persiste son état."""
    repo = ctx.session_repo()
    rec  = repo.get_by_id(session_id)
    if not rec:
        _err(f"Session {session_id} introuvable")
        sys.exit(1)
    if not rec.is_open:
        _warn(f"Session {session_id} déjà fermée le {rec.closed_at}")
        return
    repo.close(session_id)
    _ok(f"Session {session_id} fermée")


# ════════════════════════════════════════════════════════════════════════════════
# GROUPE report
# ════════════════════════════════════════════════════════════════════════════════

@cli.group()
def report():
    """Génération de rapports PDF."""


@report.command("natal")
@click.option("--chart-id",     required=True, type=int,  help="ID du thème natal")
@click.option("--output", "-o", default=None,             help="Chemin PDF de sortie")
@click.option("--blocks",       default="A01,A02,A03",    show_default=True,
              help="Blocs actifs séparés par virgule (ex: A01,A02,A03). Défaut : A01 (profil natal), A02 (inter-générations), A03 (patterns familiaux)")
@click.option("--birth-place",  default="")
@click.option("--birth-date",   default="")
@click.option("--birth-time",   default="")
@click.option("--title",        default="Analyse Natale Ligen")
@click.option("--no-wheel",     is_flag=True, help="Exclure la roue du PDF")
@click.option("--session-id",   default=None, type=int)
@click.option("--json-out",     is_flag=True)
@pass_ctx
def report_natal(ctx, chart_id, output, blocks, birth_place, birth_date,
                  birth_time, title, no_wheel, session_id, json_out):
    """Génère un rapport PDF natal complet."""
    from ligen.core.engine import NatalChart, PlanetPosition, HouseCusp, AspectResult
    from ligen.reports.generator import ReportGenerator, ReportConfig

    repo = ctx.chart_repo()
    rec  = repo.get_by_id(chart_id)
    if not rec:
        _err(f"Thème ID {chart_id} introuvable")
        sys.exit(1)

    data = repo.restore_natal_chart(chart_id)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            planets = [PlanetPosition(**p) for p in data["planets"]]
            houses  = [HouseCusp(**h)      for h in data["houses"]]
            asps    = [AspectResult(**a)   for a in data["aspects"]]
            natal = NatalChart(
                name=data["name"], birth_dt_ut=data["birth_dt_ut"],
                latitude=data["latitude"], longitude_geo=data["longitude_geo"],
                altitude=data["altitude"], house_system=data["house_system"],
                asc=data["asc"], mc=data["mc"],
                planets=planets, houses=houses, aspects=asps,
            )
    except Exception as exc:
        _err(f"Reconstruction chart : {exc}")
        sys.exit(1)

    active_blocks = [b.strip().upper() for b in blocks.split(",") if b.strip()]
    cfg = ReportConfig(
        subject_name=rec.name,
        birth_date=birth_date or rec.birth_date,
        birth_time=birth_time or rec.birth_time_ut[:5] + " UT",
        birth_place=birth_place or rec.birth_place,
        active_blocks=active_blocks,
        include_wheel=not no_wheel,
        report_title=title,
    )

    if not output:
        os.makedirs(ctx.reports_dir, exist_ok=True)
        ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c for c in rec.name if c.isalnum() or c in "_-")
        output = os.path.join(ctx.reports_dir, f"natal_{safe}_{ts}.pdf")

    if not json_out:
        click.echo(f"\nGénération rapport natal pour {rec.name}...")

    try:
        gen = ReportGenerator(
            chart=natal, config=cfg,
            prompts_dir=ctx.prompts_dir,
            templates_dir=ctx.templates_dir,
            ephe_path=ctx.ephe_path,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gen.render_pdf(output)
    except Exception as exc:
        _err(f"Erreur génération PDF : {exc}")
        sys.exit(1)

    # Persister en base
    report_id = ctx.report_repo().save(
        title=f"{title} — {rec.name}",
        file_path=output, report_type="natal", format="pdf",
        session_id=session_id, chart_id=chart_id,
    )

    size_kb = os.path.getsize(output) // 1024

    if json_out:
        click.echo(json.dumps({
            "report_id": report_id, "file_path": output, "size_kb": size_kb,
        }))
        return

    _ok(f"PDF généré ({size_kb} KB) → {output}")
    _ok(f"Rapport persisté — ID {report_id}")


@report.command("lineage")
@click.option("--chart-ids",    required=True,  help="IDs séparés par virgule ex: 1,2")
@click.option("--roles",        default="",     help="Rôles séparés par virgule ex: self,partner")
@click.option("--output", "-o", default=None)
@click.option("--no-wheels",    is_flag=True,   help="Exclure les roues du PDF")
@click.option("--json-out",     is_flag=True)
@pass_ctx
def report_lineage(ctx, chart_ids, roles, output, no_wheels, json_out):
    """Génère un rapport PDF de lignée multi-membres."""
    from ligen.core.engine import NatalChart, PlanetPosition, HouseCusp, AspectResult
    from ligen.lineage.engine import LineageEngine, LineageMember
    from ligen.reports.lineage_report import LineageReportGenerator

    chart_repo = ctx.chart_repo()
    ids_list   = [int(i.strip()) for i in chart_ids.split(",") if i.strip()]
    roles_list = [r.strip() for r in roles.split(",")] if roles else []

    if len(ids_list) < 2:
        _err("Au minimum 2 chart IDs requis (--chart-ids 1,2)")
        sys.exit(1)

    members = []
    for i, cid in enumerate(ids_list):
        data = chart_repo.restore_natal_chart(cid)
        if not data:
            _err(f"Thème ID {cid} introuvable")
            sys.exit(1)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                planets = [PlanetPosition(**p) for p in data["planets"]]
                houses  = [HouseCusp(**h)      for h in data["houses"]]
                asps    = [AspectResult(**a)   for a in data["aspects"]]
                natal = NatalChart(
                    name=data["name"], birth_dt_ut=data["birth_dt_ut"],
                    latitude=data["latitude"], longitude_geo=data["longitude_geo"],
                    altitude=data["altitude"], house_system=data["house_system"],
                    asc=data["asc"], mc=data["mc"],
                    planets=planets, houses=houses, aspects=asps,
                )
        except Exception as exc:
            _err(f"Reconstruction chart {cid} : {exc}")
            sys.exit(1)
        role = roles_list[i] if i < len(roles_list) else f"membre_{i+1}"
        members.append(LineageMember(chart=natal, role=role))

    if not output:
        os.makedirs(ctx.reports_dir, exist_ok=True)
        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        names = "_".join(m.chart.name[:8] for m in members)
        output = os.path.join(ctx.reports_dir, f"lineage_{names}_{ts}.pdf")

    if not json_out:
        click.echo(f"\nAnalyse de lignée : {', '.join(m.chart.name for m in members)}...")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        engine = LineageEngine(members)
        lineage_report = engine.analyze()

    try:
        gen = LineageReportGenerator(
            lineage_report=lineage_report, members=members,
            templates_dir=ctx.templates_dir, ephe_path=ctx.ephe_path,
            include_wheels=not no_wheels,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gen.render_pdf(output)
    except Exception as exc:
        _err(f"Erreur génération PDF lignée : {exc}")
        sys.exit(1)

    report_id = ctx.report_repo().save(
        title=f"Lignée — {' · '.join(m.chart.name for m in members)}",
        file_path=output, report_type="lineage", format="pdf",
    )
    size_kb = os.path.getsize(output) // 1024

    if json_out:
        click.echo(json.dumps({
            "report_id": report_id, "file_path": output, "size_kb": size_kb,
            "lineage_theme": lineage_report.lineage_theme,
        }))
        return

    _ok(f"PDF généré ({size_kb} KB) → {output}")
    _ok(f"Thème de lignée : {lineage_report.lineage_theme}")
    _ok(f"Rapport persisté — ID {report_id}")


# ════════════════════════════════════════════════════════════════════════════════
# GROUPE db
# ════════════════════════════════════════════════════════════════════════════════

@cli.group()
def db():
    """Gestion de la base de données."""


@db.command("init")
@pass_ctx
def db_init(ctx):
    """Initialise (ou vérifie) la base de données."""
    from ligen.data.db import Database
    database = Database(ctx.db_path)
    database.initialize()
    _ok(f"Base initialisée → {ctx.db_path} (version {database.schema_version()})")


@db.command("info")
@click.option("--json-out", is_flag=True)
@pass_ctx
def db_info(ctx, json_out):
    """Statistiques de la base de données."""
    d = ctx.db
    tables = ["charts","planet_positions","natal_aspects",
              "sessions","session_blocks","reports",
              "lineages","lineage_members"]
    counts = {t: d.row_count(t) for t in tables}
    counts["schema_version"] = d.schema_version()

    if json_out:
        click.echo(json.dumps(counts))
        return

    _header(f"Base de données — {ctx.db_path}")
    for t, c in counts.items():
        _row(t, str(c))


@db.command("reset")
@click.confirmation_option(prompt="Supprimer TOUTES les données ?")
@pass_ctx
def db_reset(ctx):
    """Réinitialise la base (suppression + recréation)."""
    import os
    ctx.db.close()
    if os.path.exists(ctx.db_path) and ctx.db_path != ":memory:":
        os.unlink(ctx.db_path)
        _ok(f"Base supprimée : {ctx.db_path}")
    from ligen.data.db import Database
    db_new = Database(ctx.db_path)
    db_new.initialize()
    _ok("Base recréée vide")


# ════════════════════════════════════════════════════════════════════════════════
# COMMANDE audit
# ════════════════════════════════════════════════════════════════════════════════

@cli.command()
@pass_ctx
def audit(ctx):
    """Vérifie la présence des 26 blocs d'interprétation standards (A01–A14, B01–B06, C01–C06) et signale les éléments manquants. Contrôle aussi les éphémérides et les templates."""
    import os
    _header("Audit environnement Ligen")

    # Éphémérides
    ephe = ctx.ephe_path
    if os.path.isdir(ephe):
        se1_files = list(Path(ephe).glob("*.se1"))
        _ok(f"Éphémérides : {ephe} ({len(se1_files)} fichiers .se1)")
        for f in ["seas_18.se1", "semo_18.se1", "sepl_18.se1"]:
            status = "✓" if (Path(ephe) / f).exists() else "✗ MANQUANT"
            click.echo(f"    {f}  {status}")
    else:
        _warn(f"Éphémérides introuvables : {ephe}")

    # Blocs prompts
    prompts = ctx.prompts_dir
    if os.path.isdir(prompts):
        from ligen.prompts.loader import PromptLoader
        loader  = PromptLoader(prompts)
        result  = loader.audit()
        present = len(result["present"])
        missing = len(result["missing"])
        if missing == 0:
            _ok(f"Blocs prompts : {present}/26 présents ({prompts})")
        else:
            _warn(f"Blocs prompts : {present}/26 — manquants : {result['missing']}")
    else:
        _warn(f"Dossier prompts introuvable : {prompts}")

    # Templates Jinja2
    templates = ctx.templates_dir
    if os.path.isdir(templates):
        j2_files = list(Path(templates).glob("*.j2"))
        _ok(f"Templates : {templates} ({len(j2_files)} fichiers .j2)")
    else:
        _err(f"Templates introuvables : {templates}  ← CRITIQUE")

    # Base de données
    try:
        d = ctx.db
        v = d.schema_version()
        charts_n = d.row_count("charts")
        _ok(f"Base SQLite : {ctx.db_path} (version {v}, {charts_n} thèmes)")
    except Exception as exc:
        _warn(f"Base SQLite : {exc}")

    # Dépendances Python
    click.echo()
    click.echo(click.style("  Dépendances", bold=True))
    deps = ["flask","weasyprint","jinja2","swisseph","svgwrite","cairosvg","click"]
    for dep in deps:
        try:
            import importlib.metadata as m
            ver = m.version(dep)
            click.echo(f"    {dep:<14} {ver}")
        except Exception:
            _warn(f"{dep} non installé")

    click.echo()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    cli(auto_envvar_prefix="LIGEN")


if __name__ == "__main__":
    main()
