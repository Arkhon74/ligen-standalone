"""
ligen/lineage/synastry.py
Ligen Astralogie — Rendu textuel synastrie par paire

Prend un LineageReport et produit des sections textuelles lisibles
pour chaque paire de membres : aspects, thèmes communs, tensions, ressources.

Usage
-----
    from ligen.lineage.synastry import SynastryRenderer

    renderer = SynastryRenderer(report)
    sections = renderer.render_all_pairs()
    for pair_name, text in sections.items():
        print(pair_name, text[:200])
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Optional

try:
    from ligen.lineage.engine import (
        LineageReport, LineageMember, InterAspect,
        NodalResonance, PERSONAL_PLANETS, KARMIC_POINTS,
    )
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ligen.lineage.engine import (
        LineageReport, LineageMember, InterAspect,
        NodalResonance, PERSONAL_PLANETS, KARMIC_POINTS,
    )


# ── Thèmes astrologique par planète (pour les narratives) ────────────────────

PLANET_THEMES: dict[str, str] = {
    "Soleil":     "identité, vitalité, expression du moi",
    "Lune":       "émotions, sécurité, monde intérieur",
    "Mercure":    "communication, pensée, échanges",
    "Vénus":      "amour, valeurs, attractivité",
    "Mars":       "action, désir, affirmation",
    "Jupiter":    "expansion, foi, philosophie",
    "Saturne":    "structure, limites, maturité",
    "Uranus":     "originalité, rupture, libération",
    "Neptune":    "idéal, spiritualité, dissolution",
    "Pluton":     "transformation, pouvoir, profondeur",
    "Nœud Nord":  "mission d'âme, évolution",
    "Chiron":     "blessure sacrée, guérison",
    "Lilith Moy": "féminin sauvage, autonomie",
    "Cérès":      "nourrissage, soin",
    "Pallas":     "stratégie, sagesse",
    "Junon":      "engagement, loyauté",
    "Vesta":      "dévotion, focus sacré",
}

ASPECT_DYNAMICS: dict[str, tuple[str, str]] = {
    # (qualité, dynamique)
    "Conjonction": ("fusion",    "activation directe et intense"),
    "Trigone":     ("harmonie",  "fluidité naturelle, don partagé"),
    "Sextile":     ("opportunité", "complémentarité activable"),
    "Opposition":  ("polarité",  "tension créatrice, miroir"),
    "Carré":       ("friction",  "défi mutuel, apprentissage forcé"),
    "Quinconce":   ("ajustement", "irritation productive, adaptation"),
    "Semi-sextile":("contact",   "lien subtil, échange discret"),
}


# ── Dataclasses de sortie ─────────────────────────────────────────────────────

@dataclass
class PairSection:
    """Analyse textuelle d'une paire de membres."""
    pair_key:     str          # "Fred↔Olivia"
    member_a:     str
    member_b:     str
    aspect_count: int
    top_aspects:  list[str]    # lignes narratives
    karmic_links: list[str]    # résonances nodales de cette paire
    resources:    list[str]    # aspects harmoniques
    tensions:     list[str]    # aspects tendus
    themes:       list[str]    # thèmes communs identifiés
    synthesis:    str          # paragraphe de synthèse


# ── Renderer ──────────────────────────────────────────────────────────────────

