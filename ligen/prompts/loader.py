"""
ligen/prompts/loader.py
Ligen Astralogie — Loader strict des blocs A1→C6 (MODE STRICT PROMPTS)

Règle absolue : aucun prompt inline dans le code applicatif.
Tout bloc non présent dans le référentiel lève une erreur dure.

Structure attendue du répertoire de blocs :
  prompts/
    A01.md  A02.md ... A14.md
    B01.md  B02.md ... B06.md
    C01.md  C02.md ... C06.md
"""

from __future__ import annotations

import re
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# ── Catalogue canonique ───────────────────────────────────────────────────────

# Blocs A (Session Astro) — placeholders obligatoires
BLOCK_CATALOG: dict[str, dict] = {
    "A01": {"label": "session.start",          "placeholders": ["PRENOM_USER", "DATE_JOUR", "NB_MEMBRES"]},
    "A02": {"label": "membre.select",           "placeholders": ["NOM_MEMBRE", "DATE_NAISSANCE", "HEURE_NAISSANCE", "LIEU_NAISSANCE", "SIGNE_SOLEIL", "SIGNE_LUNE", "ASCENDANT"]},
    "A03": {"label": "action.axe_luminaires",   "placeholders": ["NOM_MEMBRE", "SIGNE_SOLEIL", "MAISON_SOLEIL", "SIGNE_LUNE", "MAISON_LUNE", "ASPECT_SOL_LUN"]},
    "A04": {"label": "action.synastrie_duo",    "placeholders": ["MEMBRE_A", "MEMBRE_B", "LIEN", "ASPECTS_MAJEURS"]},
    "A05": {"label": "action.triangle",         "placeholders": ["MEMBRE_A", "MEMBRE_B", "MEMBRE_C", "LIENS_TRIO", "AXES_TENSION", "AXE_RESSOURCE"]},
    "A06": {"label": "action.karma",            "placeholders": ["NOM_MEMBRE", "NOEUD_NORD", "NOEUD_SUD", "PLANETE_NODAL"]},
    "A07": {"label": "action.chiron",           "placeholders": ["NOM_MEMBRE", "CHIRON_SIGNE", "CHIRON_MAISON", "ASPECTS_CHIRON"]},
    "A08": {"label": "action.eclipse",          "placeholders": ["NOM_MEMBRE", "TYPE_ECLIPSE", "DATE_ECLIPSE", "DEGRE_ECLIPSE", "MAISON_TOUCHEE"]},
    "A09": {"label": "action.ressources",       "placeholders": ["LISTE_MEMBRES", "TRIGONES_INTER", "PLANETES_SEXTILE"]},
    "A10": {"label": "action.tensions",         "placeholders": ["LISTE_MEMBRES", "CARRES_INTER", "OPPOSITIONS_INTER", "NOEUD_TENSION"]},
    "A11": {"label": "action.transits",         "placeholders": ["NOM_MEMBRE", "PLANETE_TRANSIT", "POINT_NATAL_TOUCHE", "TYPE_ASPECT_TRANSIT", "DATE_DEBUT_TRANSIT"]},
    "A12": {"label": "action.conseil",          "placeholders": ["NOM_MEMBRE_OU_SYSTEME", "THEME_PRINCIPAL", "PLANETE_CLE"], "prerequisite": ["A01"]},
    "A13": {"label": "session.close",           "placeholders": ["PRENOM_USER", "NB_BLOCS_ACTIVES", "THEME_CLE_SESSION"]},
    "A14": {"label": "action.exporter",         "placeholders": ["PRENOM_USER", "DATE_SESSION", "LISTE_BLOCS_ACTIVES", "FORMAT_EXPORT"], "prerequisite": ["A13"]},
    # Blocs B (Synastrie Familiale)
    "B01": {"label": "action.synastrie",        "placeholders": ["PRENOM_USER", "PRENOM_PERSONNE_B", "LIEN_FAMILIAL", "ELEMENT_COMMUN"], "prerequisite": ["A01"]},
    "B02": {"label": "action.aspects",          "placeholders": ["PRENOM_USER", "PRENOM_PERSONNE_B", "ASPECT_MAJEUR", "PLANETE_1", "PLANETE_2"], "prerequisite": ["B01"]},
    "B03": {"label": "action.themes_communs",   "placeholders": ["PRENOM_USER", "PRENOM_PERSONNE_B", "THEME_COMMUN_1", "THEME_COMMUN_2"], "prerequisite": ["B01"]},
    "B04": {"label": "action.conseils_lien",    "placeholders": ["PRENOM_USER", "PRENOM_PERSONNE_B", "DEFI_PRINCIPAL", "FORCE_COMMUNE"], "prerequisite": ["B01"]},
    "B05": {"label": "action.karma_lien",       "placeholders": ["PRENOM_USER", "PRENOM_PERSONNE_B", "NOEUD_DOMINANT", "LECON_KARMIQUE"], "prerequisite": ["A06", "B01"]},
    "B06": {"label": "action.message_lien",     "placeholders": ["PRENOM_USER", "PRENOM_PERSONNE_B", "INTENTION_MESSAGE", "TON_CHOISI"], "prerequisite": ["B01"]},
    # Blocs C (Mise en Page)
    "C01": {"label": "appel_simultane_apres",   "placeholders": ["PRENOM_USER", "DATE_SESSION", "TITRE_SECTION", "CONTENU_BLOC"], "prerequisite": ["A01"]},
    "C02": {"label": "action.carte_visuelle",   "placeholders": ["PRENOM_USER", "DATE_NAISSANCE", "HEURE_NAISSANCE", "LIEU_NAISSANCE", "ELEMENTS_A_AFFICHER"]},
    "C03": {"label": "action.generer_rapport",  "placeholders": ["PRENOM_USER", "DATE_SESSION", "LISTE_BLOCS_ACTIVES", "FORMAT_EXPORT"], "prerequisite": ["A13", "C01"]},
    "C04": {"label": "action.synthese",         "placeholders": ["PRENOM_USER", "DATE_SESSION", "MOT_CLE_SESSION", "THEME_DOMINANT", "PLANETE_FOCUS"]},
    "C05": {"label": "action.newsletter",       "placeholders": ["PRENOM_USER", "PERIODE_ASTRO", "THEME_NEWSLETTER", "PLANETE_DU_MOMENT", "CONSEIL_PRATIQUE"]},
    "C06": {"label": "action.post_social",      "placeholders": ["PRENOM_USER", "RESEAU_SOCIAL", "THEME_POST", "SIGNE_OU_PLANETE", "HASHTAGS"]},
}

