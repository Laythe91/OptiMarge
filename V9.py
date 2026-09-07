import streamlit as st
import pandas as pd
import numpy as np
import re
import unicodedata
import io
from difflib import SequenceMatcher


# ============================================================
# LIBRAIRIES OPTIONNELLES
# ============================================================

try:
    import pdfplumber
    PDFPLUMBER_DISPONIBLE = True
except ImportError:
    pdfplumber = None
    PDFPLUMBER_DISPONIBLE = False


try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_DISPONIBLE = True
except ImportError:
    RAPIDFUZZ_DISPONIBLE = False


# ============================================================
# CONFIGURATION STREAMLIT
# ============================================================

st.set_page_config(
    page_title="OptiMarge Food",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)


VERSION_APP = "V10.2 — moteur générique robuste"

SEUIL_MATCHING_FORT = 0.92
SEUIL_MATCHING_PROBABLE = 0.86


# ============================================================
# CSS — HEADER CORRIGÉ
# ============================================================

st.markdown(
    """
    <style>

    /* -------------------------------------------------------
       CONTENEUR PRINCIPAL
       ------------------------------------------------------- */

    .block-container {
        padding-top: 2.8rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        overflow: visible !important;
    }


    /* -------------------------------------------------------
       HEADER OPTIMARGE
       ------------------------------------------------------- */

    .optimarge-header {
        width: 100%;
        box-sizing: border-box;
        margin: 0 0 1.5rem 0;
        padding: 0.4rem 0.2rem 0.8rem 0.2rem;
        overflow: visible !important;
        position: relative;
    }

    .optimarge-title {
        display: block;
        width: 100%;
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        font-size: clamp(2rem, 5vw, 3.4rem);
        line-height: 1.15;
        font-weight: 800;
        letter-spacing: -0.04em;
        white-space: normal;
        overflow: visible !important;
        text-overflow: clip;
        word-break: normal;
    }

    .optimarge-subtitle {
        display: block;
        width: 100%;
        margin-top: 0.55rem;
        font-size: clamp(0.9rem, 1.7vw, 1.08rem);
        line-height: 1.5;
        white-space: normal;
        overflow: visible !important;
    }


    /* -------------------------------------------------------
       CARTES
       ------------------------------------------------------- */

    .provider-card {
        width: 100%;
        box-sizing: border-box;
        padding: 0.9rem;
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        margin-bottom: 0.6rem;
        overflow: visible;
    }

    .small-muted {
        color: #777;
        font-size: 0.85rem;
    }


    /* -------------------------------------------------------
       BOUTONS
       ------------------------------------------------------- */

    div.stButton > button,
    div.stDownloadButton > button {
        width: 100%;
        min-height: 3rem;
    }


    /* -------------------------------------------------------
       KPI
       ------------------------------------------------------- */

    [data-testid="stMetricValue"] {
        font-size: 1.7rem;
    }


    /* -------------------------------------------------------
       MOBILE
       ------------------------------------------------------- */

   @media (max-width: 700px) {

        /* Augmenter le padding-top pour dégager la barre Streamlit */
        .block-container {
            padding-top: 3.5rem !important; /* Passe de 1.6rem à 3.5rem */
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }

        .optimarge-header {
            padding-top: 0.5rem;
            margin-top: 0rem;
        }

        .optimarge-title {
            font-size: 1.8rem; /* Légèrement réduit pour éviter les retours à la ligne tronqués */
            line-height: 1.25;
            letter-spacing: -0.02em;
        }

        .optimarge-subtitle {
            font-size: 0.85rem;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.4rem;
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
    """
    <div class="optimarge-header">
        <div class="optimarge-title">
            🛒 OptiMarge Food
        </div>
        <div class="optimarge-subtitle">
            Comparateur intelligent de prix fournisseurs
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# UNITÉS
# ============================================================

CORRESPONDANCES_UNITES = {

    # Masse
    "G": "G",
    "GR": "G",
    "GRAM": "G",
    "GRAMME": "G",
    "GRAMMES": "G",

    "KG": "KG",
    "KGS": "KG",
    "KILO": "KG",
    "KILOS": "KG",
    "KILOGRAM": "KG",
    "KILOGRAMS": "KG",

    "LB": "LB",
    "LBS": "LB",
    "LIVRE": "LB",
    "LIVRES": "LB",
    "POUND": "LB",
    "POUNDS": "LB",

    "OZ": "OZ",
    "OUNCE": "OZ",
    "OUNCES": "OZ",

    # Volume
    "ML": "ML",
    "MILLILITRE": "ML",
    "MILLILITRES": "ML",
    "MILLILITER": "ML",
    "MILLILITERS": "ML",

    "CL": "CL",
    "CENTILITRE": "CL",
    "CENTILITRES": "CL",
    "CENTILITER": "CL",
    "CENTILITERS": "CL",

    "L": "L",
    "LT": "L",
    "LTR": "L",
    "LITRE": "L",
    "LITRES": "L",
    "LITER": "L",
    "LITERS": "L",

    "FL OZ": "FL OZ",
    "FLOZ": "FL OZ",

    "GAL": "GAL",
    "GALLON": "GAL",
    "GALLONS": "GAL",

    # Unités
    "U": "U",
    "UN": "U",
    "UNITE": "U",
    "UNITES": "U",
    "UNIT": "U",
    "UNITS": "U",

    "EA": "U",
    "EACH": "U",
    "PIECE": "U",
    "PIECES": "U",
    "PCS": "U",
    "PC": "U",
    "COUNT": "U",
    "CT": "U",

    "PACK": "U",
    "PACKS": "U",
    "PK": "U",

    "BOX": "U",
    "BOXES": "U",
    "BX": "U",

    "BAG": "U",
    "BAGS": "U",
    "SAC": "U",
    "SACS": "U",

    "SACHET": "U",
    "SACHETS": "U",

    "BOTTLE": "U",
    "BOTTLES": "U",
    "BOUTEILLE": "U",
    "BOUTEILLES": "U",

    "CASE": "U",
    "CASES": "U",
    "CARTON": "U",
    "CARTONS": "U",

    "BARQUETTE": "U",
    "BARQUETTES": "U",

    "BIDON": "U",
    "BIDONS": "U",

    "DOZ": "DOZ",
    "DOZEN": "DOZ",
}


FACTEURS_CONVERSION = {

    "G": ("KG", 0.001),
    "KG": ("KG", 1.0),

    "LB": ("KG", 0.45359237),
    "OZ": ("KG", 0.028349523125),

    "ML": ("L", 0.001),
    "CL": ("L", 0.01),
    "L": ("L", 1.0),

    "FL OZ": ("L", 0.0295735295625),
    "GAL": ("L", 3.785411784),

    "U": ("U", 1.0),
    "DOZ": ("U", 12.0),
}


UNITES_COMPARABLES = {
    "KG",
    "L",
    "U",
}


BASES_PRIX_DIRECTES = {
    "KG",
    "G",
    "LB",
    "OZ",
    "L",
    "ML",
    "CL",
    "U",
}


STOPWORDS_PRODUIT = {
    "DE",
    "DU",
    "DES",
    "LA",
    "LE",
    "LES",
    "D",
    "AU",
    "AUX",
    "EN",
    "ET",
    "THE",
    "OF",
    "AND",
    "FOR",
    "WITH",
}


# ============================================================
# CONFIGURATION RÉGION
# ============================================================

def configuration_region(region):

    mots_communs_prix = [
        "prix",
        "tarif",
        "cout",
        "coût",
        "pu",
        "p.u",
        "prix unitaire",
        "tarif unitaire",
        "prix ht",
        "prix ttc",
        "tarif ht",
        "montant",
        "amount",
        "price",
        "cost",
        "unit price",
        "unit cost",
        "purchase price",
        "supplier price",
        "wholesale price",
        "net price",
        "net cost",
    ]

    mots_communs_produit = [
        "produit",
        "article",
        "designation",
        "désignation",
        "libelle",
        "libellé",
        "description",
        "reference",
        "référence",
        "code produit",
        "nom produit",
        "item",
        "item name",
        "item number",
        "sku",
        "product",
        "product name",
        "product description",
    ]

    mots_unite = [
        "unite",
        "unité",
        "unit",
        "units",
        "uom",
        "format",
        "conditionnement",
        "pack",
        "package",
        "packaging",
        "contenance",
        "size",
        "weight",
        "poids",
        "volume",
    ]

    mots_quantite = [
        "quantite",
        "quantité",
        "qty",
        "quantity",
        "qte",
        "nombre",
        "nb",
        "count",
    ]

    if region == "France 🇫🇷":

        return {
            "pays": "FR",
            "devise": "EUR",
            "symbole": "€",
            "mots_prix": mots_communs_prix + [
                "prix achat",
                "prix fournisseur",
                "cout achat",
                "coût achat",
                "prix au kg",
                "prix au kilo",
                "prix au litre",
                "prix par unite",
                "prix par unité",
                "prix par piece",
                "prix par pièce",
            ],
            "mots_produit": mots_communs_produit,
            "mots_unite": mots_unite,
            "mots_quantite": mots_quantite,
        }

    return {
        "pays": "CA",
        "devise": "CAD",
        "symbole": "CA$",
        "mots_prix": mots_communs_prix + [
            "wholesale",
            "sale price",
            "price per kg",
            "price per lb",
            "price per litre",
            "price per unit",
            "price per piece",
        ],
        "mots_produit": mots_communs_produit,
        "mots_unite": mots_unite,
        "mots_quantite": mots_quantite,
    }


# ============================================================
# UTILITAIRES
# ============================================================

def colonnes_existantes(df, colonnes):

    return [
        c
        for c in colonnes
        if c in df.columns
    ]


def valeur_vide(valeur):

    if valeur is None:
        return True

    try:
        if pd.isna(valeur):
            return True
    except Exception:
        pass

    return not str(valeur).strip()


def cle_streamlit(texte):

    texte = str(texte)

    texte = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        texte,
    )

    return texte[:80]


# ============================================================
# NORMALISATION TEXTE
# ============================================================

def normaliser_texte(texte):

    if valeur_vide(texte):
        return ""

    texte = str(texte).strip().lower()

    texte = texte.replace("×", "x")
    texte = texte.replace("✕", "x")
    texte = texte.replace("–", "-")
    texte = texte.replace("—", "-")
    texte = texte.replace("\u00a0", " ")
    texte = texte.replace("\u202f", " ")

    texte = unicodedata.normalize(
        "NFKD",
        texte,
    )

    texte = "".join(
        c
        for c in texte
        if not unicodedata.combining(c)
    )

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    )

    return texte.strip()


def normaliser_produit(produit):

    s = normaliser_texte(produit)

    s = re.sub(
        r"[^a-z0-9]+",
        " ",
        s,
    )

    s = re.sub(
        r"\s+",
        " ",
        s,
    ).strip()

    return s.upper()


