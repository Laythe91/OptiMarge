import streamlit as st
import pandas as pd
import numpy as np
import re
import unicodedata
import io
from difflib import SequenceMatcher
import pdfplumber


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="OptiMarge - Comparateur Instantané",
    page_icon="🛒",
    layout="wide",
)


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }

    .small-muted {
        color: #6b7280;
        font-size: 0.88rem;
    }

    [data-testid="stFileUploader"] {
        border-radius: 12px;
    }

    div.stButton > button,
    div.stDownloadButton > button {
        width: 100%;
        border-radius: 10px;
        min-height: 44px;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.6rem;
    }

    @media (max-width: 600px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
            padding-top: 0.8rem;
        }

        .main-title {
            font-size: 1.7rem;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.25rem;
        }

        .small-muted {
            font-size: 0.82rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# TITRE
# ============================================================

st.markdown(
    '<div class="main-title">🛒 OptiMarge Food</div>',
    unsafe_allow_html=True,
)

st.caption(
    "Compare automatiquement les tarifs de tes fournisseurs "
    "et identifie le meilleur prix comparable pour chaque produit."
)


# ============================================================
# NORMALISATION TEXTE
# ============================================================

def normaliser_texte(texte):
    """
    Normalisation générale :
    - accents supprimés
    - minuscules
    - espaces normalisés
    - symbole × converti en x
    """

    if texte is None or pd.isna(texte):
        return ""

    texte = str(texte)

    texte = unicodedata.normalize("NFKD", texte)

    texte = "".join(
        c for c in texte
        if not unicodedata.combining(c)
    )

    texte = texte.lower()
    texte = texte.replace("×", "x")
    texte = texte.replace("’", "'")
    texte = re.sub(r"\s+", " ", texte).strip()

    return texte


# ============================================================
# MOTS PEU DISCRIMINANTS
# ============================================================

MOTS_GRAMMATICAUX = {
    "de",
    "du",
    "des",
    "d",
    "la",
    "le",
    "les",
    "a",
    "au",
    "aux",
    "of",
    "the",
}


def normaliser_produit(texte):
    """
    Normalisation du nom du produit.

    IMPORTANT :
    le conditionnement doit avoir été retiré avant cette fonction.
    """

    texte = normaliser_texte(texte)

    texte = texte.replace("'", " ")

    texte = re.sub(r"[^a-z0-9]+", " ", texte)

    mots = texte.split()

    # Retrait de mots grammaticaux uniquement
    mots = [
        mot for mot in mots
        if mot not in MOTS_GRAMMATICAUX
    ]

    return " ".join(mots).upper().strip()


# ============================================================
# CLE DE MATCHING PRODUIT
# ============================================================

def cle_produit_fuzzy(texte):
    """
    Clé secondaire pour la comparaison approximative.

    Exemple :
        Jus d'orange
        Jus Orange
        Jus d orange

    deviennent :
        JUS ORANGE
    """

    texte = normaliser_produit(texte)

    # Réduction de quelques variantes fréquentes
    remplacements = {
        "JUS DE ": "JUS ",
        "JUS D ": "JUS ",
    }

    for ancien, nouveau in remplacements.items():
        if texte.startswith(ancien):
            texte = texte.replace(
                ancien,
                nouveau,
                1,
            )

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    ).strip()

    return texte


# ============================================================
# SIMILARITE PRODUITS
# ============================================================

def similarite_texte(a, b):
    """
    Similarité globale entre deux noms.
    Retourne une valeur entre 0 et 1.
    """

    a = normaliser_texte(a)
    b = normaliser_texte(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    ratio_global = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()

    tokens_a = set(
        normaliser_produit(a).split()
    )

    tokens_b = set(
        normaliser_produit(b).split()
    )

    if tokens_a and tokens_b:
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)

        ratio_tokens = (
            intersection / union
            if union
            else 0
        )
    else:
        ratio_tokens = 0

    # On privilégie les mots communs mais on conserve
    # la similarité globale pour gérer les petites fautes.
    return (
        0.60 * ratio_global
        + 0.40 * ratio_tokens
    )


# ============================================================
# MATCHING DES PRODUITS
# ============================================================

SEUIL_MATCHING_FORT = 0.92
SEUIL_MATCHING_PROBABLE = 0.86


def trouver_groupe_produit(
    nom_produit,
    unite_etalon,
    groupes_existants,
):
    """
    Cherche le groupe produit correspondant.

    On ne compare que les produits de même famille d'unité :
        KG avec KG
        L avec L
        U avec U

    Cela évite par exemple de rapprocher arbitrairement
    un produit vendu au litre et un produit vendu au kilo.
    """

    if not nom_produit:
        return None, 0.0, "aucune correspondance"

    cle = cle_produit_fuzzy(nom_produit)

    # --------------------------------------------------------
    # 1. Correspondance exacte
    # --------------------------------------------------------

    for groupe in groupes_existants:

        if groupe["unite_etalon"] != unite_etalon:
            continue

        if groupe["cle"] == cle:
            return (
                groupe["id"],
                1.0,
                "exacte",
            )

    # --------------------------------------------------------
    # 2. Correspondance approximative
    # --------------------------------------------------------

    meilleur_id = None
    meilleure_score = 0.0

    for groupe in groupes_existants:

        if groupe["unite_etalon"] != unite_etalon:
            continue

        score = similarite_texte(
            cle,
            groupe["cle"],
        )

        if score > meilleure_score:
            meilleure_score = score
            meilleur_id = groupe["id"]

    if meilleure_score >= SEUIL_MATCHING_FORT:
        return (
            meilleur_id,
            meilleure_score,
            "forte",
        )

    if meilleure_score >= SEUIL_MATCHING_PROBABLE:
        return (
            meilleur_id,
            meilleure_score,
            "probable",
        )

    return (
        None,
        meilleure_score,
        "aucune correspondance",
    )


# ============================================================
# CONFIGURATION REGIONALE
# ============================================================

def configuration_region(region):

    if region == "🇨🇦 Canada":
        return {
            "pays": "CA",
            "devise": "CAD",
            "symbole": "CA$",

            "mots_produit": [
                "product",
                "item",
                "description",
                "product name",
                "article",
                "produit",
                "designation",
                "description produit",
                "nom produit",
            ],

            "mots_prix": [
                "price",
                "prix",
                "cost",
                "cout",
                "unit price",
                "unit cost",
                "selling price",
                "wholesale price",
                "prix unitaire",
                "prix fournisseur",
                "tarif",
                "amount",
                "montant",
            ],
        }

    return {
        "pays": "FR",
        "devise": "EUR",
        "symbole": "€",

        "mots_produit": [
            "produit",
            "designation",
            "désignation",
            "description",
            "article",
            "nom produit",
            "libelle",
            "libellé",
            "product",
            "item",
        ],

        "mots_prix": [
            "prix",
            "prix unitaire",
            "prix fournisseur",
            "tarif",
            "cout",
            "coût",
            "montant",
            "price",
            "unit price",
            "unit cost",
            "selling price",
            "wholesale price",
        ],
    }