ALL_BLOCK_IDS = set(BLOCK_CATALOG.keys())

# ── Exceptions ────────────────────────────────────────────────────────────────

class BlockNotFoundError(RuntimeError):
    """Bloc absent du système de fichiers — STOP_COMPLET requis."""
    pass

class BlockMissingPlaceholderError(ValueError):
    """Un placeholder obligatoire n'a pas été fourni à la substitution."""
    pass

class PrerequisiteNotMetError(RuntimeError):
    """Un prérequis de bloc n'est pas satisfait dans la session courante."""
    pass

class UnknownBlockError(KeyError):
    """ID de bloc non reconnu dans le catalogue canonique."""
    pass

# ── Dataclass de résultat ─────────────────────────────────────────────────────

@dataclass
class RenderedBlock:
    block_id: str
    label: str
    content: str                # texte final après substitution
    sha256: str                 # empreinte du fichier source
    placeholders_filled: dict[str, str]


# ── Loader ────────────────────────────────────────────────────────────────────

class PromptLoader:
    """
    Loader strict MODE STRICT PROMPTS.

    Utilisation
    -----------
    loader = PromptLoader(prompts_dir="ligen/prompts/blocks")
    result = loader.render("A03", {
        "NOM_MEMBRE": "Fred",
        "SIGNE_SOLEIL": "Gémeaux",
        "MAISON_SOLEIL": "12",
        "SIGNE_LUNE": "Scorpion",
        "MAISON_LUNE": "5",
        "ASPECT_SOL_LUN": "Carré",
    }, active_blocks={"A01", "A02"})
    print(result.content)
    """

    def __init__(self, prompts_dir: str | Path = "ligen/prompts/blocks"):
        self.dir = Path(prompts_dir)
        if not self.dir.exists():
            raise FileNotFoundError(
                f"Répertoire de blocs introuvable : {self.dir.resolve()}"
            )
        self._cache: dict[str, tuple[str, str]] = {}  # id → (content, sha256)

    # ── Chargement ────────────────────────────────────────────────────────────

    def _load_block_file(self, block_id: str) -> tuple[str, str]:
        """Charge le fichier .md d'un bloc et retourne (contenu, sha256)."""
        if block_id in self._cache:
            return self._cache[block_id]

        candidates = list(self.dir.glob(f"{block_id}*.md"))
        if not candidates:
            candidates = list(self.dir.glob(f"{block_id}*.txt"))
        if not candidates:
            raise BlockNotFoundError(
                f"ERR_BLOC : fichier bloc '{block_id}' absent dans {self.dir}. "
                f"STOP_COMPLET — créez le fichier {block_id}.md dans {self.dir}."
            )

        path = candidates[0]
        raw = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(raw.encode()).hexdigest()
        self._cache[block_id] = (raw, sha)
        return raw, sha

    # ── Validation ────────────────────────────────────────────────────────────

    def _check_catalog(self, block_id: str) -> dict:
        """Vérifie que le bloc existe dans le catalogue canonique."""
        if block_id not in BLOCK_CATALOG:
            raise UnknownBlockError(
                f"Bloc '{block_id}' absent du catalogue canonique. "
                f"IDs valides : {sorted(ALL_BLOCK_IDS)}"
            )
        return BLOCK_CATALOG[block_id]

    def _check_prerequisites(
        self, block_id: str, active_blocks: set[str]
    ) -> None:
        """Vérifie que les prérequis du bloc sont dans active_blocks."""
        meta = BLOCK_CATALOG[block_id]
        prereqs = meta.get("prerequisite", [])
        missing = [p for p in prereqs if p not in active_blocks]
        if missing:
            raise PrerequisiteNotMetError(
                f"Bloc '{block_id}' exige {missing} — "
                f"blocs actifs actuels : {sorted(active_blocks)}. "
                f"Activez d'abord : {missing}."
            )

    def _substitute(self, template: str, values: dict[str, str]) -> str:
        """Remplace les {{PLACEHOLDER}} dans le template."""
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            if key not in values:
                raise BlockMissingPlaceholderError(
                    f"Placeholder '{key}' requis mais absent dans les valeurs fournies."
                )
            return values[key]

        return re.sub(r"\{\{(\w+)\}\}", replacer, template)

    # ── API publique ──────────────────────────────────────────────────────────

    def render(
        self,
        block_id: str,
        values: dict[str, str],
        active_blocks: Optional[set[str]] = None,
    ) -> RenderedBlock:
        """
        Charge, valide et substitue un bloc prompt.

        Paramètres
        ----------
        block_id      : identifiant canonique (ex: "A03")
        values        : dict {PLACEHOLDER: valeur}
        active_blocks : ensemble des blocs déjà activés dans la session
                        (nécessaire pour vérifier les prérequis)

        Retourne
        --------
        RenderedBlock avec contenu final et métadonnées

        Lève
        ----
        UnknownBlockError          : bloc hors catalogue
        BlockNotFoundError         : fichier absent → STOP_COMPLET
        PrerequisiteNotMetError    : prérequis non satisfait
        BlockMissingPlaceholderError : placeholder manquant
        """
        block_id = block_id.upper().strip()
        meta = self._check_catalog(block_id)

        if active_blocks is None:
            active_blocks = set()

        self._check_prerequisites(block_id, active_blocks)

        template, sha = self._load_block_file(block_id)

        # Vérification que tous les placeholders connus du catalogue sont fournis
        missing_known = [p for p in meta["placeholders"] if p not in values]
        if missing_known:
            raise BlockMissingPlaceholderError(
                f"Bloc '{block_id}' — placeholders manquants : {missing_known}"
            )

        content = self._substitute(template, values)

        return RenderedBlock(
            block_id=block_id,
            label=meta["label"],
            content=content,
            sha256=sha,
            placeholders_filled=values,
        )

    def list_available(self) -> list[str]:
        """Retourne les IDs des blocs dont le fichier est présent sur disque."""
        present = []
        for bid in ALL_BLOCK_IDS:
            candidates = (
                list(self.dir.glob(f"{bid}*.md")) +
                list(self.dir.glob(f"{bid}*.txt"))
            )
            if candidates:
                present.append(bid)
        return sorted(present)

    def audit(self) -> dict[str, list[str]]:
        """
        Audit complet : retourne {"present": [...], "missing": [...]}.
        Utile pour vérifier l'état du référentiel avant une session.
        """
        present = set(self.list_available())
        missing = sorted(ALL_BLOCK_IDS - present)
        return {"present": sorted(present), "missing": missing}


# ── CLI minimal ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, sys

    prompts_dir = sys.argv[1] if len(sys.argv) > 1 else "ligen/prompts/blocks"
    loader = PromptLoader(prompts_dir)
    audit = loader.audit()
    print("=== AUDIT BLOCS ===")
    print(f"Présents ({len(audit['present'])}) : {audit['present']}")
    print(f"Manquants ({len(audit['missing'])}) : {audit['missing']}")