class SynastryRenderer:
    """
    Produit les sections textuelles d'une synastrie de lignée.

    Paramètres
    ----------
    report   : LineageReport issu de LineageEngine.analyze()
    members  : liste des LineageMember originaux (pour accès aux rôles)
    """

    def __init__(
        self,
        report: LineageReport,
        members: Optional[list[LineageMember]] = None,
    ):
        self.report  = report
        self.members = members or []

    def _role(self, name: str) -> str:
        if not self.members:
            return name
        m = next((m for m in self.members if m.chart.name == name), None)
        return f"{name} ({m.role})" if m else name

    def _narrative_aspect(self, ia: InterAspect) -> str:
        """Une ligne narrative pour un aspect inter-thème."""
        dyn = ASPECT_DYNAMICS.get(ia.aspect, ("lien", "connexion"))
        theme_a = PLANET_THEMES.get(ia.planet_a, ia.planet_a)
        theme_b = PLANET_THEMES.get(ia.planet_b, ia.planet_b)
        retro_note = ""
        return (
            f"{ia.planet_a} {ia.member_a} {ia.aspect} "
            f"{ia.planet_b} {ia.member_b} "
            f"(orbe {ia.orb:.2f}°) — {dyn[0]} : "
            f"{theme_a} rencontre {theme_b}"
        )

    def _pair_aspects(self, name_a: str, name_b: str) -> list[InterAspect]:
        """Filtre les aspects inter-thèmes pour une paire donnée."""
        return [
            ia for ia in self.report.inter_aspects
            if (ia.member_a == name_a and ia.member_b == name_b)
            or (ia.member_a == name_b and ia.member_b == name_a)
        ]

    def _pair_nodal(self, name_a: str, name_b: str) -> list[NodalResonance]:
        return [
            nr for nr in self.report.nodal_resonances
            if (nr.member_planet == name_a and nr.member_node == name_b)
            or (nr.member_planet == name_b and nr.member_node == name_a)
        ]

    def _identify_themes(self, aspects: list[InterAspect]) -> list[str]:
        """Identifie les thèmes communs dominants d'une paire."""
        theme_counts: dict[str, int] = {}
        for ia in aspects:
            for planet in [ia.planet_a, ia.planet_b]:
                theme = PLANET_THEMES.get(planet, "")
                if theme:
                    # Extraire le premier mot-clé
                    key = theme.split(",")[0].strip()
                    theme_counts[key] = theme_counts.get(key, 0) + 1

        # Retourner les 3 thèmes les plus fréquents
        sorted_themes = sorted(theme_counts.items(), key=lambda x: -x[1])
        return [t[0] for t in sorted_themes[:3]]

    def _synthesize_pair(
        self,
        name_a: str,
        name_b: str,
        aspects: list[InterAspect],
        nodal: list[NodalResonance],
        themes: list[str],
    ) -> str:
        """Paragraphe de synthèse pour une paire."""
        n_asp = len(aspects)
        n_harm = sum(1 for a in aspects if a.aspect in ("Trigone", "Sextile", "Conjonction"))
        n_tense = sum(1 for a in aspects if a.aspect in ("Carré", "Opposition", "Quinconce"))
        n_nodal = len(nodal)

        balance = "tension" if n_tense > n_harm else ("harmonie" if n_harm > n_tense else "équilibre")

        # Aspect le plus fort (poids max, orbe min parmi personnels)
        personal = [a for a in aspects if a.planet_a in PERSONAL_PLANETS or a.planet_b in PERSONAL_PLANETS]
        top = sorted(personal, key=lambda x: (-x.weight, x.orb))[0] if personal else None
        top_str = (
            f"L'axe le plus actif est {top.planet_a}–{top.planet_b} "
            f"({top.aspect}, orbe {top.orb:.2f}°)."
        ) if top else ""

        karmic_str = (
            f"Le lien porte {n_nodal} résonance(s) nodale(s), "
            f"signalant une mémoire d'âme commune."
        ) if n_nodal > 0 else ""

        themes_str = f"Thèmes dominants : {', '.join(themes)}." if themes else ""

        return (
            f"La synastrie {name_a}–{name_b} présente {n_asp} aspects inter-thèmes "
            f"({n_harm} harmoniques, {n_tense} tendus) — polarité globale : {balance}. "
            f"{top_str} {karmic_str} {themes_str}"
        ).strip()

    def render_pair(self, name_a: str, name_b: str) -> PairSection:
        """Rend l'analyse complète d'une paire."""
        aspects  = self._pair_aspects(name_a, name_b)
        nodal    = self._pair_nodal(name_a, name_b)
        themes   = self._identify_themes(aspects)

        resources = [
            self._narrative_aspect(a) for a in aspects
            if a.aspect in ("Trigone", "Sextile", "Conjonction")
        ][:6]
        tensions = [
            self._narrative_aspect(a) for a in aspects
            if a.aspect in ("Carré", "Opposition", "Quinconce")
        ][:6]
        top_aspects = [self._narrative_aspect(a) for a in aspects[:5]]

        karmic_links = [
            f"{nr.planet} {nr.member_planet} {nr.aspect} "
            f"{nr.node_type} {nr.member_node} (orbe {nr.orb:.2f}°)"
            for nr in nodal[:5]
        ]

        synth = self._synthesize_pair(name_a, name_b, aspects, nodal, themes)

        return PairSection(
            pair_key=f"{name_a}↔{name_b}",
            member_a=name_a,
            member_b=name_b,
            aspect_count=len(aspects),
            top_aspects=top_aspects,
            karmic_links=karmic_links,
            resources=resources,
            tensions=tensions,
            themes=themes,
            synthesis=synth,
        )

    def render_all_pairs(self) -> dict[str, PairSection]:
        """
        Rend toutes les paires du rapport.
        Retourne un dict {pair_key: PairSection}.
        """
        names = self.report.members
        result: dict[str, PairSection] = {}
        for a, b in itertools.combinations(names, 2):
            section = self.render_pair(a, b)
            result[section.pair_key] = section
        return result

    def render_lineage_summary(self) -> str:
        """
        Texte de synthèse global de la lignée (tous membres confondus).
        """
        r = self.report
        lines = [
            f"LIGNÉE : {' — '.join(r.members)}",
            f"Thème central : {r.lineage_theme}",
            "",
            f"Profil élémentaire : "
            f"Feu {r.element_profile.fire}% · "
            f"Terre {r.element_profile.earth}% · "
            f"Air {r.element_profile.air}% · "
            f"Eau {r.element_profile.water}%",
            f"  → Dominant : {r.element_profile.dominant} | "
            f"Carence systémique : {r.element_profile.deficient}",
            "",
            f"Profil modal : "
            f"Cardinal {r.modal_profile.cardinal}% · "
            f"Fixe {r.modal_profile.fixed}% · "
            f"Mutable {r.modal_profile.mutable}%",
            f"  → Dominant : {r.modal_profile.dominant}",
            "",
        ]

        if r.stelliums:
            lines.append("Stelliums de lignée :")
            for s in r.stelliums[:3]:
                members_str = ", ".join({e[0] for e in s.planets})
                lines.append(
                    f"  {s.sign} : {s.count} planètes ({members_str})"
                )
            lines.append("")

        if r.repeated_patterns:
            lines.append("Patterns répétés :")
            for p in r.repeated_patterns[:5]:
                lines.append(
                    f"  {p.planet} en {p.aspect_type} × {p.count} paires"
                )
            lines.append("")

        if r.systemic_tensions:
            lines.append("Tensions systémiques :")
            for t in r.systemic_tensions[:3]:
                lines.append(
                    f"  {t.tension_type} axe {t.axis} "
                    f"({', '.join(t.involved)}) × {t.count}"
                )
            lines.append("")

        lines.append("Top ressources :")
        for res in r.top_resources:
            lines.append(f"  + {res}")
        lines.append("")
        lines.append("Top tensions :")
        for ten in r.top_tensions:
            lines.append(f"  - {ten}")

        return "\n".join(lines)