# ============================================================
# PRIX
# ============================================================

def convertir_prix_international(
    valeur,
    pays="FR",
):
    """
    Convertit différentes écritures de prix en float.

    Exemples :
        12,50
        12.50
        1 234,50
        €12,50
        CA$ 12.50
        $12.50
        1,234.50
    """

    if pd.isna(valeur):
        return np.nan

    if isinstance(
        valeur,
        (
            int,
            float,
            np.integer,
            np.floating,
        ),
    ):
        valeur = float(valeur)

        return (
            valeur
            if valeur >= 0
            else np.nan
        )

    s = str(valeur).strip()

    if not s:
        return np.nan

    s = s.replace(
        "\u00a0",
        " ",
    )

    s = re.sub(
        r"(CA\$|CAD|USD|EUR|EURO|DOLLARS?|"
        r"DOLLARS?\s+CANADIENS?|€|\$|£)",
        "",
        s,
        flags=re.IGNORECASE,
    )

    s = s.strip()

    s = re.sub(
        r"[^0-9,\.\-]",
        "",
        s,
    )

    if not s:
        return np.nan

    if "-" in s and not s.startswith("-"):
        return np.nan

    try:

        # 1.234,56
        # 1,234.56
        if "," in s and "." in s:

            derniere_virgule = s.rfind(",")
            dernier_point = s.rfind(".")

            if derniere_virgule > dernier_point:
                s = s.replace(".", "")
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")

        elif "," in s:

            morceaux = s.split(",")

            if len(morceaux) > 2:
                s = "".join(morceaux)

            else:
                avant, apres = morceaux

                if (
                    len(apres) == 3
                    and pays == "CA"
                ):
                    s = avant + apres
                else:
                    s = avant + "." + apres

        elif s.count(".") > 1:
            s = "".join(
                s.split(".")
            )

        resultat = float(s)

        if resultat < 0:
            return np.nan

        return resultat

    except (
        ValueError,
        TypeError,
    ):
        return np.nan


# ============================================================
# UNITES
# ============================================================

UNITE_MASSE = {
    "g": ("KG", 0.001),
    "kg": ("KG", 1.0),
    "kilo": ("KG", 1.0),
    "kilos": ("KG", 1.0),
    "kilogramme": ("KG", 1.0),
    "kilogrammes": ("KG", 1.0),

    "lb": ("KG", 0.45359237),
    "lbs": ("KG", 0.45359237),
    "pound": ("KG", 0.45359237),
    "pounds": ("KG", 0.45359237),

    "oz": ("KG", 0.028349523125),
    "ounce": ("KG", 0.028349523125),
    "ounces": ("KG", 0.028349523125),
}


UNITE_VOLUME = {
    "ml": ("L", 0.001),
    "millilitre": ("L", 0.001),
    "millilitres": ("L", 0.001),
    "milliliter": ("L", 0.001),
    "milliliters": ("L", 0.001),

    "cl": ("L", 0.01),
    "centilitre": ("L", 0.01),
    "centilitres": ("L", 0.01),
    "centiliter": ("L", 0.01),
    "centiliters": ("L", 0.01),

    "l": ("L", 1.0),
    "litre": ("L", 1.0),
    "litres": ("L", 1.0),
    "liter": ("L", 1.0),
    "liters": ("L", 1.0),

    # US fluid ounce / gallon
    "floz": ("L", 0.0295735295625),
    "fl oz": ("L", 0.0295735295625),

    "fluidounce": ("L", 0.0295735295625),
    "fluidounces": ("L", 0.0295735295625),

    "gal": ("L", 3.785411784),
    "gallon": ("L", 3.785411784),
    "gallons": ("L", 3.785411784),
}


def normaliser_unite(
    quantite,
    unite,
):
    unite = normaliser_texte(unite)

    unite_sans_espace = unite.replace(
        " ",
        "",
    )

    if unite in UNITE_MASSE:
        unite_standard, facteur = UNITE_MASSE[unite]

        return (
            quantite * facteur,
            unite_standard,
        )

    if unite_sans_espace in UNITE_MASSE:
        unite_standard, facteur = UNITE_MASSE[
            unite_sans_espace
        ]

        return (
            quantite * facteur,
            unite_standard,
        )

    if unite in UNITE_VOLUME:
        unite_standard, facteur = UNITE_VOLUME[unite]

        return (
            quantite * facteur,
            unite_standard,
        )

    if unite_sans_espace in UNITE_VOLUME:
        unite_standard, facteur = UNITE_VOLUME[
            unite_sans_espace
        ]

        return (
            quantite * facteur,
            unite_standard,
        )

    return (
        quantite,
        "U",
    )


# ============================================================
# EXTRACTION CONDITIONNEMENT
# ============================================================