def cle_produit_fuzzy(produit):

    s = normaliser_produit(produit)

    if not s:
        return ""

    # Multipack : 12 X 355 ML
    s = re.sub(
        r"""
        \b
        \d+(?:[.,]\d+)?
        \s*x\s*
        \d+(?:[.,]\d+)?
        \s*
        (?:KG|KGS|KILO|KILOS|G|GR|GRAM|GRAMME|GRAMMES|
        LB|LBS|POUND|POUNDS|OZ|OUNCE|OUNCES|
        ML|CL|L|LT|LTR|LITRE|LITRES|LITER|LITERS)
        \b
        """,
        " ",
        s,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    # Conditionnement simple
    s = re.sub(
        r"""
        \b
        \d+(?:[.,]\d+)?
        \s*
        (?:KG|KGS|KILO|KILOS|G|GR|GRAM|GRAMME|GRAMMES|
        LB|LBS|POUND|POUNDS|OZ|OUNCE|OUNCES|
        ML|CL|L|LT|LTR|LITRE|LITRES|LITER|LITERS)
        \b
        """,
        " ",
        s,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    # Fractions
    s = re.sub(
        r"""
        \b
        \d+(?:[.,]\d+)?
        \s*/\s*
        \d+(?:[.,]\d+)?
        \s*
        (?:KG|G|LB|OZ|ML|CL|L)
        \b
        """,
        " ",
        s,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    tokens = [
        token
        for token in s.split()
        if token not in STOPWORDS_PRODUIT
    ]

    return " ".join(tokens).strip()


# ============================================================
# COLONNES
# ============================================================

def normaliser_noms_colonnes(df):

    df = df.copy()

    nouveaux_noms = []
    compteurs = {}

    for i, col in enumerate(df.columns):

        nom = (
            ""
            if pd.isna(col)
            else str(col).strip()
        )

        if (
            not nom
            or nom.lower().startswith("unnamed")
        ):
            nom = f"Colonne_{i + 1}"

        cle = normaliser_texte(nom)

        if cle in compteurs:

            compteurs[cle] += 1

            nom_final = (
                f"{nom}_{compteurs[cle]}"
            )

        else:

            compteurs[cle] = 0
            nom_final = nom

        nouveaux_noms.append(
            nom_final
        )

    df.columns = nouveaux_noms

    return df


# ============================================================
# PARSING NUMÉRIQUE
# ============================================================

def nettoyer_texte_numerique(
    valeur,
    retirer_devise=True,
):

    if valeur_vide(valeur):
        return ""

    if isinstance(
        valeur,
        (int, float, np.integer, np.floating),
    ) and not isinstance(valeur, bool):

        return str(float(valeur))

    texte = str(valeur).strip()

    texte = texte.replace(
        "\u00a0",
        "",
    )

    texte = texte.replace(
        "\u202f",
        "",
    )

    if retirer_devise:

        texte = re.sub(
            r"""
            (?:CAD|C\$|CA\$|CAN\$|
            USD|US\$|
            EUR|EURO|EUROS|
            GBP|£|€|\$)
            """,
            "",
            texte,
            flags=re.IGNORECASE | re.VERBOSE,
        )

    return texte.strip()


def parser_nombre_general(
    valeur,
    pays="FR",
):

    texte = nettoyer_texte_numerique(
        valeur
    )

    if not texte:
        return np.nan

    texte = texte.replace(
        " ",
        "",
    )

    texte = re.sub(
        r"[^0-9,.\-]",
        "",
        texte,
    )

    if not texte:
        return np.nan

    if "," in texte and "." in texte:

        derniere_virgule = texte.rfind(",")
        dernier_point = texte.rfind(".")

        if derniere_virgule > dernier_point:

            texte = texte.replace(
                ".",
                "",
            )

            texte = texte.replace(
                ",",
                ".",
            )

        else:

            texte = texte.replace(
                ",",
                "",
            )

    elif "," in texte:

        morceaux = texte.split(",")

        if len(morceaux) == 2:

            avant, apres = morceaux

            if (
                pays == "CA"
                and len(apres) == 3
                and avant.isdigit()
                and apres.isdigit()
            ):

                texte = (
                    avant
                    + apres
                )

            else:

                texte = (
                    avant
                    + "."
                    + apres
                )

        else:

            texte = texte.replace(
                ",",
                "",
            )

    elif "." in texte:

        morceaux = texte.split(".")

        if len(morceaux) > 2:

            texte = texte.replace(
                ".",
                "",
            )

    try:

        nombre = float(texte)

        if not np.isfinite(nombre):
            return np.nan

        return nombre

    except Exception:

        return np.nan


def valeur_est_numerique(
    valeur,
    pays="FR",
):

    return pd.notna(
        parser_nombre_general(
            valeur,
            pays,
        )
    )


def est_valeur_prix(
    valeur,
    pays="FR",
):

    if valeur_vide(valeur):
        return False

    if isinstance(
        valeur,
        (int, float, np.integer, np.floating),
    ) and not isinstance(valeur, bool):

        return np.isfinite(
            float(valeur)
        )

    texte = str(valeur).strip()

    if not texte:
        return False

    nombre = parser_nombre_general(
        valeur,
        pays,
    )

    if pd.isna(nombre):
        return False

    # Devise explicite
    if re.search(
        r"""
        [€$£]
        |
        \b(?:CAD|EUR|USD|GBP)\b
        |
        \b(?:CA\$|C\$|CAN\$|US\$)\b
        """,
        texte,
        flags=re.IGNORECASE | re.VERBOSE,
    ):
        return True

    # Décimale explicite
    if re.fullmatch(
        r"-?\d+[.,]\d{1,4}",
        texte.replace(" ", ""),
    ):
        return True

    return False


def convertir_prix_international(
    valeur,
    pays="FR",
):

    nombre = parser_nombre_general(
        valeur,
        pays,
    )

    if pd.isna(nombre):
        return np.nan

    if nombre < 0:
        return np.nan

    return float(nombre)


# ============================================================
# UNITÉS
# ============================================================

def normaliser_unite(unite):

    if valeur_vide(unite):
        return None

    u = normaliser_texte(
        unite
    ).upper()

    u = re.sub(
        r"\s+",
        " ",
        u,
    ).strip()

    return CORRESPONDANCES_UNITES.get(
        u,
        u,
    )


def convertir_quantite_unite(
    quantite,
    unite,
):

    if (
        quantite is None
        or pd.isna(quantite)
        or valeur_vide(unite)
    ):
        return None, None

    unite = normaliser_unite(
        unite
    )

    if unite in FACTEURS_CONVERSION:

        unite_finale, facteur = (
            FACTEURS_CONVERSION[unite]
        )

        return (
            float(quantite) * facteur,
            unite_finale,
        )

    return (
        float(quantite),
        unite,
    )


# ============================================================
# RATIOS
# ============================================================

def ratio_numerique(
    series,
    pays="FR",
):

    valeurs = series.dropna()

    if len(valeurs) == 0:
        return 0.0

    return sum(
        valeur_est_numerique(
            v,
            pays,
        )
        for v in valeurs
    ) / len(valeurs)


def ratio_prix(
    series,
    pays="FR",
):

    valeurs = series.dropna()

    if len(valeurs) == 0:
        return 0.0

    return sum(
        est_valeur_prix(
            v,
            pays,
        )
        for v in valeurs
    ) / len(valeurs)


def ratio_texte(series):

    valeurs = series.dropna()

    if len(valeurs) == 0:
        return 0.0

    total = 0

    for valeur in valeurs:

        texte = str(valeur).strip()

        if (
            len(texte) >= 3
            and not valeur_est_numerique(
                valeur
            )
        ):
            total += 1

    return total / len(valeurs)


def ratio_unites(series):

    valeurs = series.dropna()

    if len(valeurs) == 0:
        return 0.0

    total = 0

    for valeur in valeurs:

        unite = normaliser_unite(
            valeur
        )

        if unite in set(
            CORRESPONDANCES_UNITES.values()
        ):
            total += 1

    return total / len(valeurs)


# ============================================================
# CONDITIONNEMENTS
# ============================================================

UNITE_REGEX = (
    r"kg|kgs|kilogram|kilograms|kilo|kilos|"
    r"g|gr|gram|gramme|grammes|"
    r"lb|lbs|pound|pounds|"
    r"oz|ounce|ounces|"
    r"ml|millilitre|millilitres|milliliter|milliliters|"
    r"cl|centilitre|centilitres|centiliter|centiliters|"
    r"l|lt|ltr|litre|litres|liter|liters|"
    r"fl\s*oz|gal|gallon|gallons"
)


UNITE_COMPTE_REGEX = (
    r"u|un|unite|unites|unit|units|"
    r"ea|each|piece|pieces|pcs|pc|"
    r"pack|packs|pk|"
    r"box|boxes|bx|"
    r"bag|bags|sac|sacs|"
    r"sachet|sachets|"
    r"bottle|bottles|bouteille|bouteilles|"
    r"case|cases|"
    r"carton|cartons|"
    r"barquette|barquettes|"
    r"bidon|bidons|"
    r"count|ct"
)


REGEX_MULTIPACK = re.compile(
    rf"""
    (?P<q1>\d+(?:[.,]\d+)?)
    \s*[xX×✕]\s*
    (?P<q2>\d+(?:[.,]\d+)?)
    \s*
    (?P<unit>{UNITE_REGEX})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


REGEX_MULTIPACK_UNITES = re.compile(
    rf"""
    (?P<q1>\d+(?:[.,]\d+)?)
    \s*[xX×✕]\s*
    (?P<q2>\d+(?:[.,]\d+)?)
    \s*
    (?P<unit>{UNITE_COMPTE_REGEX})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


REGEX_FRACTION = re.compile(
    rf"""
    (?P<q1>\d+(?:[.,]\d+)?)
    \s*/\s*
    (?P<q2>\d+(?:[.,]\d+)?)
    \s*
    (?P<unit>{UNITE_REGEX})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


REGEX_SIMPLE = re.compile(
    rf"""
    (?P<q>\d+(?:[.,]\d+)?)
    \s*
    (?P<unit>{UNITE_REGEX})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


REGEX_PACK = re.compile(
    rf"""
    (?P<q>\d+(?:[.,]\d+)?)
    \s*
    (?:x|×|✕)?
    \s*
    (?P<unit>{UNITE_COMPTE_REGEX})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _nombre(texte):

    try:

        return float(
            str(texte).replace(
                ",",
                ".",
            )
        )

    except Exception:

        return np.nan


def extraire_conditionnement(
    texte,
):

    if valeur_vide(texte):
        return None

    texte = str(texte)

    # 12 x 355 ml
    match = REGEX_MULTIPACK.search(
        texte
    )

    if match:

        q1 = _nombre(
            match.group("q1")
        )

        q2 = _nombre(
            match.group("q2")
        )

        quantite_brute = q1 * q2

        quantite, unite_finale = (
            convertir_quantite_unite(
                quantite_brute,
                match.group("unit"),
            )
        )

        return {
            "texte": match.group(0),
            "quantite": quantite,
            "unite": unite_finale,
            "type": "multipack",
        }

    # 6 x bottles / 24 pcs
    match = REGEX_MULTIPACK_UNITES.search(
        texte
    )

    if match:

        q1 = _nombre(
            match.group("q1")
        )

        q2 = _nombre(
            match.group("q2")
        )

        return {
            "texte": match.group(0),
            "quantite": q1 * q2,
            "unite": "U",
            "type": "multipack_unites",
        }

    # 1/2 kg
    match = REGEX_FRACTION.search(
        texte
    )

    if match:

        q1 = _nombre(
            match.group("q1")
        )

        q2 = _nombre(
            match.group("q2")
        )

        if (
            pd.notna(q1)
            and pd.notna(q2)
            and q2 != 0
        ):

            quantite_brute = (
                q1 / q2
            )

            quantite, unite_finale = (
                convertir_quantite_unite(
                    quantite_brute,
                    match.group("unit"),
                )
            )

            return {
                "texte": match.group(0),
                "quantite": quantite,
                "unite": unite_finale,
                "type": "fraction",
            }

    # 1.5 kg / 500 g / 1,5 L
    match = REGEX_SIMPLE.search(
        texte
    )

    if match:

        q = _nombre(
            match.group("q")
        )

        quantite, unite_finale = (
            convertir_quantite_unite(
                q,
                match.group("unit"),
            )
        )

        return {
            "texte": match.group(0),
            "quantite": quantite,
            "unite": unite_finale,
            "type": "simple",
        }

    # 12 bottles / 24 pcs / 2 cases
    match = REGEX_PACK.search(
        texte
    )

    if match:

        q = _nombre(
            match.group("q")
        )

        return {
            "texte": match.group(0),
            "quantite": q,
            "unite": "U",
            "type": "pack",
        }

    return None


def extraire_conditionnements_vectorises(
    series,
):

    valeurs = []

    for texte in series:

        info = extraire_conditionnement(
            texte
        )

        if info is None:

            valeurs.append(
                {
                    "Conditionnement": "",
                    "Quantite_Etalon": np.nan,
                    "Unite_Etalon": None,
                    "Type_Conditionnement": "",
                }
            )

        else:

            valeurs.append(
                {
                    "Conditionnement": info["texte"],
                    "Quantite_Etalon": info["quantite"],
                    "Unite_Etalon": info["unite"],
                    "Type_Conditionnement": info["type"],
                }
            )

    return pd.DataFrame(
        valeurs,
        index=series.index,
    )


def extraire_produit_base(
    produit,
    conditionnement,
):

    produit = (
        ""
        if valeur_vide(produit)
        else str(produit)
    )

    if conditionnement:

        produit = re.sub(
            re.escape(
                str(conditionnement)
            ),
            " ",
            produit,
            flags=re.IGNORECASE,
        )

    produit = re.sub(
        rf"""
        \b
        \d+(?:[.,]\d+)?
        \s*
        (?:{UNITE_REGEX})
        \b
        """,
        " ",
        produit,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    produit = re.sub(
        rf"""
        \b
        \d+(?:[.,]\d+)?
        \s*[xX×✕]\s*
        \d+(?:[.,]\d+)?
        \s*
        (?:{UNITE_REGEX})
        \b
        """,
        " ",
        produit,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    produit = re.sub(
        r"\s+",
        " ",
        produit,
    ).strip()

    return produit


# ============================================================
# QUANTITÉ / UNITÉ
# ============================================================

def extraire_quantite_depuis_valeur(
    valeur,
    pays="FR",
):

    if valeur_vide(valeur):
        return None, None

    texte = str(
        valeur
    ).strip()

    if not texte:
        return None, None

    info = extraire_conditionnement(
        texte
    )

    if info:

        return (
            info["quantite"],
            info["unite"],
        )

    unite = normaliser_unite(
        texte
    )

    if unite:

        if unite == "DOZ":
            return 12.0, "U"

        return 1.0, unite

    nombre = parser_nombre_general(
        valeur,
        pays,
    )

    if pd.notna(nombre):

        return (
            float(nombre),
            None,
        )

    return None, None


# ============================================================
# SCORE DES COLONNES
# ============================================================

def score_nom_colonne(
    colonne,
    config,
    type_colonne,
):

    nom = normaliser_texte(
        colonne
    )

    if not nom:
        return 0.0

    if type_colonne == "produit":
        mots = config["mots_produit"]

    elif type_colonne == "prix":
        mots = config["mots_prix"]

    elif type_colonne == "unite":
        mots = config["mots_unite"]

    elif type_colonne == "quantite":
        mots = config["mots_quantite"]

    else:
        mots = []

    score = 0.0

    for mot in mots:

        mot_normalise = normaliser_texte(
            mot
        )

        if not mot_normalise:
            continue

        if nom == mot_normalise:

            score += 120

        elif re.search(
            rf"\b{re.escape(mot_normalise)}\b",
            nom,
        ):

            score += 55

        elif mot_normalise in nom:

            score += 25

    return float(score)


def score_colonne_contenu(
    df,
    colonne,
    type_colonne,
    config,
):

    if colonne not in df.columns:
        return 0.0

    valeurs = (
        df[colonne]
        .dropna()
        .head(300)
    )

    if valeurs.empty:
        return 0.0

    pays = config["pays"]

    numerique = ratio_numerique(
        valeurs,
        pays,
    )

    prix = ratio_prix(
        valeurs,
        pays,
    )

    texte = ratio_texte(
        valeurs
    )

    unites = ratio_unites(
        valeurs
    )

    conditionnements = (
        sum(
            extraire_conditionnement(v)
            is not None
            for v in valeurs
        )
        / len(valeurs)
    )

    longueur_moyenne = np.mean(
        [
            len(str(v))
            for v in valeurs
        ]
    )

    unicite = (
        valeurs.astype(str)
        .nunique()
        / max(len(valeurs), 1)
    )

    references = 0

    for valeur in valeurs:

        s = normaliser_texte(
            valeur
        )

        if re.fullmatch(
            r"[a-z]{0,6}[-_/]?\d{4,}",
            s,
        ):
            references += 1

    taux_references = (
        references / len(valeurs)
    )

    taux_lettres = (
        valeurs.astype(str)
        .apply(
            lambda x: bool(
                re.search(
                    r"[A-Za-zÀ-ÿ]",
                    str(x),
                )
            )
        )
        .mean()
    )

    score = 0.0

    # Produit
    if type_colonne == "produit":

        score += texte * 55
        score += taux_lettres * 20

        score += min(
            longueur_moyenne / 20.0,
            1.0,
        ) * 20

        score += min(
            unicite,
            1.0,
        ) * 10

        score += conditionnements * 15

        score -= prix * 70
        score -= numerique * 75
        score -= taux_references * 35

    # Prix
    elif type_colonne == "prix":

        score += numerique * 45
        score += prix * 90

        decimal_ratio = (
            valeurs.astype(str)
            .str.contains(
                r"[.,]\d",
                regex=True,
            )
            .mean()
        )

        score += decimal_ratio * 25

        score -= texte * 30
        score -= unites * 35
        score -= taux_references * 50

    # Unité
    elif type_colonne == "unite":

        score += unites * 120
        score += conditionnements * 20
        score -= numerique * 45
        score -= prix * 35

    # Quantité
    elif type_colonne == "quantite":

        score += numerique * 90
        score += conditionnements * 25
        score -= prix * 35
        score -= taux_references * 35

        if longueur_moyenne < 15:
            score += 10

    return float(score)


def score_colonne(
    df,
    colonne,
    config,
    type_colonne,
):

    return float(
        score_nom_colonne(
            colonne,
            config,
            type_colonne,
        )
        +
        score_colonne_contenu(
            df,
            colonne,
            type_colonne,
            config,
        )
    )


# ============================================================
# DÉTECTION DES COLONNES
# ============================================================

def detecter_colonnes(
    df,
    config,
):

    if df is None or df.empty:
        return (
            None,
            None,
            [],
            None,
            None,
        )

    df = normaliser_noms_colonnes(
        df
    )

    colonnes = list(
        df.columns
    )

    if not colonnes:
        return (
            None,
            None,
            [],
            None,
            None,
        )

    scores = {}

    for type_colonne in [
        "produit",
        "prix",
        "unite",
        "quantite",
    ]:

        scores[type_colonne] = {
            col: score_colonne(
                df,
                col,
                config,
                type_colonne,
            )
            for col in colonnes
        }

    # Produit
    col_produit = max(
        colonnes,
        key=lambda c:
        scores["produit"][c],
    )

    # Prix
    candidats_prix = [
        c
        for c in colonnes
        if c != col_produit
    ]

    col_prix = (
        max(
            candidats_prix,
            key=lambda c:
            scores["prix"][c],
        )
        if candidats_prix
        else None
    )

    # Unité
    exclus = {
        col_produit,
        col_prix,
    }

    candidats_unite = [
        c
        for c in colonnes
        if c not in exclus
        and scores["unite"][c] >= 35
    ]

    col_unite = (
        max(
            candidats_unite,
            key=lambda c:
            scores["unite"][c],
        )
        if candidats_unite
        else None
    )

    # Quantité
    exclus_quantite = {
        col_produit,
        col_prix,
        col_unite,
    }

    candidats_quantite = [
        c
        for c in colonnes
        if c not in exclus_quantite
        and scores["quantite"][c] >= 35
    ]

    col_quantite = (
        max(
            candidats_quantite,
            key=lambda c:
            scores["quantite"][c],
        )
        if candidats_quantite
        else None
    )

    diagnostics = []

    for col in colonnes:

        serie = (
            df[col]
            .dropna()
            .head(300)
        )

        if len(serie) > 0:

            taux_conditionnement = (
                sum(
                    extraire_conditionnement(v)
                    is not None
                    for v in serie
                )
                / len(serie)
                * 100
            )

        else:

            taux_conditionnement = 0.0

        diagnostics.append(
            {
                "Colonne": str(col),

                "Score Produit": round(
                    scores["produit"][col],
                    1,
                ),

                "Score Prix": round(
                    scores["prix"][col],
                    1,
                ),

                "Score Unité": round(
                    scores["unite"][col],
                    1,
                ),

                "Score Quantité": round(
                    scores["quantite"][col],
                    1,
                ),

                "% numérique": round(
                    ratio_numerique(
                        df[col],
                        config["pays"],
                    ) * 100,
                    1,
                ),

                "% prix": round(
                    ratio_prix(
                        df[col],
                        config["pays"],
                    ) * 100,
                    1,
                ),

                "% unités": round(
                    ratio_unites(
                        df[col]
                    ) * 100,
                    1,
                ),

                "% conditionnement": round(
                    taux_conditionnement,
                    1,
                ),

                "Produit retenu":
                    "✅"
                    if col == col_produit
                    else "",

                "Prix retenu":
                    "💰"
                    if col == col_prix
                    else "",

                "Unité retenue":
                    "📦"
                    if col == col_unite
                    else "",

                "Quantité retenue":
                    "🔢"
                    if col == col_quantite
                    else "",
            }
        )

    return (
        col_produit,
        col_prix,
        diagnostics,
        col_unite,
        col_quantite,
    )


# ============================================================
# DÉTECTION EN-TÊTE
# ============================================================

def score_ligne_entete(
    ligne,
    config,
):

    valeurs = [
        normaliser_texte(v)
        for v in ligne
        if not valeur_vide(v)
    ]

    if not valeurs:
        return 0.0

    texte = " ".join(
        valeurs
    )

    score = 0.0

    for mot in config["mots_produit"]:

        mot = normaliser_texte(
            mot
        )

        if (
            mot
            and re.search(
                rf"\b{re.escape(mot)}\b",
                texte,
            )
        ):

            score += 18

    for mot in config["mots_prix"]:

        mot = normaliser_texte(
            mot
        )

        if (
            mot
            and re.search(
                rf"\b{re.escape(mot)}\b",
                texte,
            )
        ):

            score += 18

    for mot in config["mots_unite"]:

        mot = normaliser_texte(
            mot
        )

        if (
            mot
            and re.search(
                rf"\b{re.escape(mot)}\b",
                texte,
            )
        ):

            score += 5

    score += min(
        len(valeurs) * 2,
        12,
    )

    numeriques = sum(
        valeur_est_numerique(
            v,
            config["pays"],
        )
        for v in valeurs
    )

    ratio_num = (
        numeriques / len(valeurs)
    )

    if ratio_num == 0:
        score += 8

    elif ratio_num < 0.25:
        score += 4

    return float(score)


def detecter_ligne_entete(
    df,
    config,
    max_lignes=20,
):

    if df is None or df.empty:
        return 0

    limite = min(
        max_lignes,
        len(df),
    )

    scores = []

    for i in range(limite):

        scores.append(
            score_ligne_entete(
                df.iloc[i].tolist(),
                config,
            )
        )

    if not scores:
        return 0

    meilleur = int(
        np.argmax(scores)
    )

    if scores[meilleur] < 18:
        return 0

    return meilleur


def appliquer_entete_detectee(
    df,
    config,
):

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    index_entete = detecter_ligne_entete(
        df,
        config,
    )

    header = df.iloc[
        index_entete
    ].tolist()

    nouveaux_noms = []

    for i, valeur in enumerate(header):

        nom = (
            ""
            if valeur_vide(valeur)
            else str(valeur).strip()
        )

        if (
            not nom
            or nom.lower().startswith("unnamed")
        ):

            nom = f"Colonne_{i + 1}"

        nouveaux_noms.append(
            nom
        )

    donnees = df.iloc[
        index_entete + 1:
    ].copy()

    donnees.columns = nouveaux_noms

    donnees = normaliser_noms_colonnes(
        donnees
    )

    donnees = donnees.dropna(
        how="all"
    )

    if not donnees.empty:

        donnees = donnees[
            ~donnees.apply(
                lambda row:
                all(
                    valeur_vide(v)
                    for v in row
                ),
                axis=1,
            )
        ]

    return donnees.reset_index(
        drop=True
    )


# ============================================================
# BASE DE PRIX
# ============================================================

def detecter_base_prix_colonne(
    nom_colonne,
):

    if valeur_vide(nom_colonne):
        return None

    s = normaliser_texte(
        nom_colonne
    )

    tests = [

        (
            "KG",
            r"(?:/|par|au|per)\s*(?:kg|kgs|kilo|kilos|kilogram|kilograms)\b",
        ),

        (
            "G",
            r"(?:/|par|au|per)\s*(?:g|gr|gram|gramme|grammes)\b",
        ),

        (
            "LB",
            r"(?:/|par|au|per)\s*(?:lb|lbs|livre|livres|pound|pounds)\b",
        ),

        (
            "OZ",
            r"(?:/|par|au|per)\s*(?:oz|once|onces|ounce|ounces)\b",
        ),

        (
            "L",
            r"(?:/|par|au|per)\s*(?:l|lt|ltr|litre|litres|liter|liters)\b",
        ),

        (
            "ML",
            r"(?:/|par|au|per)\s*(?:ml|millilitre|millilitres|milliliter|milliliters)\b",
        ),

        (
            "CL",
            r"(?:/|par|au|per)\s*(?:cl|centilitre|centilitres|centiliter|centiliters)\b",
        ),

        (
            "U",
            r"(?:/|par|au|per)\s*(?:u|un|unite|unites|unit|units|piece|pieces|ea|each)\b",
        ),
    ]

    for base, pattern in tests:

        if re.search(
            pattern,
            s,
            flags=re.IGNORECASE,
        ):

            return base

    if re.search(
        r"\b(?:prix|price|cout|cost|tarif)\b",
        s,
    ):

        mots_directs = [
            ("KG", r"\bkg\b"),
            ("G", r"\bg\b"),
            ("LB", r"\blb\b"),
            ("OZ", r"\boz\b"),
            ("ML", r"\bml\b"),
            ("CL", r"\bcl\b"),
            ("L", r"\bl\b"),
            (
                "U",
                r"\b(?:unit|unite|unites|piece|pieces|ea|each)\b",
            ),
        ]

        for base, pattern in mots_directs:

            if re.search(
                pattern,
                s,
                flags=re.IGNORECASE,
            ):

                return base

    return None


def detecter_base_prix_valeur(
    valeur,
):

    if valeur_vide(valeur):
        return None

    texte = normaliser_texte(
        valeur
    )

    tests = [

        ("KG", r"(?:/|par|au|per)\s*kg\b"),
        ("G", r"(?:/|par|au|per)\s*g\b"),
        ("LB", r"(?:/|par|au|per)\s*lbs?\b"),
        ("OZ", r"(?:/|par|au|per)\s*oz\b"),
        ("ML", r"(?:/|par|au|per)\s*ml\b"),
        ("CL", r"(?:/|par|au|per)\s*cl\b"),
        ("L", r"(?:/|par|au|per)\s*l\b"),
        (
            "U",
            r"(?:/|par|au|per)\s*(?:u|un|unit|units|unite|unites|piece|pieces|each|ea)\b",
        ),
    ]

    for base, pattern in tests:

        if re.search(
            pattern,
            texte,
            flags=re.IGNORECASE,
        ):

            return base

    return None


def convertir_prix_direct(
    prix,
    base,
):

    if (
        pd.isna(prix)
        or base not in BASES_PRIX_DIRECTES
    ):

        return np.nan, None

    prix = float(prix)

    if prix < 0:
        return np.nan, None

    if base == "KG":
        return prix, "KG"

    if base == "G":
        return prix * 1000, "KG"

    if base == "LB":
        return prix / 0.45359237, "KG"

    if base == "OZ":
        return prix / 0.028349523125, "KG"

    if base == "L":
        return prix, "L"

    if base == "ML":
        return prix * 1000, "L"

    if base == "CL":
        return prix * 100, "L"

    if base == "U":
        return prix, "U"

    return np.nan, None


# ============================================================
# MATCHING
# ============================================================

def score_matching(
    a,
    b,
):

    a = cle_produit_fuzzy(a)
    b = cle_produit_fuzzy(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    tokens_a = set(
        a.split()
    )

    tokens_b = set(
        b.split()
    )

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = (
        tokens_a & tokens_b
    )

    union = (
        tokens_a | tokens_b
    )

    jaccard = (
        len(intersection)
        / max(len(union), 1)
    )

    # Produits multi-mots sans aucun mot commun
    # = faux positif très probable.
    if (
        len(tokens_a) >= 2
        and len(tokens_b) >= 2
        and len(intersection) == 0
    ):

        return 0.0

    if RAPIDFUZZ_DISPONIBLE:

        ratio = (
            fuzz.ratio(a, b)
            / 100.0
        )

        token_set = (
            fuzz.token_set_ratio(a, b)
            / 100.0
        )

        token_sort = (
            fuzz.token_sort_ratio(a, b)
            / 100.0
        )

        partial = (
            fuzz.partial_ratio(a, b)
            / 100.0
        )

        score = (
            0.30 * ratio
            + 0.25 * token_set
            + 0.20 * token_sort
            + 0.10 * partial
            + 0.15 * jaccard
        )

    else:

        ratio = SequenceMatcher(
            None,
            a,
            b,
        ).ratio()

        score = (
            0.75 * ratio
            + 0.25 * jaccard
        )

    if (
        len(tokens_a) >= 2
        and len(tokens_b) >= 2
        and jaccard == 0
    ):

        return 0.0

    return float(
        max(
            0.0,
            min(
                score,
                1.0,
            ),
        )
    )


def determiner_unite_matching(
    ligne,
):

    unite = ligne.get(
        "Unite_Comparaison"
    )

    if not valeur_vide(unite):

        return str(
            unite
        ).strip().upper()

    return "BRUT"


def trouver_meilleur_groupe(
    cle,
    unite_matching,
    groupes,
):

    meilleur = None
    meilleur_score = 0.0

    for groupe in groupes:

        # IMPORTANT :
        # on ne mélange jamais KG, L, U et BRUT.
        if (
            groupe["unite"]
            != unite_matching
        ):

            continue

        for alias in groupe["alias"]:

            score = score_matching(
                cle,
                alias,
            )

            if score > meilleur_score:

                meilleur_score = score
                meilleur = groupe

    if meilleur is None:

        return (
            None,
            0.0,
            "nouveau",
        )

    if (
        meilleur_score
        >= SEUIL_MATCHING_FORT
    ):

        return (
            meilleur,
            meilleur_score,
            "fort",
        )

    if (
        meilleur_score
        >= SEUIL_MATCHING_PROBABLE
    ):

        return (
            meilleur,
            meilleur_score,
            "probable",
        )

    return (
        None,
        meilleur_score,
        "nouveau",
    )


def appliquer_matching(
    df,
):

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    groupes = []

    groupe_ids = []
    scores = []
    statuts = []
    unites_matching = []

    for _, ligne in df.iterrows():

        cle = ligne.get(
            "Cle_Produit",
            "",
        )

        unite_matching = (
            determiner_unite_matching(
                ligne
            )
        )

        groupe, score, statut = (
            trouver_meilleur_groupe(
                cle,
                unite_matching,
                groupes,
            )
        )

        if groupe is None:

            groupe = {
                "id": len(groupes),
                "cle": cle,
                "alias": (
                    [cle]
                    if cle
                    else []
                ),
                "unite": unite_matching,
            }

            groupes.append(
                groupe
            )

            groupe_ids.append(
                groupe["id"]
            )

            # IMPORTANT :
            # score interne = 1.0
            # donc score affiché = 100.0 %
            scores.append(
                1.0
            )

            statuts.append(
                "nouveau"
            )

        else:

            if (
                cle
                and cle not in groupe["alias"]
            ):

                groupe["alias"].append(
                    cle
                )

            groupe_ids.append(
                groupe["id"]
            )

            scores.append(
                float(score)
            )

            statuts.append(
                statut
            )

        unites_matching.append(
            unite_matching
        )

    df["Unite_Matching"] = (
        unites_matching
    )

    df["Groupe_Produit"] = (
        groupe_ids
    )

    # Toujours un float 0.0 -> 1.0
    df["Score_Matching"] = (
        pd.to_numeric(
            pd.Series(
                scores,
                index=df.index,
            ),
            errors="coerce",
        )
        .fillna(0.0)
        .clip(0.0, 1.0)
        .astype("float64")
    )

    # NOUVELLE COLONNE D'AFFICHAGE :
    # 1.0 devient 100.0
    # 0.92 devient 92.0
    #
    # On n'utilise volontairement PAS le format
    # Streamlit %.0f%% sur Score_Matching.
    # Cela élimine toute ambiguïté 1 % / 100 %.
    df["Match_Pourcent"] = (
        df["Score_Matching"]
        * 100.0
    ).clip(
        0.0,
        100.0,
    ).astype("float64")

    df["Statut_Matching"] = (
        statuts
    )

    return df


# ============================================================
# PRÉPARATION DES DONNÉES
# ============================================================

def preparer_donnees(
    df,
    col_produit,
    col_prix,
    fournisseur,
    config,
    col_unite=None,
    col_quantite=None,
):

    if df is None or df.empty:

        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    df = normaliser_noms_colonnes(
        df
    )

    colonnes = list(
        df.columns
    )

    if (
        col_produit not in colonnes
        or col_prix not in colonnes
    ):

        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    if col_unite not in colonnes:
        col_unite = None

    if col_quantite not in colonnes:
        col_quantite = None

    resultat = pd.DataFrame(
        index=df.index
    )

    # --------------------------------------------------------
    # Produit
    # --------------------------------------------------------

    resultat[
        "Produit_Affichage"
    ] = (
        df[col_produit]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    resultat[
        "Cle_Produit_Brut"
    ] = (
        resultat[
            "Produit_Affichage"
        ].apply(
            normaliser_produit
        )
    )

    # --------------------------------------------------------
    # Prix
    # --------------------------------------------------------

    # On conserve la valeur d'origine dans une colonne texte.
    resultat[
        "Prix_Brut_Affichage"
    ] = (
        df[col_prix]
        .map(
            lambda x:
            ""
            if valeur_vide(x)
            else str(x).strip()
        )
        .astype("string")
    )

    # IMPORTANT :
    # Prix_Brut est TOUJOURS numérique.
    resultat[
        "Prix_Brut"
    ] = (
        resultat[
            "Prix_Brut_Affichage"
        ]
        .apply(
            lambda x:
            convertir_prix_international(
                x,
                config["pays"],
            )
        )
    )

    resultat[
        "Prix_Brut"
    ] = pd.to_numeric(
        resultat[
            "Prix_Brut"
        ],
        errors="coerce",
    ).astype("float64")

    resultat[
        "Prix_Unitaire"
    ] = (
        resultat[
            "Prix_Brut"
        ]
        .copy()
        .astype("float64")
    )

    resultat[
        "Fournisseur"
    ] = str(
        fournisseur
    )

    # --------------------------------------------------------
    # Conditionnement
    # --------------------------------------------------------

    conditions = (
        extraire_conditionnements_vectorises(
            resultat[
                "Produit_Affichage"
            ]
        )
    )

    resultat = pd.concat(
        [
            resultat,
            conditions,
        ],
        axis=1,
    )

    # --------------------------------------------------------
    # Unité séparée
    # --------------------------------------------------------

    if col_unite is not None:

        for idx in resultat.index:

            unite_existante = (
                resultat.at[
                    idx,
                    "Unite_Etalon",
                ]
            )

            if not valeur_vide(
                unite_existante
            ):
                continue

            valeur_unite = df.at[
                idx,
                col_unite,
            ]

            (
                quantite_extraite,
                unite_extraite,
            ) = (
                extraire_quantite_depuis_valeur(
                    valeur_unite,
                    config["pays"],
                )
            )

            if unite_extraite:

                resultat.at[
                    idx,
                    "Unite_Etalon",
                ] = unite_extraite

                if pd.isna(
                    resultat.at[
                        idx,
                        "Quantite_Etalon",
                    ]
                ):

                    if quantite_extraite:

                        resultat.at[
                            idx,
                            "Quantite_Etalon",
                        ] = (
                            quantite_extraite
                        )

                        resultat.at[
                            idx,
                            "Conditionnement",
                        ] = (
                            f"{quantite_extraite:g} "
                            f"{unite_extraite}"
                        )

    # --------------------------------------------------------
    # Quantité séparée
    # --------------------------------------------------------

    if col_quantite is not None:

        for idx in resultat.index:

            if pd.notna(
                resultat.at[
                    idx,
                    "Quantite_Etalon",
                ]
            ):
                continue

            valeur_quantite = df.at[
                idx,
                col_quantite,
            ]

            if valeur_vide(
                valeur_quantite
            ):
                continue

            (
                quantite,
                unite,
            ) = extraire_quantite_depuis_valeur(
                valeur_quantite,
                config["pays"],
            )

            if quantite is None:
                continue

            if unite:

                (
                    quantite_finale,
                    unite_finale,
                ) = convertir_quantite_unite(
                    quantite,
                    unite,
                )

            else:

                unite_existante = (
                    resultat.at[
                        idx,
                        "Unite_Etalon",
                    ]
                )

                if unite_existante:

                    (
                        quantite_finale,
                        unite_finale,
                    ) = convertir_quantite_unite(
                        quantite,
                        unite_existante,
                    )

                else:

                    quantite_finale = (
                        quantite
                    )

                    unite_finale = None

            resultat.at[
                idx,
                "Quantite_Etalon",
            ] = quantite_finale

            if unite_finale:

                resultat.at[
                    idx,
                    "Unite_Etalon",
                ] = unite_finale

    # --------------------------------------------------------
    # Types numériques
    # --------------------------------------------------------

    resultat[
        "Quantite_Etalon"
    ] = pd.to_numeric(
        resultat[
            "Quantite_Etalon"
        ],
        errors="coerce",
    ).astype("float64")

    # --------------------------------------------------------
    # Produit base
    # --------------------------------------------------------

    resultat[
        "Produit_Base_Affichage"
    ] = [
        extraire_produit_base(
            produit,
            conditionnement,
        )
        for produit, conditionnement
        in zip(
            resultat[
                "Produit_Affichage"
            ],
            resultat[
                "Conditionnement"
            ],
        )
    ]

    resultat[
        "Cle_Produit"
    ] = (
        resultat[
            "Produit_Base_Affichage"
        ].apply(
            cle_produit_fuzzy
        )
    )

    # --------------------------------------------------------
    # Base prix
    # --------------------------------------------------------

    base_colonne = (
        detecter_base_prix_colonne(
            col_prix
        )
    )

    resultat[
        "Base_Prix"
    ] = base_colonne

    for idx in resultat.index:

        if valeur_vide(
            resultat.at[
                idx,
                "Base_Prix",
            ]
        ):

            # On utilise d'abord la colonne brute texte.
            base_valeur = (
                detecter_base_prix_valeur(
                    resultat.at[
                        idx,
                        "Prix_Brut_Affichage",
                    ]
                )
            )

            resultat.at[
                idx,
                "Base_Prix",
            ] = base_valeur

    # --------------------------------------------------------
    # Prix comparable
    # --------------------------------------------------------

    prix_comparables = []
    unites_comparaison = []
    modes_comparaison = []

    for _, ligne in resultat.iterrows():

        prix = ligne[
            "Prix_Unitaire"
        ]

        base_prix = ligne[
            "Base_Prix"
        ]

        quantite = ligne[
            "Quantite_Etalon"
        ]

        unite = normaliser_unite(
            ligne[
                "Unite_Etalon"
            ]
        )

        prix_comparable = np.nan
        unite_comparable = None
        mode = None

        # Prix direct
        if base_prix in BASES_PRIX_DIRECTES:

            (
                prix_direct,
                unite_directe,
            ) = convertir_prix_direct(
                prix,
                base_prix,
            )

            if pd.notna(
                prix_direct
            ):

                prix_comparable = (
                    prix_direct
                )

                unite_comparable = (
                    unite_directe
                )

                mode = "prix_direct"

        # Conditionnement
        if (
            pd.isna(
                prix_comparable
            )
            and pd.notna(prix)
            and pd.notna(quantite)
            and float(quantite) > 0
            and unite in UNITES_COMPARABLES
        ):

            prix_comparable = (
                float(prix)
                / float(quantite)
            )

            unite_comparable = unite
            mode = "conditionnement"

        # Fallback V4
        if (
            pd.isna(
                prix_comparable
            )
            and pd.notna(prix)
        ):

            prix_comparable = float(
                prix
            )

            unite_comparable = "BRUT"
            mode = "fallback_v4"

        prix_comparables.append(
            prix_comparable
        )

        unites_comparaison.append(
            unite_comparable
        )

        modes_comparaison.append(
            mode
        )

    resultat[
        "Prix_Comparable"
    ] = pd.to_numeric(
        prix_comparables,
        errors="coerce",
    ).astype("float64")

    resultat[
        "Unite_Comparaison"
    ] = unites_comparaison

    resultat[
        "Mode_Comparaison"
    ] = modes_comparaison

    # --------------------------------------------------------
    # Fiabilité
    # --------------------------------------------------------

    resultat[
        "Fiabilite_Comparaison"
    ] = (
        resultat[
            "Mode_Comparaison"
        ].map(
            {
                "prix_direct": "Élevée",
                "conditionnement": "Élevée",
                "fallback_v4": "À vérifier",
            }
        )
        .fillna("Faible")
    )

    # --------------------------------------------------------
    # Rejets
    # --------------------------------------------------------

    def raison_rejet(
        ligne,
    ):

        if valeur_vide(
            ligne[
                "Produit_Affichage"
            ]
        ):

            return "Produit vide"

        if valeur_vide(
            ligne[
                "Cle_Produit"
            ]
        ):

            return "Produit non identifiable"

        if pd.isna(
            ligne[
                "Prix_Unitaire"
            ]
        ):

            return "Prix non numérique"

        if (
            ligne[
                "Prix_Unitaire"
            ] < 0
        ):

            return "Prix négatif"

        if pd.isna(
            ligne[
                "Prix_Comparable"
            ]
        ):

            return "Prix comparable impossible"

        if (
            ligne[
                "Prix_Comparable"
            ] < 0
        ):

            return "Prix comparable négatif"

        if valeur_vide(
            ligne[
                "Unite_Comparaison"
            ]
        ):

            return "Unité de comparaison inconnue"

        return ""

    resultat[
        "Raison_Rejet"
    ] = resultat.apply(
        raison_rejet,
        axis=1,
    )

    rejetes = resultat[
        resultat[
            "Raison_Rejet"
        ] != ""
    ].copy()

    exploitable = resultat[
        resultat[
            "Raison_Rejet"
        ] == ""
    ].copy()

    if not exploitable.empty:

        exploitable = (
            exploitable.drop_duplicates(
                subset=[
                    "Cle_Produit",
                    "Prix_Unitaire",
                    "Fournisseur",
                    "Conditionnement",
                    "Unite_Comparaison",
                ]
            )
        )

    # Sécurisation numérique finale.
    for col in [
        "Prix_Brut",
        "Prix_Unitaire",
        "Prix_Comparable",
        "Quantite_Etalon",
    ]:

        if col in exploitable.columns:

            exploitable[col] = (
                pd.to_numeric(
                    exploitable[col],
                    errors="coerce",
                )
                .astype("float64")
            )

        if col in rejetes.columns:

            rejetes[col] = (
                pd.to_numeric(
                    rejetes[col],
                    errors="coerce",
                )
                .astype("float64")
            )

    return (
        exploitable.reset_index(
            drop=True
        ),
        rejetes.reset_index(
            drop=True
        ),
    )


# ============================================================
# SCORE STRUCTURE FICHIER
# ============================================================

def score_dataframe_structure(
    df,
    config,
):

    if df is None or df.empty:
        return -999.0

    try:

        (
            col_produit,
            col_prix,
            _,
            col_unite,
            col_quantite,
        ) = detecter_colonnes(
            df,
            config,
        )

    except Exception:

        return -999.0

    score = 0.0

    if col_produit:
        score += 100

    if col_prix:
        score += 100

    if col_unite:
        score += 10

    if col_quantite:
        score += 10

    score += min(
        len(df) / 1000,
        30,
    )

    score += min(
        len(df.columns),
        20,
    )

    return float(score)


# ============================================================
# LECTURE EXCEL
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_excel(
    contenu_bytes,
    pays,
):

    config = configuration_region(
        "France 🇫🇷"
        if pays == "FR"
        else "Canada 🇨🇦"
    )

    try:

        with pd.ExcelFile(
            io.BytesIO(
                contenu_bytes
            )
        ) as excel:

            candidats = []

            for feuille in excel.sheet_names:

                try:

                    df = excel.parse(
                        feuille,
                        header=None,
                        dtype=object,
                    )

                    df = df.dropna(
                        how="all"
                    )

                    if (
                        df.empty
                        or df.shape[1] < 2
                    ):

                        continue

                    df_prepare = (
                        appliquer_entete_detectee(
                            df,
                            config,
                        )
                    )

                    if (
                        df_prepare.empty
                        or df_prepare.shape[1] < 2
                    ):

                        continue

                    score = (
                        score_dataframe_structure(
                            df_prepare,
                            config,
                        )
                    )

                    score += min(
                        len(df_prepare) / 500,
                        10,
                    )

                    candidats.append(
                        (
                            score,
                            df_prepare,
                        )
                    )

                except Exception:

                    continue

            if not candidats:
                return pd.DataFrame()

            candidats.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            return normaliser_noms_colonnes(
                candidats[0][1]
            )

    except Exception:

        return pd.DataFrame()


# ============================================================
# LECTURE CSV
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_csv(
    contenu_bytes,
    pays,
):

    config = configuration_region(
        "France 🇫🇷"
        if pays == "FR"
        else "Canada 🇨🇦"
    )

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    separateurs = [
        ";",
        ",",
        "\t",
        "|",
    ]

    candidats = []

    for encoding in encodings:

        for separateur in separateurs:

            try:

                df = pd.read_csv(
                    io.BytesIO(
                        contenu_bytes
                    ),
                    encoding=encoding,
                    sep=separateur,
                    header=None,
                    dtype=object,
                    engine="python",
                    on_bad_lines="skip",
                )

                df = df.dropna(
                    how="all"
                )

                if (
                    df.empty
                    or df.shape[1] < 2
                ):

                    continue

                df_prepare = (
                    appliquer_entete_detectee(
                        df,
                        config,
                    )
                )

                if (
                    df_prepare.empty
                    or df_prepare.shape[1] < 2
                ):

                    continue

                score = (
                    score_dataframe_structure(
                        df_prepare,
                        config,
                    )
                )

                if df_prepare.shape[1] == 1:
                    score -= 100

                candidats.append(
                    (
                        score,
                        df_prepare,
                    )
                )

            except Exception:

                continue

    if not candidats:

        try:

            df = pd.read_csv(
                io.BytesIO(
                    contenu_bytes
                ),
                encoding="utf-8-sig",
                sep=None,
                engine="python",
                header=None,
                dtype=object,
            )

            df = df.dropna(
                how="all"
            )

            return normaliser_noms_colonnes(
                appliquer_entete_detectee(
                    df,
                    config,
                )
            )

        except Exception:

            return pd.DataFrame()

    candidats.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return normaliser_noms_colonnes(
        candidats[0][1]
    )


# ============================================================
# PDF
# ============================================================

def table_pdf_vers_df(
    table,
    config,
):

    if not table:
        return pd.DataFrame()

    lignes = []

    for ligne in table:

        if ligne is None:
            continue

        ligne_nettoyee = [
            ""
            if valeur is None
            else str(valeur).strip()
            for valeur in ligne
        ]

        if any(
            str(v).strip()
            for v in ligne_nettoyee
        ):

            lignes.append(
                ligne_nettoyee
            )

    if len(lignes) < 2:
        return pd.DataFrame()

    largeur = max(
        len(ligne)
        for ligne in lignes
    )

    lignes = [
        ligne
        + [""] * (
            largeur - len(ligne)
        )
        for ligne in lignes
    ]

    df = pd.DataFrame(
        lignes
    )

    return appliquer_entete_detectee(
        df,
        config,
    )


@st.cache_data(
    show_spinner=False
)
def lire_pdf(
    contenu_bytes,
    pays,
):

    if not PDFPLUMBER_DISPONIBLE:
        return pd.DataFrame()

    config = configuration_region(
        "France 🇫🇷"
        if pays == "FR"
        else "Canada 🇨🇦"
    )

    tables = []

    try:

        with pdfplumber.open(
            io.BytesIO(
                contenu_bytes
            )
        ) as pdf:

            for page in pdf.pages:

                try:

                    page_tables = (
                        page.extract_tables()
                    )

                except Exception:

                    page_tables = []

                for table in page_tables:

                    df = table_pdf_vers_df(
                        table,
                        config,
                    )

                    if (
                        not df.empty
                        and df.shape[1] >= 2
                    ):

                        tables.append(
                            df
                        )

    except Exception:

        return pd.DataFrame()

    if not tables:
        return pd.DataFrame()

    structures = []

    for df in tables:

        score = (
            score_dataframe_structure(
                df,
                config,
            )
        )

        structures.append(
            (
                score,
                df,
            )
        )

    structures.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    meilleure = structures[0][1]

    largeur = (
        meilleure.shape[1]
    )

    compatibles = [
        df
        for _, df in structures
        if df.shape[1] == largeur
    ]

    if compatibles:

        resultat = pd.concat(
            compatibles,
            ignore_index=True,
        )

    else:

        resultat = meilleure.copy()

    resultat = normaliser_noms_colonnes(
        resultat
    )

    # Suppression des lignes d'en-tête répétées.
    noms_colonnes = [
        normaliser_texte(c)
        for c in resultat.columns
    ]

    lignes_a_garder = []

    for _, ligne in resultat.iterrows():

        valeurs = [
            normaliser_texte(v)
            for v in ligne.tolist()
        ]

        correspondances = sum(
            1
            for a, b in zip(
                valeurs,
                noms_colonnes,
            )
            if a
            and b
            and a == b
        )

        lignes_a_garder.append(
            correspondances
            < max(
                2,
                int(
                    len(noms_colonnes)
                    * 0.5
                ),
            )
        )

    resultat = resultat[
        lignes_a_garder
    ]

    return resultat.reset_index(
        drop=True
    )


# ============================================================
# LECTURE FICHIER
# ============================================================

def lire_fichier_fournisseur(
    fichier,
    config,
):

    contenu_bytes = (
        fichier.getvalue()
    )

    extension = (
        fichier.name
        .lower()
        .rsplit(
            ".",
            1,
        )[-1]
    )

    pays = config["pays"]

    if extension in {
        "xlsx",
        "xls",
    }:

        return lire_excel(
            contenu_bytes,
            pays,
        )

    if extension == "csv":

        return lire_csv(
            contenu_bytes,
            pays,
        )

    if extension == "pdf":

        return lire_pdf(
            contenu_bytes,
            pays,
        )

    return pd.DataFrame()


# ============================================================
# SÉCURISATION STREAMLIT / PYARROW
# ============================================================

COLONNES_NUMERIQUES = {
    "Prix_Brut",
    "Prix_Unitaire",
    "Prix_Comparable",
    "Quantite_Etalon",
    "Facteur_Conversion",
    "Score_Matching",
    "Match_Pourcent",
}


def rendre_dataframe_streamlit(
    df,
):

    if df is None:
        return pd.DataFrame()

    df = df.copy()

    # --------------------------------------------------------
    # Colonnes numériques
    # --------------------------------------------------------

    for col in COLONNES_NUMERIQUES:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            ).astype("float64")

    # --------------------------------------------------------
    # Colonnes object
    #
    # On élimine les mélanges str/float/list/etc.
    # responsables des erreurs Arrow.
    # --------------------------------------------------------

    for col in df.columns:

        if pd.api.types.is_object_dtype(
            df[col]
        ):

            df[col] = (
                df[col]
                .map(
                    lambda x:
                    ""
                    if valeur_vide(x)
                    else str(x)
                )
                .astype("string")
            )

    return df


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "⚙️ Configuration"
)

region = st.sidebar.selectbox(
    "🌍 Région",
    [
        "France 🇫🇷",
        "Canada 🇨🇦",
    ],
)

config = configuration_region(
    region
)

devise = config[
    "devise"
]

symbole = config[
    "symbole"
]

st.sidebar.info(
    f"Devise utilisée : "
    f"**{devise} ({symbole})**"
)

st.sidebar.markdown(
    "---"
)

st.sidebar.caption(
    VERSION_APP
)

st.sidebar.caption(
    "Détection générique par nom + contenu."
)

st.sidebar.caption(
    "Matching exact + fuzzy + unités comparables."
)


# ============================================================
# IMPORT
# ============================================================

st.subheader(
    "📂 Importer les tarifs fournisseurs"
)

st.caption(
    "Formats acceptés : Excel, CSV et PDF"
)

fichiers = st.file_uploader(
    "Dépose les fichiers fournisseurs ici",
    type=[
        "xlsx",
        "xls",
        "csv",
        "pdf",
    ],
    accept_multiple_files=True,
)


if not fichiers:

    st.info(
        "👆 Ajoute au moins un fichier fournisseur "
        "pour commencer la comparaison."
    )

    st.stop()


# ============================================================
# STOCKAGE
# ============================================================

donnees_fournisseurs = {}
rejets_fournisseurs = {}
diagnostics_globaux = []


# ============================================================
# TRAITEMENT
# ============================================================

for numero_fichier, fichier in enumerate(
    fichiers
):

    nom_fournisseur = (
        fichier.name
        .rsplit(
            ".",
            1,
        )[0]
    )

    cle_fichier = (
        f"{cle_streamlit(fichier.name)}"
        f"_{numero_fichier}"
    )

    with st.spinner(
        f"Lecture de {fichier.name}..."
    ):

        df_brut = lire_fichier_fournisseur(
            fichier,
            config,
        )

    if df_brut.empty:

        st.error(
            f"❌ Impossible de lire "
            f"**{fichier.name}**."
        )

        diagnostics_globaux.append(
            {
                "Fournisseur": nom_fournisseur,
                "Fichier": fichier.name,
                "Lignes brutes": 0,
                "Offres exploitables": 0,
                "Offres rejetées": 0,
                "Colonne produit": "",
                "Colonne prix": "",
                "Colonne unité": "",
                "Colonne quantité": "",
                "Statut": "Lecture impossible",
            }
        )

        continue

    (
        col_produit,
        col_prix,
        diagnostics,
        col_unite_detectee,
        col_quantite_detectee,
    ) = detecter_colonnes(
        df_brut,
        config,
    )

    with st.expander(
        f"📄 {nom_fournisseur}",
        expanded=True,
    ):

        st.markdown(
            f"""
            <div class="provider-card">
                <strong>{fichier.name}</strong><br>
                <span class="small-muted">
                    {len(df_brut)} lignes détectées —
                    {len(df_brut.columns)} colonnes
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write(
            f"**Produit détecté :** `{col_produit}`"
        )

        st.write(
            f"**Prix détecté :** `{col_prix}`"
        )

        if col_unite_detectee:

            st.write(
                f"**Unité détectée :** "
                f"`{col_unite_detectee}`"
            )

        if col_quantite_detectee:

            st.write(
                f"**Quantité détectée :** "
                f"`{col_quantite_detectee}`"
            )

        correction = st.checkbox(
            "🛠️ Corriger les colonnes manuellement",
            key=f"correction_{cle_fichier}",
        )

        if correction:

            colonnes = list(
                df_brut.columns
            )

            nouveau_produit = st.selectbox(
                "Colonne Produit",
                colonnes,
                index=(
                    colonnes.index(
                        col_produit
                    )
                    if col_produit in colonnes
                    else 0
                ),
                key=f"produit_{cle_fichier}",
            )

            choix_prix = [
                col
                for col in colonnes
                if col != nouveau_produit
            ]

            if not choix_prix:

                st.error(
                    "Impossible de sélectionner "
                    "une colonne prix différente."
                )

                continue

            nouveau_prix = st.selectbox(
                "Colonne Prix",
                choix_prix,
                index=(
                    choix_prix.index(
                        col_prix
                    )
                    if col_prix in choix_prix
                    else 0
                ),
                key=f"prix_{cle_fichier}",
            )

            choix_unite = [
                "(Aucune)"
            ] + [
                col
                for col in colonnes
                if col not in {
                    nouveau_produit,
                    nouveau_prix,
                }
            ]

            index_unite = 0

            if (
                col_unite_detectee
                in choix_unite
            ):

                index_unite = (
                    choix_unite.index(
                        col_unite_detectee
                    )
                )

            nouvelle_unite = st.selectbox(
                "Colonne Unité — optionnel",
                choix_unite,
                index=index_unite,
                key=f"unite_{cle_fichier}",
            )

            choix_quantite = [
                "(Aucune)"
            ] + [
                col
                for col in colonnes
                if col not in {
                    nouveau_produit,
                    nouveau_prix,
                    nouvelle_unite,
                }
            ]

            index_quantite = 0

            if (
                col_quantite_detectee
                in choix_quantite
            ):

                index_quantite = (
                    choix_quantite.index(
                        col_quantite_detectee
                    )
                )

            nouvelle_quantite = st.selectbox(
                "Colonne Quantité — optionnel",
                choix_quantite,
                index=index_quantite,
                key=f"quantite_{cle_fichier}",
            )

            col_produit = (
                nouveau_produit
            )

            col_prix = (
                nouveau_prix
            )

            col_unite_detectee = (
                None
                if nouvelle_unite
                == "(Aucune)"
                else nouvelle_unite
            )

            col_quantite_detectee = (
                None
                if nouvelle_quantite
                == "(Aucune)"
                else nouvelle_quantite
            )

        # ----------------------------------------------------
        # Aperçu
        # ----------------------------------------------------

        with st.expander(
            "👀 Aperçu du fichier"
        ):

            st.dataframe(
                rendre_dataframe_streamlit(
                    df_brut.head(15)
                ),
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------------------------
        # Scores
        # ----------------------------------------------------

        with st.expander(
            "🔎 Scores de détection"
        ):

            st.dataframe(
                rendre_dataframe_streamlit(
                    pd.DataFrame(
                        diagnostics
                    )
                ),
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------------------------
        # Préparation
        # ----------------------------------------------------

        (
            df_clean,
            df_rejets,
        ) = preparer_donnees(
            df_brut,
            col_produit,
            col_prix,
            nom_fournisseur,
            config,
            col_unite=col_unite_detectee,
            col_quantite=col_quantite_detectee,
        )

        if df_clean.empty:

            st.warning(
                "⚠️ Aucune offre exploitable "
                "après nettoyage."
            )

        else:

            st.success(
                f"✅ {len(df_clean)} offres exploitables"
            )

        if not df_rejets.empty:

            st.warning(
                f"⚠️ {len(df_rejets)} ligne(s) rejetée(s)"
            )

            with st.expander(
                "Voir les lignes rejetées"
            ):

                colonnes_rejets = [
                    "Produit_Affichage",
                    "Prix_Brut_Affichage",
                    "Prix_Brut",
                    "Prix_Unitaire",
                    "Conditionnement",
                    "Quantite_Etalon",
                    "Unite_Etalon",
                    "Raison_Rejet",
                ]

                colonnes_rejets = (
                    colonnes_existantes(
                        df_rejets,
                        colonnes_rejets,
                    )
                )

                st.dataframe(
                    rendre_dataframe_streamlit(
                        df_rejets[
                            colonnes_rejets
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

        # ----------------------------------------------------
        # Diagnostic
        # ----------------------------------------------------

        if not df_clean.empty:

            with st.expander(
                "🧪 Diagnostic de normalisation"
            ):

                colonnes_diagnostic = [
                    "Produit_Affichage",
                    "Produit_Base_Affichage",
                    "Prix_Brut_Affichage",
                    "Prix_Brut",
                    "Prix_Unitaire",
                    "Base_Prix",
                    "Conditionnement",
                    "Quantite_Etalon",
                    "Unite_Etalon",
                    "Prix_Comparable",
                    "Unite_Comparaison",
                    "Mode_Comparaison",
                    "Fiabilite_Comparaison",
                ]

                colonnes_diagnostic = (
                    colonnes_existantes(
                        df_clean,
                        colonnes_diagnostic,
                    )
                )

                st.dataframe(
                    rendre_dataframe_streamlit(
                        df_clean[
                            colonnes_diagnostic
                        ].head(30)
                    ),
                    width="stretch",
                    hide_index=True,
                )

        # ----------------------------------------------------
        # Stockage
        # ----------------------------------------------------

        if not df_clean.empty:

            donnees_fournisseurs[
                cle_fichier
            ] = df_clean

        if not df_rejets.empty:

            rejets_fournisseurs[
                cle_fichier
            ] = df_rejets

        diagnostics_globaux.append(
            {
                "Fournisseur": nom_fournisseur,
                "Fichier": fichier.name,
                "Lignes brutes": len(df_brut),
                "Offres exploitables": len(df_clean),
                "Offres rejetées": len(df_rejets),
                "Colonne produit":
                    col_produit or "",
                "Colonne prix":
                    col_prix or "",
                "Colonne unité":
                    col_unite_detectee or "",
                "Colonne quantité":
                    col_quantite_detectee or "",
                "Statut":
                    (
                        "OK"
                        if not df_clean.empty
                        else "Aucune offre exploitable"
                    ),
            }
        )


# ============================================================
# VÉRIFICATION
# ============================================================

if not donnees_fournisseurs:

    st.error(
        "❌ Aucun fichier ne contient de données "
        "exploitables."
    )

    if diagnostics_globaux:

        st.dataframe(
            rendre_dataframe_streamlit(
                pd.DataFrame(
                    diagnostics_globaux
                )
            ),
            width="stretch",
            hide_index=True,
        )

    st.stop()


# ============================================================
# FUSION
# ============================================================

df_total = pd.concat(
    list(
        donnees_fournisseurs.values()
    ),
    ignore_index=True,
)


# ============================================================
# MATCHING
# ============================================================

df_total = appliquer_matching(
    df_total
)


# ============================================================
# NOM CANONIQUE
# ============================================================

def choisir_nom_canonique(
    series,
):

    valeurs = [
        str(v).strip()
        for v in series
        if not valeur_vide(v)
    ]

    if not valeurs:
        return ""

    valeurs = sorted(
        valeurs,
        key=lambda s: (
            len(
                cle_produit_fuzzy(s)
            ),
            len(s),
            s.lower(),
        ),
    )

    return valeurs[0]


noms_canonique = (
    df_total
    .groupby(
        "Groupe_Produit"
    )[
        "Produit_Affichage"
    ]
    .agg(
        choisir_nom_canonique
    )
    .to_dict()
)

df_total[
    "Produit_Canonique"
] = (
    df_total[
        "Groupe_Produit"
    ].map(
        noms_canonique
    )
)


# ============================================================
# COMPARAISON
# ============================================================

cles_comparaison = [
    "Groupe_Produit",
    "Unite_Comparaison",
]

prix_minimum = (
    df_total
    .groupby(
        cles_comparaison
    )[
        "Prix_Comparable"
    ]
    .transform(
        "min"
    )
)

resultat = df_total[
    np.isclose(
        df_total[
            "Prix_Comparable"
        ].astype(float),
        prix_minimum.astype(float),
        rtol=1e-9,
        atol=1e-9,
    )
].copy()


# ============================================================
# TRI
# ============================================================

if not resultat.empty:

    resultat = resultat.sort_values(
        by=[
            "Produit_Canonique",
            "Unite_Comparaison",
            "Prix_Comparable",
            "Fournisseur",
        ],
        ascending=[
            True,
            True,
            True,
            True,
        ],
    )


# ============================================================
# KPI
# ============================================================

nombre_produits = (
    df_total[
        [
            "Groupe_Produit",
            "Unite_Comparaison",
        ]
    ]
    .drop_duplicates()
    .shape[0]
)


nombre_ex_aequo = 0

if not resultat.empty:

    nombre_ex_aequo = int(
        (
            resultat
            .groupby(
                [
                    "Groupe_Produit",
                    "Unite_Comparaison",
                ]
            )
            .size()
            > 1
        ).sum()
    )


nombre_fournisseurs = (
    df_total[
        "Fournisseur"
    ].nunique()
)


nombre_rejets = sum(
    len(df)
    for df in rejets_fournisseurs.values()
)


# ============================================================
# KPI
# ============================================================

st.divider()

st.subheader(
    "🏆 Meilleurs prix"
)

col1, col2, col3, col4 = (
    st.columns(4)
)

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
    len(df_total),
)

col4.metric(
    "Offres rejetées",
    nombre_rejets,
)


if nombre_ex_aequo > 0:

    st.info(
        f"ℹ️ {nombre_ex_aequo} groupe(s) "
        f"présente(nt) plusieurs fournisseurs "
        f"au même meilleur prix. Tous les ex æquo "
        f"sont conservés."
    )


# ============================================================
# TABLEAU PRINCIPAL
# ============================================================

if resultat.empty:

    st.error(
        "❌ Aucune offre comparable n'a été trouvée."
    )

    st.info(
        "Les données ont toutefois été analysées. "
        "Consulte les diagnostics ci-dessous."
    )

else:

    colonnes_affichage = [
        "Produit_Canonique",
        "Fournisseur",
        "Prix_Unitaire",
        "Prix_Comparable",
        "Unite_Comparaison",
        "Conditionnement",
        "Fiabilite_Comparaison",
        "Match_Pourcent",
        "Statut_Matching",
    ]

    colonnes_affichage = (
        colonnes_existantes(
            resultat,
            colonnes_affichage,
        )
    )

    resultat_affichage = (
        resultat[
            colonnes_affichage
        ].copy()
    )

    resultat_affichage = (
        resultat_affichage.rename(
            columns={

                "Produit_Canonique":
                    "Produit",

                "Prix_Unitaire":
                    f"Prix fournisseur ({devise})",

                "Prix_Comparable":
                    f"Prix comparable ({devise})",

                "Unite_Comparaison":
                    "Comparaison",

                "Fiabilite_Comparaison":
                    "Fiabilité",

                "Match_Pourcent":
                    "Match",

                "Statut_Matching":
                    "Matching",
            }
        )
    )

    # IMPORTANT :
    # Match est maintenant 0 -> 100,
    # pas 0 -> 1.
    resultat_affichage[
        "Match"
    ] = pd.to_numeric(
        resultat_affichage[
            "Match"
        ],
        errors="coerce",
    ).fillna(
        0.0
    ).clip(
        0.0,
        100.0,
    ).astype(
        "float64"
    )

    resultat_affichage = (
        rendre_dataframe_streamlit(
            resultat_affichage
        )
    )

    st.dataframe(
        resultat_affichage,
        width="stretch",
        hide_index=True,
        column_config={

            "Produit":
                st.column_config.TextColumn(
                    "Produit",
                ),

            f"Prix fournisseur ({devise})":
                st.column_config.NumberColumn(
                    f"Prix fournisseur ({devise})",
                    format=f"{symbole} %.2f",
                ),

            f"Prix comparable ({devise})":
                st.column_config.NumberColumn(
                    f"Prix comparable ({devise})",
                    format=f"{symbole} %.4f",
                ),

            "Comparaison":
                st.column_config.TextColumn(
                    "Unité",
                ),

            "Conditionnement":
                st.column_config.TextColumn(
                    "Conditionnement",
                ),

            "Fiabilité":
                st.column_config.TextColumn(
                    "Fiabilité",
                ),

            # IMPORTANT :
            # valeur = 100
            # format = 100 %
            #
            # On ne donne plus à Streamlit une valeur 1
            # avec un format percentage.
            "Match":
                st.column_config.NumberColumn(
                    "Match",
                    format="%.0f%%",
                    min_value=0.0,
                    max_value=100.0,
                ),

            "Matching":
                st.column_config.TextColumn(
                    "Matching",
                ),
        },
    )


# ============================================================
# TOUTES LES OFFRES
# ============================================================

with st.expander(
    "📊 Voir toutes les offres analysées"
):

    colonnes_toutes_offres = [
        "Produit_Affichage",
        "Produit_Canonique",
        "Fournisseur",
        "Prix_Brut_Affichage",
        "Prix_Brut",
        "Prix_Unitaire",
        "Base_Prix",
        "Conditionnement",
        "Quantite_Etalon",
        "Unite_Etalon",
        "Prix_Comparable",
        "Unite_Comparaison",
        "Mode_Comparaison",
        "Fiabilite_Comparaison",
        "Groupe_Produit",
        "Score_Matching",
        "Match_Pourcent",
        "Statut_Matching",
    ]

    colonnes_toutes_offres = (
        colonnes_existantes(
            df_total,
            colonnes_toutes_offres,
        )
    )

    toutes_offres = (
        df_total[
            colonnes_toutes_offres
        ].copy()
    )

    colonnes_tri = [
        c
        for c in [
            "Produit_Canonique",
            "Fournisseur",
        ]
        if c in toutes_offres.columns
    ]

    if colonnes_tri:

        toutes_offres = (
            toutes_offres.sort_values(
                by=colonnes_tri
            )
        )

    st.dataframe(
        rendre_dataframe_streamlit(
            toutes_offres
        ),
        width="stretch",
        hide_index=True,
    )


# ============================================================
# OFFRES REJETÉES
# ============================================================

tous_rejets = []

for df_rejet in (
    rejets_fournisseurs.values()
):

    tous_rejets.append(
        df_rejet
    )


if tous_rejets:

    df_tous_rejets = pd.concat(
        tous_rejets,
        ignore_index=True,
    )

else:

    df_tous_rejets = (
        pd.DataFrame()
    )


if not df_tous_rejets.empty:

    with st.expander(
        f"⚠️ Offres rejetées ({len(df_tous_rejets)})"
    ):

        colonnes_rejets = [
            "Produit_Affichage",
            "Fournisseur",
            "Prix_Brut_Affichage",
            "Prix_Brut",
            "Prix_Unitaire",
            "Conditionnement",
            "Quantite_Etalon",
            "Unite_Etalon",
            "Raison_Rejet",
        ]

        colonnes_rejets = (
            colonnes_existantes(
                df_tous_rejets,
                colonnes_rejets,
            )
        )

        st.dataframe(
            rendre_dataframe_streamlit(
                df_tous_rejets[
                    colonnes_rejets
                ]
            ),
            width="stretch",
            hide_index=True,
        )


# ============================================================
# EXPORT
# ============================================================

st.subheader(
    "📥 Export"
)


# ============================================================
# EXPORT MEILLEURS PRIX
# ============================================================

if not resultat.empty:

    colonnes_export = [
        "Produit_Canonique",
        "Fournisseur",
        "Prix_Unitaire",
        "Prix_Comparable",
        "Unite_Comparaison",
        "Conditionnement",
        "Fiabilite_Comparaison",
        "Match_Pourcent",
        "Statut_Matching",
    ]

    colonnes_export = (
        colonnes_existantes(
            resultat,
            colonnes_export,
        )
    )

    export_meilleurs = (
        resultat[
            colonnes_export
        ].copy()
    )

    export_meilleurs = (
        export_meilleurs.rename(
            columns={

                "Produit_Canonique":
                    "Produit",

                "Prix_Unitaire":
                    f"Prix fournisseur ({devise})",

                "Prix_Comparable":
                    f"Prix comparable ({devise})",

                "Unite_Comparaison":
                    "Unite comparaison",

                "Fiabilite_Comparaison":
                    "Fiabilite",

                "Match_Pourcent":
                    "Match (%)",

                "Statut_Matching":
                    "Statut matching",
            }
        )
    )

    export_meilleurs[
        "Match (%)"
    ] = pd.to_numeric(
        export_meilleurs[
            "Match (%)"
        ],
        errors="coerce",
    ).fillna(
        0.0
    ).round(
        0
    ).astype(
        "float64"
    )

    csv_export = (
        export_meilleurs.to_csv(
            index=False,
            encoding="utf-8-sig",
        )
    )

    st.download_button(
        label="📥 Télécharger les meilleurs prix (CSV)",
        data=csv_export,
        file_name=(
            "optimarge_meilleurs_prix.csv"
        ),
        mime="text/csv",
    )


# ============================================================
# EXPORT TOUTES LES OFFRES
# ============================================================

colonnes_export_toutes = [
    "Produit_Affichage",
    "Produit_Canonique",
    "Fournisseur",
    "Prix_Brut_Affichage",
    "Prix_Brut",
    "Prix_Unitaire",
    "Base_Prix",
    "Conditionnement",
    "Quantite_Etalon",
    "Unite_Etalon",
    "Prix_Comparable",
    "Unite_Comparaison",
    "Mode_Comparaison",
    "Fiabilite_Comparaison",
    "Groupe_Produit",
    "Score_Matching",
    "Match_Pourcent",
    "Statut_Matching",
]

colonnes_export_toutes = (
    colonnes_existantes(
        df_total,
        colonnes_export_toutes,
    )
)

toutes_offres_csv = (
    df_total[
        colonnes_export_toutes
    ].to_csv(
        index=False,
        encoding="utf-8-sig",
    )
)

st.download_button(
    label="📥 Télécharger toutes les offres analysées",
    data=toutes_offres_csv,
    file_name=(
        "optimarge_toutes_offres.csv"
    ),
    mime="text/csv",
)


# ============================================================
# EXPORT REJETS
# ============================================================

if not df_tous_rejets.empty:

    rejets_csv = (
        df_tous_rejets.to_csv(
            index=False,
            encoding="utf-8-sig",
        )
    )

    st.download_button(
        label="📥 Télécharger les offres rejetées",
        data=rejets_csv,
        file_name=(
            "optimarge_offres_rejetees.csv"
        ),
        mime="text/csv",
    )


# ============================================================
# DIAGNOSTICS TECHNIQUES
# ============================================================

with st.expander(
    "🧪 Détails techniques"
):

    if diagnostics_globaux:

        st.dataframe(
            rendre_dataframe_streamlit(
                pd.DataFrame(
                    diagnostics_globaux
                )
            ),
            width="stretch",
            hide_index=True,
        )

    st.write(
        f"**Version :** {VERSION_APP}"
    )

    st.write(
        f"**Région :** {region}"
    )

    st.write(
        f"**Devise :** {devise} ({symbole})"
    )

    st.write(
        f"**Fichiers exploitables :** "
        f"{len(donnees_fournisseurs)}"
    )

    st.write(
        f"**Offres analysées :** "
        f"{len(df_total)}"
    )

    st.write(
        f"**Offres rejetées :** "
        f"{len(df_tous_rejets)}"
    )

    st.write(
        f"**Groupes de comparaison :** "
        f"{nombre_produits}"
    )

    st.write(
        f"**Groupes avec ex æquo :** "
        f"{nombre_ex_aequo}"
    )

    st.write(
        f"**RapidFuzz disponible :** "
        f"{'Oui' if RAPIDFUZZ_DISPONIBLE else 'Non'}"
    )

    st.write(
        f"**pdfplumber disponible :** "
        f"{'Oui' if PDFPLUMBER_DISPONIBLE else 'Non'}"
    )

    st.write(
        f"**Seuil matching fort :** "
        f"{SEUIL_MATCHING_FORT:.0%}"
    )

    st.write(
        f"**Seuil matching probable :** "
        f"{SEUIL_MATCHING_PROBABLE:.0%}"
    )


# ============================================================
# MESSAGE FINAL
# ============================================================

if not resultat.empty:

    st.success(
        f"✅ Comparaison terminée : "
        f"**{nombre_produits} groupes de produits** "
        f"comparés auprès de "
        f"**{nombre_fournisseurs} fournisseurs**."
    )

else:

    st.warning(
        "⚠️ Analyse terminée, mais aucun meilleur prix "
        "n'a pu être déterminé."
    )