def extraire_conditionnement(
    libelle,
):
    """
    Extrait :

        500 g
        1 kg
        2 lb
        16 oz
        750 ml
        1 L

        12 x 355 ml
        12x355ml
        6 x 1 L
        4 x 2.5 kg

        6/750 ml
        12/1 L
        24/355 ml

        pack de 6
        pack of 6
        case of 24
        caisse de 24

        24 pcs
        24 units
        12 bottles
        24 cans
    """

    if libelle is None or pd.isna(libelle):
        return {
            "conditionnement_original": "",
            "quantite_totale": np.nan,
            "unite_standard": None,
            "conditionnement_detecte": False,
            "texte_conditionnement": "",
            "type_conditionnement": "inconnu",
        }

    original = str(libelle)

    s = normaliser_texte(
        original
    ).replace(
        ",",
        ".",
    )

    # --------------------------------------------------------
    # 1. MULTIPACK x
    # --------------------------------------------------------

    regex_pack = re.compile(
        r"""
        (?P<nb>\d+(?:\.\d+)?)
        \s*
        (?:x|\*)
        \s*
        (?P<qte>\d+(?:\.\d+)?)
        \s*
        (?P<unite>
            fl\s*oz|
            ml|cl|kg|lb|lbs|oz|g|l|gal
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_pack.search(s)

    if match:

        nb = float(
            match.group("nb")
        )

        qte = float(
            match.group("qte")
        )

        unite = match.group(
            "unite"
        ).lower()

        quantite_totale, unite_standard = normaliser_unite(
            nb * qte,
            unite,
        )

        return {
            "conditionnement_original": original,
            "quantite_totale": quantite_totale,
            "unite_standard": unite_standard,
            "conditionnement_detecte": True,
            "texte_conditionnement": match.group(0),
            "type_conditionnement": "multipack",
        }

    # --------------------------------------------------------
    # 2. FRACTION :
    # 6/750 ml
    # 12/1 L
    # --------------------------------------------------------

    regex_fraction = re.compile(
        r"""
        (?P<nb>\d+(?:\.\d+)?)
        \s*/\s*
        (?P<qte>\d+(?:\.\d+)?)
        \s*
        (?P<unite>
            fl\s*oz|
            ml|cl|kg|lb|lbs|oz|g|l|gal
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_fraction.search(s)

    if match:

        nb = float(
            match.group("nb")
        )

        qte = float(
            match.group("qte")
        )

        unite = match.group(
            "unite"
        ).lower()

        quantite_totale, unite_standard = normaliser_unite(
            nb * qte,
            unite,
        )

        return {
            "conditionnement_original": original,
            "quantite_totale": quantite_totale,
            "unite_standard": unite_standard,
            "conditionnement_detecte": True,
            "texte_conditionnement": match.group(0),
            "type_conditionnement": "multipack",
        }

    # --------------------------------------------------------
    # 3. SIMPLE
    # --------------------------------------------------------

    regex_simple = re.compile(
        r"""
        (?P<qte>\d+(?:\.\d+)?)
        \s*
        (?P<unite>
            fl\s*oz|
            ml|cl|kg|lb|lbs|oz|g|l|gal
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_simple.search(s)

    if match:

        qte = float(
            match.group("qte")
        )

        unite = match.group(
            "unite"
        ).lower()

        quantite_totale, unite_standard = normaliser_unite(
            qte,
            unite,
        )

        return {
            "conditionnement_original": original,
            "quantite_totale": quantite_totale,
            "unite_standard": unite_standard,
            "conditionnement_detecte": True,
            "texte_conditionnement": match.group(0),
            "type_conditionnement": "simple",
        }

    # --------------------------------------------------------
    # 4. COLIS
    # --------------------------------------------------------

    mots_colis = [
        "caisse",
        "caisses",
        "case",
        "cases",
        "carton",
        "cartons",
        "pack",
        "packs",
        "paquet",
        "paquets",
        "box",
        "boxes",
        "boite",
        "boites",
        "bte",
        "sac",
        "sacs",
    ]

    mots_colis_regex = "|".join(
        re.escape(mot)
        for mot in mots_colis
    )

    regex_colis = re.compile(
        rf"""
        (?P<contexte>
            {mots_colis_regex}
        )
        \s*
        (?:
            de|
            of|
            x
        )?
        \s*
        (?P<nb>\d+(?:\.\d+)?)
        \s*
        (?:
            unités?|
            units?|
            pcs?|
            pieces?|
            pièces?
        )?
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_colis.search(s)

    if match:

        nb = float(
            match.group("nb")
        )

        if nb > 0:

            return {
                "conditionnement_original": original,
                "quantite_totale": nb,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "colis",
            }

    # --------------------------------------------------------
    # 5. UNITES EXPLICITES
    # --------------------------------------------------------

    regex_unites = re.compile(
        r"""
        (?P<nb>\d+(?:\.\d+)?)
        \s*
        (?:
            u|
            unites?|
            units?|
            pcs?|
            pieces?|
            pièces?
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_unites.search(s)

    if match:

        nb = float(
            match.group("nb")
        )

        if nb > 0:

            return {
                "conditionnement_original": original,
                "quantite_totale": nb,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "unites",
            }

    # --------------------------------------------------------
    # 6. BOUTEILLES / CANETTES / SACS / BOX
    # --------------------------------------------------------

    mots_comptage = [
        "bouteille",
        "bouteilles",
        "bottle",
        "bottles",
        "btl",
        "canette",
        "canettes",
        "can",
        "cans",
        "boite",
        "boites",
        "box",
        "boxes",
        "sac",
        "sacs",
        "bag",
        "bags",
    ]

    mots_comptage_regex = "|".join(
        re.escape(mot)
        for mot in mots_comptage
    )

    regex_comptage = re.compile(
        rf"""
        (?P<nb>\d+(?:\.\d+)?)
        \s*
        (?P<unite>
            {mots_comptage_regex}
        )
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_comptage.search(s)

    if match:

        nb = float(
            match.group("nb")
        )

        if nb > 0:

            return {
                "conditionnement_original": original,
                "quantite_totale": nb,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "comptage",
            }

    # --------------------------------------------------------
    # 7. INCONNU
    # --------------------------------------------------------

    return {
        "conditionnement_original": original,
        "quantite_totale": np.nan,
        "unite_standard": None,
        "conditionnement_detecte": False,
        "texte_conditionnement": "",
        "type_conditionnement": "inconnu",
    }


# ============================================================
# PRODUIT DE BASE
# ============================================================

def extraire_produit_base(
    libelle,
):
    """
    Retire uniquement le conditionnement détecté.

    Exemple :
        Jus orange 12 x 1 L
        ->
        Jus orange
    """

    if libelle is None or pd.isna(libelle):
        return ""

    original = str(libelle)

    info = extraire_conditionnement(
        original
    )

    texte_conditionnement = info[
        "texte_conditionnement"
    ]

    if not texte_conditionnement:
        return normaliser_produit(
            original
        )

    base = original.replace(
        texte_conditionnement,
        " ",
        1,
    )

    base = re.sub(
        r"\s+",
        " ",
        base,
    ).strip()

    base = re.sub(
        r"[\-_/|]+$",
        "",
        base,
    ).strip()

    base = re.sub(
        r"^[\-_/|]+",
        "",
        base,
    ).strip()

    return normaliser_produit(
        base
    )


# ============================================================
# DETECTION DE LA BASE DU PRIX
# ============================================================

def detecter_base_prix_colonne(
    nom_colonne,
):
    """
    Détermine si la colonne de prix contient déjà
    un prix normalisé.

    Exemples :

        Prix
        Prix fournisseur
        Price
        -> PACKAGE

        Prix/kg
        Prix au kg
        €/kg
        $/kg
        -> KG

        Prix/L
        €/L
        $/L
        -> L

        Prix/unité
        Prix / U
        -> U

        Prix/lb
        $/lb
        -> LB
    """

    s = normaliser_texte(
        nom_colonne
    )

    # --------------------------------------------------------
    # Masse
    # --------------------------------------------------------

    if re.search(
        r"(?:/|par|au|a)\s*kg\b",
        s,
    ):
        return "KG"

    if re.search(
        r"(?:/|par|au|a)\s*(?:lb|lbs|pound|pounds)\b",
        s,
    ):
        return "LB"

    if re.search(
        r"(?:/|par|au|a)\s*(?:oz|ounce|ounces)\b",
        s,
    ):
        return "OZ"

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    if re.search(
        r"(?:/|par|au|a)\s*(?:l|litre|litres|liter|liters)\b",
        s,
    ):
        return "L"

    if re.search(
        r"(?:/|par|au|a)\s*(?:ml)\b",
        s,
    ):
        return "ML"

    if re.search(
        r"(?:/|par|au|a)\s*(?:gal|gallon|gallons)\b",
        s,
    ):
        return "GAL"

    # --------------------------------------------------------
    # Unité
    # --------------------------------------------------------

    if re.search(
        r"(?:/|par|a|au)\s*(?:u|unite|unites|unit|units|piece|pieces|pc|pcs)\b",
        s,
    ):
        return "U"

    return "PACKAGE"


def detecter_base_prix_valeur(
    valeur,
):
    """
    Détection de secours à partir de la valeur elle-même.

    Exemples :
        12,50 €/kg
        $4.20/lb
        CA$ 3.50 / L

    Retourne :
        (nombre, unité)

    ou :
        (valeur, PACKAGE)
    """

    if pd.isna(valeur):
        return (
            np.nan,
            "PACKAGE",
        )

    original = str(valeur)

    s = normaliser_texte(
        original
    )

    # --------------------------------------------------------
    # Recherche unité
    # --------------------------------------------------------

    unite = None

    if re.search(
        r"(?:/|par|au|a)\s*kg\b",
        s,
    ):
        unite = "KG"

    elif re.search(
        r"(?:/|par|au|a)\s*(?:lb|lbs|pound|pounds)\b",
        s,
    ):
        unite = "LB"

    elif re.search(
        r"(?:/|par|au|a)\s*(?:oz|ounce|ounces)\b",
        s,
    ):
        unite = "OZ"

    elif re.search(
        r"(?:/|par|au|a)\s*(?:l|litre|litres|liter|liters)\b",
        s,
    ):
        unite = "L"

    elif re.search(
        r"(?:/|par|au|a)\s*ml\b",
        s,
    ):
        unite = "ML"

    elif re.search(
        r"(?:/|par|au|a)\s*(?:gal|gallon|gallons)\b",
        s,
    ):
        unite = "GAL"

    elif re.search(
        r"(?:/|par|a|au)\s*(?:u|unite|unites|unit|units|piece|pieces|pc|pcs)\b",
        s,
    ):
        unite = "U"

    if unite is None:
        return (
            convertir_prix_international(
                valeur
            ),
            "PACKAGE",
        )

    # --------------------------------------------------------
    # Extraire la partie numérique
    # --------------------------------------------------------

    match = re.search(
        r"-?\d+(?:[\.,]\d+)?",
        s,
    )

    if not match:
        return (
            np.nan,
            unite,
        )

    nombre = convertir_prix_international(
        match.group(0),
        pays="CA",
    )

    return (
        nombre,
        unite,
    )


# ============================================================
# CONVERSION PRIX DIRECT
# ============================================================

def convertir_prix_direct(
    prix,
    unite_source,
):
    """
    Convertit un prix déjà normalisé :

        $/kg -> $/kg
        $/lb -> $/kg
        $/oz -> $/kg

        $/L -> $/L
        $/ml -> $/L
        $/gal -> $/L

        $/U -> $/U
    """

    if pd.isna(prix):
        return (
            np.nan,
            None,
        )

    if unite_source == "PACKAGE":
        return (
            prix,
            "PACKAGE",
        )

    if unite_source == "KG":
        return (
            prix,
            "KG",
        )

    if unite_source == "LB":
        # 1 lb = 0.45359237 kg
        return (
            prix / 0.45359237,
            "KG",
        )

    if unite_source == "OZ":
        # 1 oz = 0.028349523125 kg
        return (
            prix / 0.028349523125,
            "KG",
        )

    if unite_source == "L":
        return (
            prix,
            "L",
        )

    if unite_source == "ML":
        return (
            prix * 1000,
            "L",
        )

    if unite_source == "GAL":
        return (
            prix / 3.785411784,
            "L",
        )

    if unite_source == "U":
        return (
            prix,
            "U",
        )

    return (
        prix,
        None,
    )


# ============================================================
# FORMATAGE CONDITIONNEMENT
# ============================================================

def formater_conditionnement(
    quantite,
    unite,
):
    if pd.isna(quantite) or not unite:
        return "Non détecté"

    if unite == "KG":

        if quantite >= 1:
            return f"{quantite:g} kg"

        return f"{quantite * 1000:g} g"

    if unite == "L":

        if quantite >= 1:
            return f"{quantite:g} L"

        return f"{quantite * 1000:g} ml"

    if unite == "U":
        return f"{quantite:g} U"

    return f"{quantite:g} {unite}"


# ============================================================
# PRIX COMPARABLE
# ============================================================

def calculer_prix_comparable(
    prix,
    quantite,
    unite,
):
    if pd.isna(prix):
        return np.nan

    if pd.isna(quantite):
        return np.nan

    if not unite:
        return np.nan

    if quantite <= 0:
        return np.nan

    return prix / quantite


def format_prix_comparable(
    prix,
    unite,
    symbole,
):
    if pd.isna(prix) or not unite:
        return "Non calculable"

    if unite == "KG":
        return f"{prix:.2f} {symbole}/kg"

    if unite == "L":
        return f"{prix:.2f} {symbole}/L"

    if unite == "U":
        return f"{prix:.2f} {symbole}/U"

    return f"{prix:.2f} {symbole}"


# ============================================================
# DETECTION COLONNES
# ============================================================

def score_colonne_produit(
    nom_colonne,
    config,
):
    nom = normaliser_texte(
        nom_colonne
    )

    score = 0

    for mot in config["mots_produit"]:

        mot = normaliser_texte(
            mot
        )

        if nom == mot:
            score += 100

        elif mot in nom:
            score += 50

    return score


def score_colonne_prix(
    nom_colonne,
    config,
):
    nom = normaliser_texte(
        nom_colonne
    )

    score = 0

    for mot in config["mots_prix"]:

        mot = normaliser_texte(
            mot
        )

        if nom == mot:
            score += 100

        elif mot in nom:
            score += 50

    if any(
        x in nom
        for x in [
            "€",
            "$",
            "eur",
            "cad",
            "price",
            "prix",
        ]
    ):
        score += 15

    return score


def detecter_colonnes(
    df,
    config,
):
    colonnes = list(
        df.columns
    )

    if not colonnes:
        return (
            None,
            None,
        )

    scores_produit = {
        col: score_colonne_produit(
            col,
            config,
        )
        for col in colonnes
    }

    scores_prix = {
        col: score_colonne_prix(
            col,
            config,
        )
        for col in colonnes
    }

    colonne_produit = max(
        scores_produit,
        key=scores_produit.get,
    )

    colonne_prix = max(
        scores_prix,
        key=scores_prix.get,
    )

    if scores_produit[
        colonne_produit
    ] == 0:
        colonne_produit = colonnes[0]

    if scores_prix[
        colonne_prix
    ] == 0:

        colonnes_numeriques = []

        for col in colonnes:

            valeurs = pd.to_numeric(
                df[col],
                errors="coerce",
            )

            if valeurs.notna().sum() > 0:
                colonnes_numeriques.append(
                    col
                )

        if colonnes_numeriques:

            colonne_prix = max(
                colonnes_numeriques,
                key=lambda c:
                pd.to_numeric(
                    df[c],
                    errors="coerce",
                ).notna().sum(),
            )

        else:
            colonne_prix = colonnes[-1]

    if (
        colonne_produit
        == colonne_prix
    ):

        alternatives = [
            col
            for col in colonnes
            if (
                col != colonne_produit
                and scores_prix[col] > 0
            )
        ]

        if alternatives:

            colonne_prix = max(
                alternatives,
                key=scores_prix.get,
            )

    return (
        colonne_produit,
        colonne_prix,
    )


# ============================================================
# LECTURE EXCEL
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_excel(
    contenu_bytes,
):
    dfs = {}

    with pd.ExcelFile(
        io.BytesIO(
            contenu_bytes
        )
    ) as excel:

        for feuille in excel.sheet_names:

            try:

                df = excel.parse(
                    feuille
                )

                if (
                    df is not None
                    and not df.empty
                ):
                    dfs[feuille] = df

            except Exception:
                continue

    return dfs


# ============================================================
# LECTURE CSV
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_csv(
    contenu_bytes,
):
    tentatives = [
        ("utf-8", ";"),
        ("utf-8", ","),
        ("utf-8-sig", ";"),
        ("utf-8-sig", ","),
        ("cp1252", ";"),
        ("cp1252", ","),
        ("latin1", ";"),
        ("latin1", ","),
    ]

    for encodage, separateur in tentatives:

        try:

            df = pd.read_csv(
                io.BytesIO(
                    contenu_bytes
                ),
                encoding=encodage,
                sep=separateur,
            )

            if df.shape[1] >= 2:
                return {
                    "CSV": df
                }

        except Exception:
            continue

    for encodage in [
        "utf-8",
        "utf-8-sig",
        "cp1252",
        "latin1",
    ]:

        try:

            df = pd.read_csv(
                io.BytesIO(
                    contenu_bytes
                ),
                encoding=encodage,
                sep=None,
                engine="python",
            )

            if df.shape[1] >= 1:
                return {
                    "CSV": df
                }

        except Exception:
            continue

    return {}


# ============================================================
# PDF
# ============================================================

def nettoyer_table_pdf(
    table,
):
    if not table:
        return None

    lignes = []

    for ligne in table:

        if not ligne:
            continue

        ligne_nettoyee = [
            ""
            if valeur is None
            else str(valeur).strip()
            for valeur in ligne
        ]

        if any(
            ligne_nettoyee
        ):
            lignes.append(
                ligne_nettoyee
            )

    if len(lignes) < 2:
        return None

    premiere_ligne = lignes[0]

    colonnes = []

    for i, valeur in enumerate(
        premiere_ligne
    ):

        nom = (
            valeur
            if valeur
            else f"Colonne_{i + 1}"
        )

        colonnes.append(
            nom
        )

    donnees = lignes[1:]

    largeur = len(
        colonnes
    )

    donnees_corrigees = []

    for ligne in donnees:

        if len(ligne) < largeur:

            ligne = (
                ligne
                + [""] * (
                    largeur
                    - len(ligne)
                )
            )

        elif len(ligne) > largeur:

            ligne = ligne[
                :largeur
            ]

        donnees_corrigees.append(
            ligne
        )

    return pd.DataFrame(
        donnees_corrigees,
        columns=colonnes,
    )


@st.cache_data(
    show_spinner=False
)
def lire_pdf(
    contenu_bytes,
):
    dfs = {}

    try:

        with pdfplumber.open(
            io.BytesIO(
                contenu_bytes
            )
        ) as pdf:

            compteur = 1

            for page in pdf.pages:

                try:

                    tables = page.extract_tables()

                    for table in tables:

                        df = nettoyer_table_pdf(
                            table
                        )

                        if (
                            df is not None
                            and not df.empty
                        ):

                            dfs[
                                f"Page {page.page_number} - Tableau {compteur}"
                            ] = df

                            compteur += 1

                except Exception:
                    continue

    except Exception:
        return {}

    return dfs


# ============================================================
# LECTURE FICHIER
# ============================================================

def lire_fichier_fournisseur(
    fichier,
):
    extension = (
        fichier.name
        .lower()
        .split(".")[-1]
    )

    contenu_bytes = fichier.getvalue()

    if extension in [
        "xlsx",
        "xls",
    ]:
        return lire_excel(
            contenu_bytes
        )

    if extension == "csv":
        return lire_csv(
            contenu_bytes
        )

    if extension == "pdf":
        return lire_pdf(
            contenu_bytes
        )

    return {}


# ============================================================
# PREPARATION DONNEES
# ============================================================

def preparer_donnees(
    df,
    colonne_produit,
    colonne_prix,
    fournisseur,
    pays,
):
    travail = df.copy()

    # --------------------------------------------------------
    # Produit original
    # --------------------------------------------------------

    travail[
        "Produit_Affichage"
    ] = (
        travail[
            colonne_produit
        ]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Détection base prix selon colonne
    # --------------------------------------------------------

    base_prix_colonne = detecter_base_prix_colonne(
        colonne_prix
    )

    travail[
        "Base_Prix_Colonne"
    ] = base_prix_colonne

    # --------------------------------------------------------
    # Prix
    # --------------------------------------------------------

    prix_bruts = []
    bases_prix = []

    for valeur in travail[
        colonne_prix
    ]:

        # Si la colonne indique déjà une unité,
        # on la respecte.
        if (
            base_prix_colonne
            != "PACKAGE"
        ):

            prix = convertir_prix_international(
                valeur,
                pays=pays,
            )

            base = base_prix_colonne

        else:

            prix, base_detectee = detecter_base_prix_valeur(
                valeur
            )

            base = base_detectee

        prix_bruts.append(
            prix
        )

        bases_prix.append(
            base
        )

    travail[
        "Prix_Unitaire"
    ] = prix_bruts

    travail[
        "Base_Prix"
    ] = bases_prix

    # --------------------------------------------------------
    # Conditionnement
    # --------------------------------------------------------

    infos_conditionnement = travail[
        "Produit_Affichage"
    ].apply(
        extraire_conditionnement
    )

    travail[
        "Conditionnement"
    ] = infos_conditionnement.apply(
        lambda x:
        x[
            "conditionnement_original"
        ]
    )

    travail[
        "Quantite_Normalisee"
    ] = infos_conditionnement.apply(
        lambda x:
        x[
            "quantite_totale"
        ]
    )

    travail[
        "Unite_Etalon"
    ] = infos_conditionnement.apply(
        lambda x:
        x[
            "unite_standard"
        ]
    )

    travail[
        "Conditionnement_Detecte"
    ] = infos_conditionnement.apply(
        lambda x:
        x[
            "conditionnement_detecte"
        ]
    )

    travail[
        "Type_Conditionnement"
    ] = infos_conditionnement.apply(
        lambda x:
        x[
            "type_conditionnement"
        ]
    )

    # --------------------------------------------------------
    # Produit de base
    # --------------------------------------------------------

    travail[
        "Produit_Base"
    ] = travail[
        "Produit_Affichage"
    ].apply(
        extraire_produit_base
    )

    # --------------------------------------------------------
    # Prix comparable
    # --------------------------------------------------------

    prix_comparables = []
    unites_comparables = []

    for _, ligne in travail.iterrows():

        prix = ligne[
            "Prix_Unitaire"
        ]

        base_prix = ligne[
            "Base_Prix"
        ]

        quantite = ligne[
            "Quantite_Normalisee"
        ]

        unite_conditionnement = ligne[
            "Unite_Etalon"
        ]

        # ----------------------------------------------------
        # CAS 1 :
        # Prix déjà au kg/L/U
        # ----------------------------------------------------

        if base_prix != "PACKAGE":

            prix_converti, unite = convertir_prix_direct(
                prix,
                base_prix,
            )

            prix_comparables.append(
                prix_converti
            )

            unites_comparables.append(
                unite
            )

            continue

        # ----------------------------------------------------
        # CAS 2 :
        # Prix du colis
        # ----------------------------------------------------

        if (
            pd.notna(quantite)
            and unite_conditionnement
        ):

            prix_comparable = calculer_prix_comparable(
                prix,
                quantite,
                unite_conditionnement,
            )

            prix_comparables.append(
                prix_comparable
            )

            unites_comparables.append(
                unite_conditionnement
            )

        else:

            prix_comparables.append(
                np.nan
            )

            unites_comparables.append(
                None
            )

    travail[
        "Prix_Comparable"
    ] = prix_comparables

    travail[
        "Unite_Comparaison"
    ] = unites_comparables

    travail[
        "Fournisseur"
    ] = fournisseur

    # --------------------------------------------------------
    # Nettoyage
    # --------------------------------------------------------

    travail = travail[
        trabalho_colonnes := [
            "Produit_Affichage",
            "Produit_Base",
            "Prix_Unitaire",
            "Base_Prix",
            "Conditionnement",
            "Quantite_Normalisee",
            "Unite_Etalon",
            "Conditionnement_Detecte",
            "Type_Conditionnement",
            "Prix_Comparable",
            "Unite_Comparaison",
            "Fournisseur",
        ]
    ].copy()

    travail = travail[
        travail[
            "Produit_Base"
        ].notna()
        & (
            travail[
                "Produit_Base"
            ].astype(str).str.strip()
            != ""
        )
    ]

    travail = travail[
        travail[
            "Prix_Unitaire"
        ].notna()
        & (
            travail[
                "Prix_Unitaire"
            ] >= 0
        )
    ]

    travail = travail.drop_duplicates(
        subset=[
            "Produit_Base",
            "Prix_Unitaire",
            "Conditionnement",
            "Fournisseur",
        ]
    )

    return travail


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "⚙️ Configuration"
    )

    region = st.selectbox(
        "Région",
        [
            "🇫🇷 France",
            "🇨🇦 Canada",
        ],
    )

    config = configuration_region(
        region
    )

    st.info(
        f"Devise : **{config['devise']} "
        f"({config['symbole']})**"
    )

    st.markdown("---")

    st.markdown(
        """
        **Comparaison intelligente**

        Les prix peuvent être comparés :
        - au kg
        - au L
        - à l'unité

        Le moteur reconnaît aussi les différences
        légères entre les noms fournisseurs.
        """
    )


# ============================================================
# IMPORT
# ============================================================

st.subheader(
    "📥 Importer les tarifs fournisseurs"
)

fichiers = st.file_uploader(
    "Dépose tes fichiers ici",
    type=[
        "xlsx",
        "xls",
        "csv",
        "pdf",
    ],
    accept_multiple_files=True,
    help="Excel, CSV et PDF sont acceptés.",
)


if not fichiers:

    st.info(
        "👆 Importe les tarifs de tes fournisseurs "
        "pour commencer."
    )

    st.markdown(
        """
        ### Exemples

        **Produits**

        `Jus d'orange 12 x 1 L`  
        `Jus Orange 6 x 1L`  
        `Jus orange 5 L`

        seront rapprochés comme un même produit.

        **Prix**

        `18,00 €`  
        `18 €/kg`  
        `4,50 €/L`  
        `$2.99/lb`

        sont également pris en charge.
        """
    )

    st.stop()


# ============================================================
# TRAITEMENT FOURNISSEURS
# ============================================================

donnees_fournisseurs = {}
diagnostics_globaux = []

for fichier in fichiers:

    nom_fournisseur = fichier.name.rsplit(
        ".",
        1,
    )[0]

    with st.container(
        border=True
    ):

        st.markdown(
            f"### 🏪 {nom_fournisseur}"
        )

        try:

            feuilles = lire_fichier_fournisseur(
                fichier
            )

        except Exception as e:

            st.error(
                f"Impossible de lire "
                f"**{fichier.name}** : {e}"
            )

            continue

        if not feuilles:

            st.error(
                "Aucune donnée exploitable "
                "n'a été trouvée."
            )

            continue

        noms_feuilles = list(
            feuilles.keys()
        )

        if len(noms_feuilles) > 1:

            feuille_selectionnee = st.selectbox(
                "Feuille / tableau",
                noms_feuilles,
                key=f"feuille_{fichier.name}",
            )

        else:

            feuille_selectionnee = (
                noms_feuilles[0]
            )

        df_brut = feuilles[
            feuille_selectionnee
        ].copy()

        if df_brut.empty:

            st.warning(
                "Le tableau est vide."
            )

            continue

        (
            colonne_produit_auto,
            colonne_prix_auto,
        ) = detecter_colonnes(
            df_brut,
            config,
        )

        st.markdown(
            '<div class="small-muted">'
            "Colonnes détectées automatiquement"
            "</div>",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)

        with col1:

            colonne_produit = st.selectbox(
                "Colonne produit",
                list(
                    df_brut.columns
                ),
                index=list(
                    df_brut.columns
                ).index(
                    colonne_produit_auto
                ),
                key=f"produit_{fichier.name}",
            )

        with col2:

            colonne_prix = st.selectbox(
                "Colonne prix",
                list(
                    df_brut.columns
                ),
                index=list(
                    df_brut.columns
                ).index(
                    colonne_prix_auto
                ),
                key=f"prix_{fichier.name}",
            )

        base_prix_detectee = detecter_base_prix_colonne(
            colonne_prix
        )

        if base_prix_detectee != "PACKAGE":

            st.info(
                "💡 Cette colonne semble déjà "
                f"être exprimée en **{base_prix_detectee}**. "
                "Le prix ne sera donc pas divisé une deuxième fois."
            )

        with st.expander(
            "🔎 Aperçu et diagnostic",
            expanded=False,
        ):

            st.dataframe(
                df_brut.head(10),
                width="stretch",
                hide_index=True,
            )

            st.caption(
                f"{len(df_brut):,} lignes détectées."
            )

        df_propre = preparer_donnees(
            df_brut,
            colonne_produit,
            colonne_prix,
            nom_fournisseur,
            config["pays"],
        )

        if df_propre.empty:

            st.error(
                "Aucune ligne valide après nettoyage."
            )

            continue

        nombre_lignes = len(
            df_propre
        )

        nombre_conditionnements = int(
            df_propre[
                "Conditionnement_Detecte"
            ].sum()
        )

        nombre_non_detectes = (
            nombre_lignes
            - nombre_conditionnements
        )

        nombre_prix_directs = int(
            (
                df_propre[
                    "Base_Prix"
                ] != "PACKAGE"
            ).sum()
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Lignes valides",
            f"{nombre_lignes:,}",
        )

        c2.metric(
            "Conditionnements",
            f"{nombre_conditionnements:,}",
        )

        c3.metric(
            "Prix normalisés",
            f"{nombre_prix_directs:,}",
        )

        if nombre_non_detectes > 0:

            st.warning(
                f"⚠️ {nombre_non_detectes} ligne(s) "
                "n'ont pas de conditionnement détecté "
                "et ne pourront pas être comparées "
                "comme prix de colis."
            )

        donnees_fournisseurs[
            fichier.name
        ] = df_propre

        diagnostics_globaux.append(
            {
                "Fournisseur": nom_fournisseur,
                "Lignes valides": nombre_lignes,
                "Conditionnements détectés": nombre_conditionnements,
                "Conditionnements manquants": nombre_non_detectes,
                "Prix déjà normalisés": nombre_prix_directs,
            }
        )


# ============================================================
# VERIFICATION
# ============================================================

if not donnees_fournisseurs:

    st.error(
        "Aucun fournisseur n'a pu être chargé."
    )

    st.stop()


# ============================================================
# FUSION
# ============================================================

df_total = pd.concat(
    donnees_fournisseurs.values(),
    ignore_index=True,
)


# ============================================================
# CONSTRUCTION DES GROUPES PRODUITS
# ============================================================

st.markdown("---")

st.subheader(
    "🧠 Correspondance intelligente des produits"
)

groupes_produits = []

mapping_produits = {}

compteur_groupe = 0

for index, ligne in df_total.iterrows():

    produit = ligne[
        "Produit_Base"
    ]

    unite = ligne[
        "Unite_Comparaison"
    ]

    # --------------------------------------------------------
    # Si le prix est non comparable :
    # pas de fuzzy matching exploitable
    # --------------------------------------------------------

    if not unite or pd.isna(
        ligne["Prix_Comparable"]
    ):

        mapping_produits[
            index
        ] = {
            "groupe_id": None,
            "score": 0.0,
            "type": "non comparable",
        }

        continue

    groupe_id, score, type_match = trouver_groupe_produit(
        produit,
        unite,
        groupes_produits,
    )

    if groupe_id is None:

        groupe_id = compteur_groupe

        compteur_groupe += 1

        groupes_produits.append(
            {
                "id": groupe_id,
                "cle": cle_produit_fuzzy(
                    produit
                ),
                "nom": produit,
                "unite_etalon": unite,
            }
        )

        type_match = "nouveau"

    mapping_produits[
        index
    ] = {
        "groupe_id": groupe_id,
        "score": score,
        "type": type_match,
    }


# ------------------------------------------------------------
# Ajout des informations de matching
# ------------------------------------------------------------

df_total[
    "Groupe_Produit"
] = df_total.index.map(
    lambda i:
    mapping_produits[i][
        "groupe_id"
    ]
)

df_total[
    "Score_Matching"
] = df_total.index.map(
    lambda i:
    mapping_produits[i][
        "score"
    ]
)

df_total[
    "Type_Matching"
] = df_total.index.map(
    lambda i:
    mapping_produits[i][
        "type"
    ]
)


# ============================================================
# STATISTIQUES MATCHING
# ============================================================

nombre_exactes = int(
    (
        df_total[
            "Type_Matching"
        ] == "exacte"
    ).sum()
)

nombre_fortes = int(
    (
        df_total[
            "Type_Matching"
        ] == "forte"
    ).sum()
)

nombre_probables = int(
    (
        df_total[
            "Type_Matching"
        ] == "probable"
    ).sum()
)

nombre_nouveaux = int(
    (
        df_total[
            "Type_Matching"
        ] == "nouveau"
    ).sum()
)


m1, m2, m3 = st.columns(3)

m1.metric(
    "Correspondances fortes",
    nombre_fortes,
)

m2.metric(
    "Correspondances probables",
    nombre_probables,
)

m3.metric(
    "Nouveaux produits",
    nombre_nouveaux,
)


# ============================================================
# CORRESPONDANCES PROBABLES
# ============================================================

correspondances_probables = df_total[
    df_total[
        "Type_Matching"
    ] == "probable"
].copy()


if not correspondances_probables.empty:

    with st.expander(
        "⚠️ Correspondances probables à vérifier",
        expanded=False,
    ):

        affichage_matching = (
            correspondances_probables[
                [
                    "Produit_Affichage",
                    "Produit_Base",
                    "Fournisseur",
                    "Score_Matching",
                ]
            ]
            .drop_duplicates()
            .sort_values(
                "Score_Matching",
                ascending=True,
            )
        )

        affichage_matching[
            "Score"
        ] = (
            affichage_matching[
                "Score_Matching"
            ] * 100
        ).round(1).astype(str) + "%"

        st.dataframe(
            affichage_matching[
                [
                    "Produit_Affichage",
                    "Produit_Base",
                    "Fournisseur",
                    "Score",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        st.caption(
            "Ces correspondances sont suffisamment proches "
            "pour être proposées automatiquement, mais méritent "
            "une vérification humaine si les produits sont critiques."
        )


# ============================================================
# COMPARAISON DES PRIX
# ============================================================

st.markdown("---")

st.subheader(
    "🏆 Meilleurs prix comparables"
)


df_comparable = df_total[
    df_total[
        "Groupe_Produit"
    ].notna()
    & df_total[
        "Prix_Comparable"
    ].notna()
    & df_total[
        "Unite_Comparaison"
    ].notna()
    & (
        df_total[
            "Prix_Comparable"
        ] >= 0
    )
].copy()


if df_comparable.empty:

    st.error(
        "Aucun prix comparable n'a pu être calculé."
    )

    st.stop()


# ============================================================
# MINIMUM PAR GROUPE + UNITE
# ============================================================

prix_minimum = (
    df_comparable
    .groupby(
        [
            "Groupe_Produit",
            "Unite_Comparaison",
        ]
    )[
        "Prix_Comparable"
    ]
    .transform("min")
)


resultat = df_comparable[
    df_comparable[
        "Prix_Comparable"
    ] == prix_minimum
].copy()


# ============================================================
# EX AEQUO
# ============================================================

nombre_produits = resultat[
    "Groupe_Produit"
].nunique()

nombre_fournisseurs = df_total[
    "Fournisseur"
].nunique()

nombre_offres = len(
    df_total
)

ex_aequo_par_produit = (
    resultat
    .groupby(
        [
            "Groupe_Produit",
            "Unite_Comparaison",
        ]
    )[
        "Fournisseur"
    ]
    .nunique()
)

nombre_ex_aequo = int(
    (
        ex_aequo_par_produit
        > 1
    ).sum()
)


# ============================================================
# KPI
# ============================================================

col1, col2, col3 = st.columns(3)

col1.metric(
    "Produits comparés",
    nombre_produits,
)

col2.metric(
    "Fournisseurs",
    nombre_fournisseurs,
)

col3.metric(
    "Offres analysées",
    nombre_offres,
)


if nombre_ex_aequo > 0:

    st.info(
        f"🤝 {nombre_ex_aequo} produit(s) présentent "
        "un prix comparable minimum ex æquo."
    )


# ============================================================
# NOM AFFICHAGE DU PRODUIT
# ============================================================

noms_groupes = (
    df_total
    .dropna(
        subset=[
            "Groupe_Produit"
        ]
    )
    .groupby(
        "Groupe_Produit"
    )[
        "Produit_Affichage"
    ]
    .first()
    .to_dict()
)


resultat[
    "Produit"
] = resultat[
    "Groupe_Produit"
].map(
    noms_groupes
)


# ============================================================
# AFFICHAGE
# ============================================================

resultat[
    "Prix affiché"
] = resultat.apply(
    lambda ligne:
    (
        f"{ligne['Prix_Unitaire']:.2f} "
        f"{config['symbole']}"
    ),
    axis=1,
)


resultat[
    "Conditionnement affiché"
] = resultat.apply(
    lambda ligne:
    (
        "Prix direct"
        if ligne[
            "Base_Prix"
        ] != "PACKAGE"
        else formater_conditionnement(
            ligne[
                "Quantite_Normalisee"
            ],
            ligne[
                "Unite_Etalon"
            ],
        )
    ),
    axis=1,
)


resultat[
    "Prix comparable affiché"
] = resultat.apply(
    lambda ligne:
    format_prix_comparable(
        ligne[
            "Prix_Comparable"
        ],
        ligne[
            "Unite_Comparaison"
        ],
        config[
            "symbole"
        ],
    ),
    axis=1,
)


resultat[
    "Correspondance"
] = resultat[
    "Type_Matching"
].map(
    {
        "exacte": "✓ Exacte",
        "forte": "✓ Forte",
        "probable": "⚠ Probable",
        "nouveau": "• Nouveau",
    }
)


resultat = resultat.sort_values(
    by=[
        "Produit",
        "Prix_Comparable",
        "Fournisseur",
    ],
    ascending=[
        True,
        True,
        True,
    ],
)


colonnes_affichage = [
    "Produit",
    "Fournisseur",
    "Prix affiché",
    "Conditionnement affiché",
    "Prix comparable affiché",
    "Correspondance",
]


st.dataframe(
    resultat[
        colonnes_affichage
    ],
    width="stretch",
    hide_index=True,
    column_config={
        "Produit": st.column_config.TextColumn(
            "Produit",
            width="large",
        ),
        "Fournisseur": st.column_config.TextColumn(
            "Fournisseur",
            width="medium",
        ),
        "Prix affiché": st.column_config.TextColumn(
            "Prix fournisseur",
            width="small",
        ),
        "Conditionnement affiché": st.column_config.TextColumn(
            "Conditionnement",
            width="medium",
        ),
        "Prix comparable affiché": st.column_config.TextColumn(
            "Meilleur prix comparable",
            width="medium",
        ),
        "Correspondance": st.column_config.TextColumn(
            "Matching produit",
            width="small",
        ),
    },
)


# ============================================================
# DETAILS TECHNIQUES
# ============================================================

with st.expander(
    "🧮 Voir les détails des calculs",
    expanded=False,
):

    details = resultat[
        [
            "Produit_Affichage",
            "Produit",
            "Produit_Base",
            "Fournisseur",
            "Prix_Unitaire",
            "Base_Prix",
            "Conditionnement",
            "Quantite_Normalisee",
            "Unite_Etalon",
            "Prix_Comparable",
            "Unite_Comparaison",
            "Type_Matching",
            "Score_Matching",
        ]
    ].copy()

    details[
        "Prix_Unitaire"
    ] = details[
        "Prix_Unitaire"
    ].round(4)

    details[
        "Quantite_Normalisee"
    ] = details[
        "Quantite_Normalisee"
    ].round(6)

    details[
        "Prix_Comparable"
    ] = details[
        "Prix_Comparable"
    ].round(4)

    details[
        "Score_Matching"
    ] = (
        details[
            "Score_Matching"
        ] * 100
    ).round(1)

    st.dataframe(
        details,
        width="stretch",
        hide_index=True,
    )


# ============================================================
# DIAGNOSTICS GLOBAUX
# ============================================================

if diagnostics_globaux:

    with st.expander(
        "🔧 Diagnostics fournisseurs",
        expanded=False,
    ):

        df_diagnostics = pd.DataFrame(
            diagnostics_globaux
        )

        st.dataframe(
            df_diagnostics,
            width="stretch",
            hide_index=True,
        )


# ============================================================
# EXPORT CSV
# ============================================================

st.markdown("---")

export = resultat[
    [
        "Produit",
        "Fournisseur",
        "Prix_Unitaire",
        "Base_Prix",
        "Conditionnement",
        "Quantite_Normalisee",
        "Unite_Comparaison",
        "Prix_Comparable",
        "Type_Matching",
        "Score_Matching",
    ]
].copy()


export = export.rename(
    columns={
        "Prix_Unitaire":
            f"Prix fournisseur ({config['devise']})",

        "Base_Prix":
            "Base prix",

        "Quantite_Normalisee":
            "Quantite normalisee",

        "Unite_Comparaison":
            "Unite comparaison",

        "Prix_Comparable":
            f"Prix comparable ({config['devise']})",

        "Type_Matching":
            "Type matching",

        "Score_Matching":
            "Score matching",
    }
)


export[
    "Score matching"
] = (
    export[
        "Score matching"
    ] * 100
).round(1)


csv_export = export.to_csv(
    index=False,
    sep=";",
    decimal=",",
    encoding="utf-8-sig",
)


st.download_button(
    label="📥 Télécharger les meilleurs prix en CSV",
    data=csv_export,
    file_name="optimarge_meilleurs_prix.csv",
    mime="text/csv",
)


# ============================================================
# MESSAGE FINAL
# ============================================================

st.success(
    f"✅ Comparaison terminée : "
    f"{nombre_produits} produit(s), "
    f"{nombre_fournisseurs} fournisseur(s), "
    f"{nombre_offres} offre(s) analysée(s)."
)