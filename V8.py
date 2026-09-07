import streamlit as st
import pandas as pd
import numpy as np
import re
import unicodedata
import io
import pdfplumber
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_DISPONIBLE = True
except ImportError:
    RAPIDFUZZ_DISPONIBLE = False


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="OptiMarge - Comparateur Instantané",
    page_icon="🛒",
    layout="wide",
)

SEUIL_MATCHING_FORT = 0.92
SEUIL_MATCHING_PROBABLE = 0.86

FACTEURS_CONVERSION = {
    "KG": 1.0,
    "LB": 0.45359237,
    "OZ": 0.028349523125,
    "L": 1.0,
    "ML": 0.001,
    "CL": 0.01,
    "GAL": 3.785411784,
    "U": 1.0,
}


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1600px;
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        margin-bottom: 0.1rem;
    }

    .small-muted {
        color: #6b7280;
        font-size: 0.88rem;
    }

    .provider-card {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 12px;
        background: #ffffff;
    }

    .warning-box {
        border-left: 4px solid #f59e0b;
        padding: 10px 14px;
        background: #fffbeb;
        border-radius: 6px;
        margin: 8px 0;
    }

    .success-box {
        border-left: 4px solid #10b981;
        padding: 10px 14px;
        background: #ecfdf5;
        border-radius: 6px;
        margin: 8px 0;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.45rem;
    }

    @media (max-width: 600px) {
        .main-title {
            font-size: 1.6rem;
        }

        .block-container {
            padding-left: 0.7rem;
            padding-right: 0.7rem;
        }

        div.stButton > button,
        div.stDownloadButton > button {
            width: 100%;
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
# CONFIGURATION RÉGIONS
# ============================================================

REGIONS = {
    "France 🇫🇷": {
        "pays": "FR",
        "devise": "EUR",
        "symbole": "€",
        "mots_produit": [
            "produit",
            "article",
            "designation",
            "désignation",
            "libelle",
            "libellé",
            "description",
            "nom produit",
            "nom article",
            "item",
            "product",
            "product name",
            "description produit",
            "sku",
            "référence",
            "reference",
            "ref",
        ],
        "mots_prix": [
            "prix",
            "tarif",
            "prix unitaire",
            "prix ht",
            "prix htva",
            "prix achat",
            "prix fournisseur",
            "tarif fournisseur",
            "montant",
            "cout",
            "coût",
            "purchase price",
            "unit price",
            "price",
            "price ht",
            "net price",
            "prix/kg",
            "prix / kg",
            "prix au kg",
            "prix par kg",
            "prix/kilo",
            "prix/l",
            "prix / l",
            "prix au litre",
            "prix par litre",
            "€/kg",
            "€/l",
        ],
    },
    "Canada 🇨🇦": {
        "pays": "CA",
        "devise": "CAD",
        "symbole": "CA$",
        "mots_produit": [
            "produit",
            "article",
            "designation",
            "désignation",
            "libelle",
            "libellé",
            "description",
            "nom produit",
            "nom article",
            "item",
            "product",
            "product name",
            "description produit",
            "sku",
            "code",
            "item number",
            "product description",
        ],
        "mots_prix": [
            "prix",
            "tarif",
            "prix unitaire",
            "prix ht",
            "prix achat",
            "prix fournisseur",
            "tarif fournisseur",
            "montant",
            "cout",
            "coût",
            "purchase price",
            "unit price",
            "price",
            "net price",
            "cost",
            "$/kg",
            "$ / kg",
            "$/lb",
            "$ / lb",
            "$/l",
            "$ / l",
            "$/gal",
            "$ / gal",
            "prix au kg",
            "prix par kg",
            "prix au lb",
            "prix par lb",
            "prix au litre",
            "prix par litre",
        ],
    },
}


# ============================================================
# OUTILS TEXTE
# ============================================================

def normaliser_texte(texte):
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
    texte = re.sub(r"\s+", " ", texte)

    return texte.strip()


def normaliser_decimal(texte):
    """
    Transforme les décimales françaises :
        1,5 -> 1.5
        0,5 -> 0.5
        1 234,50 -> 1234.50
    """
    if texte is None:
        return ""

    texte = str(texte).strip()
    texte = texte.replace("\xa0", " ")
    texte = texte.replace(" ", "")

    # 1.234,56 -> 1234.56
    if re.search(r"\d+\.\d{3},\d+", texte):
        texte = texte.replace(".", "")
        texte = texte.replace(",", ".")
    else:
        texte = texte.replace(",", ".")

    return texte


def cle_produit_fuzzy(nom):
    texte = normaliser_texte(nom)

    texte = re.sub(r"[^a-z0-9]+", " ", texte)

    mots_a_supprimer = {
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

    tokens = [
        token
        for token in texte.split()
        if token not in mots_a_supprimer
    ]

    resultat = " ".join(tokens).upper()

    resultat = re.sub(
        r"^JUS\s+D\s+",
        "JUS DE ",
        resultat,
    )

    resultat = re.sub(
        r"^JUS\s+DE\s+",
        "JUS DE ",
        resultat,
    )

    return resultat.strip()


def token_principal(cle):
    if not cle:
        return ""

    return cle.split()[0]


# ============================================================
# NORMALISATION DES COLONNES
# ============================================================

def normaliser_noms_colonnes(df):
    """
    Corrige notamment :
      Unnamed: 0
      Unnamed: 1
      colonnes vides
      doublons de noms
    """
    df = df.copy()

    nouvelles = []
    compteurs = {}

    for i, colonne in enumerate(df.columns):
        nom = str(colonne).strip()

        if (
            not nom
            or nom.lower().startswith("unnamed:")
            or nom.lower() == "nan"
        ):
            nom = f"Colonne_{i + 1}"

        base = nom

        compteurs[base] = compteurs.get(base, 0) + 1

        if compteurs[base] > 1:
            nom = f"{base}_{compteurs[base]}"

        nouvelles.append(nom)

    df.columns = nouvelles

    return df


# ============================================================
# DÉTECTION DES COLONNES
# ============================================================

def score_colonne(nom_colonne, mots):
    nom = normaliser_texte(nom_colonne)

    meilleur = 0

    for mot in mots:
        mot_norm = normaliser_texte(mot)

        if nom == mot_norm:
            meilleur = max(meilleur, 100)

        elif mot_norm in nom:
            meilleur = max(meilleur, 80)

        else:
            ratio = SequenceMatcher(
                None,
                nom,
                mot_norm,
            ).ratio()

            meilleur = max(
                meilleur,
                int(ratio * 60),
            )

    return meilleur


def detecter_colonne_produit(df, region):
    scores = {
        colonne: score_colonne(
            colonne,
            region["mots_produit"],
        )
        for colonne in df.columns
    }

    if not scores:
        return None

    return max(
        scores,
        key=scores.get,
    )


def detecter_colonne_prix(df, region):
    scores = {
        colonne: score_colonne(
            colonne,
            region["mots_prix"],
        )
        for colonne in df.columns
    }

    if not scores:
        return None

    meilleur = max(
        scores,
        key=scores.get,
    )

    if scores[meilleur] < 25:
        return None

    return meilleur


# ============================================================
# PRIX
# ============================================================

def convertir_prix_international(valeur, pays):
    if valeur is None or pd.isna(valeur):
        return np.nan

    if isinstance(valeur, (int, float, np.integer, np.floating)):
        valeur = float(valeur)

        if valeur < 0:
            return np.nan

        return valeur

    texte = str(valeur).strip()

    if not texte:
        return np.nan

    texte = texte.replace("\xa0", " ")

    # Retirer devises et textes courants
    texte = re.sub(
        r"(EUR|€|EURO|EUROS|CAD|CA\$|C\$|USD|US\$|\$)",
        "",
        texte,
        flags=re.IGNORECASE,
    )

    texte = texte.strip()

    # Garder uniquement chiffres, séparateurs et signe
    texte = re.sub(
        r"[^0-9,\.\-\s]",
        "",
        texte,
    )

    texte = texte.replace(" ", "")

    if not texte:
        return np.nan

    # Gestion robuste des séparateurs
    if "," in texte and "." in texte:
        derniere_virgule = texte.rfind(",")
        dernier_point = texte.rfind(".")

        if derniere_virgule > dernier_point:
            texte = texte.replace(".", "")
            texte = texte.replace(",", ".")
        else:
            texte = texte.replace(",", "")

    elif "," in texte:
        parties = texte.split(",")

        if len(parties) == 2:
            if len(parties[1]) <= 2:
                texte = texte.replace(",", ".")
            else:
                texte = texte.replace(",", "")
        else:
            texte = texte.replace(",", "")

    elif texte.count(".") > 1:
        morceaux = texte.split(".")

        if len(morceaux[-1]) <= 2:
            texte = "".join(morceaux[:-1]) + "." + morceaux[-1]
        else:
            texte = "".join(morceaux)

    try:
        prix = float(texte)

        if prix < 0:
            return np.nan

        return prix

    except Exception:
        return np.nan


def detecter_base_prix_colonne(nom_colonne):
    texte = normaliser_texte(nom_colonne)

    # Bases directes
    if re.search(r"(^|[^a-z])(kg|kilo|kilos)([^a-z]|$)", texte):
        if (
            "prix au kg" in texte
            or "prix par kg" in texte
            or "/kg" in texte
            or "$/kg" in texte
            or "€/kg" in texte
        ):
            return "KG"

    if re.search(r"(^|[^a-z])(lb|lbs|livre|livres)([^a-z]|$)", texte):
        if (
            "/lb" in texte
            or "$/lb" in texte
            or "prix au lb" in texte
            or "prix par lb" in texte
        ):
            return "LB"

    if (
        "/l" in texte
        or "$/l" in texte
        or "€/l" in texte
        or "prix au litre" in texte
        or "prix par litre" in texte
        or "prix au l" in texte
    ):
        return "L"

    if (
        "/ml" in texte
        or "$/ml" in texte
        or "prix au ml" in texte
    ):
        return "ML"

    if (
        "/gal" in texte
        or "$/gal" in texte
        or "prix au gallon" in texte
    ):
        return "GAL"

    if (
        "/u" in texte
        or "par unite" in texte
        or "par unité" in texte
        or "prix unitaire" in texte
    ):
        return "U"

    if "prix au kilo" in texte or "prix par kilo" in texte:
        return "KG"

    if "prix au kg" in texte or "prix par kg" in texte:
        return "KG"

    return None


def detecter_base_prix_valeur(valeur, pays):
    if valeur is None or pd.isna(valeur):
        return None

    texte = normaliser_texte(valeur)

    if not texte:
        return None

    if re.search(r"(€/kg|€ / kg|eur/kg|eur / kg|\$/kg|\$ / kg|ca\$/kg)", texte):
        return "KG"

    if re.search(r"(\$/lb|\$ / lb|ca\$/lb|prix au lb|prix par lb)", texte):
        return "LB"

    if re.search(r"(€/l|€ / l|eur/l|\$/l|\$ / l|ca\$/l)", texte):
        return "L"

    if re.search(r"(\$/ml|\$ / ml|ca\$/ml)", texte):
        return "ML"

    if re.search(r"(\$/gal|\$ / gal|ca\$/gal)", texte):
        return "GAL"

    return None


def convertir_prix_direct(prix, unite_source):
    if pd.isna(prix) or prix < 0:
        return np.nan, None

    if not unite_source:
        return np.nan, None

    unite = str(unite_source).upper().strip()

    if unite == "KG":
        return float(prix), "KG"

    if unite == "LB":
        return float(prix) / 0.45359237, "KG"

    if unite == "OZ":
        return float(prix) / 0.028349523125, "KG"

    if unite == "L":
        return float(prix), "L"

    if unite == "ML":
        return float(prix) * 1000, "L"

    if unite == "CL":
        return float(prix) * 100, "L"

    if unite == "GAL":
        return float(prix) / 3.785411784, "L"

    if unite == "U":
        return float(prix), "U"

    return np.nan, None


def calculer_prix_comparable(prix, quantite, unite):
    if (
        pd.isna(prix)
        or pd.isna(quantite)
        or not unite
        or quantite <= 0
    ):
        return np.nan

    return prix / quantite


def format_prix_comparable(prix, unite, symbole):
    if pd.isna(prix):
        return "—"

    if unite == "KG":
        suffixe = f"{symbole}/kg"
    elif unite == "L":
        suffixe = f"{symbole}/L"
    elif unite == "U":
        suffixe = f"{symbole}/u"
    else:
        suffixe = f"{symbole}/{str(unite).lower()}"

    return f"{prix:.2f} {suffixe}"


# ============================================================
# CONDITIONNEMENT
# ============================================================

REGEX_MULTIPACK = re.compile(
    r"""
    (?P<q1>\d+(?:[.,]\d+)?)
    \s*[xX×]\s*
    (?P<q2>\d+(?:[.,]\d+)?)
    \s*
    (?P<unite>kg|g|lb|lbs|oz|ml|cl|l|litre|litres|liter|liters|gal)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

REGEX_FRACTION = re.compile(
    r"""
    (?P<q1>\d+(?:[.,]\d+)?)
    \s*/\s*
    (?P<q2>\d+(?:[.,]\d+)?)
    \s*
    (?P<unite>kg|g|lb|lbs|oz|ml|cl|l|litre|litres|liter|liters|gal)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

REGEX_SIMPLE = re.compile(
    r"""
    (?P<q>\d+(?:[.,]\d+)?)
    \s*
    (?P<unite>
        kg|g|lb|lbs|oz|
        ml|cl|l|
        litre|litres|liter|liters|
        fl\s*oz|
        gal
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

REGEX_PACK = re.compile(
    r"""
    (?:
        pack\s*(?:de|of)?\s*
        |case\s*(?:of|de)?\s*
        |caisse\s*(?:de|of)?\s*
    )
    (?P<q>\d+(?:[.,]\d+)?)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

REGEX_PACK_REVERSE = re.compile(
    r"""
    (?P<q>\d+(?:[.,]\d+)?)
    \s*
    (?:pack|packs|case|cases|caisse|caisses)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

REGEX_UNITES = re.compile(
    r"""
    (?P<q>\d+(?:[.,]\d+)?)
    \s*
    (?:pcs?|pieces?|pièces?|units?|unites?|unités?)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

REGEX_CONTENANTS = re.compile(
    r"""
    (?P<q>\d+(?:[.,]\d+)?)
    \s*
    (?:bottles?|bouteilles?|cans?|canettes?|boxes?|boites?|boîtes?|
       bags?|sacs?|jars?|pots?)
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _convertir_quantite(quantite, unite):
    if quantite is None or pd.isna(quantite):
        return np.nan, None

    try:
        quantite = float(
            normaliser_decimal(quantite)
        )
    except Exception:
        return np.nan, None

    unite = normaliser_texte(unite)

    if unite in {"g", "gramme", "grammes", "gram", "grams"}:
        return quantite / 1000, "KG"

    if unite in {"kg", "kilo", "kilos", "kilogramme", "kilogrammes", "kilogram", "kilograms"}:
        return quantite, "KG"

    if unite in {"lb", "lbs", "livre", "livres", "pound", "pounds"}:
        return quantite * 0.45359237, "KG"

    if unite in {"oz", "once", "onces", "ounce", "ounces"}:
        return quantite * 0.028349523125, "KG"

    if unite in {"ml", "millilitre", "millilitres", "milliliter", "milliliters"}:
        return quantite / 1000, "L"

    # CORRECTION IMPORTANTE :
    # 1 cl = 0,01 L
    if unite in {"cl", "centilitre", "centilitres"}:
        return quantite / 100, "L"

    if unite in {
        "l",
        "litre",
        "litres",
        "liter",
        "liters",
    }:
        return quantite, "L"

    if unite in {"fl oz", "floz"}:
        return quantite * 0.0295735295625, "L"

    if unite in {"gal", "gallon", "gallons"}:
        return quantite * 3.785411784, "L"

    return quantite, "U"


def extraire_conditionnement(libelle):
    """
    Retourne le conditionnement détecté.

    Exemples :
        12 x 355 ml
        6 x 1,5 L
        0,5 kg
        1,25 L
        24 bottles
        pack de 6
        12/750 ml
    """

    resultat = {
        "conditionnement_original": "",
        "quantite_totale": np.nan,
        "unite_standard": None,
        "conditionnement_detecte": False,
        "texte_conditionnement": "",
        "type_conditionnement": "inconnu",
    }

    if libelle is None or pd.isna(libelle):
        return resultat

    texte = str(libelle)

    # --------------------------------------------------------
    # MULTIPACK
    # --------------------------------------------------------

    match = REGEX_MULTIPACK.search(texte)

    if match:
        q1 = float(
            normaliser_decimal(match.group("q1"))
        )
        q2 = float(
            normaliser_decimal(match.group("q2"))
        )

        unite = match.group("unite")

        q2_normalisee, unite_standard = _convertir_quantite(
            q2,
            unite,
        )

        quantite_totale = q1 * q2_normalisee

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": quantite_totale,
                "unite_standard": unite_standard,
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "multipack",
            }
        )

        return resultat

    # --------------------------------------------------------
    # FRACTION
    # --------------------------------------------------------

    match = REGEX_FRACTION.search(texte)

    if match:
        q1 = float(
            normaliser_decimal(match.group("q1"))
        )
        q2 = float(
            normaliser_decimal(match.group("q2"))
        )

        unite = match.group("unite")

        q2_normalisee, unite_standard = _convertir_quantite(
            q2,
            unite,
        )

        quantite_totale = q1 * q2_normalisee

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": quantite_totale,
                "unite_standard": unite_standard,
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "fraction",
            }
        )

        return resultat

    # --------------------------------------------------------
    # SIMPLE
    # --------------------------------------------------------

    match = REGEX_SIMPLE.search(texte)

    if match:
        q = float(
            normaliser_decimal(match.group("q"))
        )

        unite = match.group("unite")

        quantite_normalisee, unite_standard = _convertir_quantite(
            q,
            unite,
        )

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": quantite_normalisee,
                "unite_standard": unite_standard,
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "simple",
            }
        )

        return resultat

    # --------------------------------------------------------
    # PACK DE X
    # --------------------------------------------------------

    match = REGEX_PACK.search(texte)

    if match:
        q = float(
            normaliser_decimal(match.group("q"))
        )

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": q,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "pack",
            }
        )

        return resultat

    # --------------------------------------------------------
    # X PACK
    # --------------------------------------------------------

    match = REGEX_PACK_REVERSE.search(texte)

    if match:
        q = float(
            normaliser_decimal(match.group("q"))
        )

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": q,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "pack",
            }
        )

        return resultat

    # --------------------------------------------------------
    # UNITÉS
    # --------------------------------------------------------

    match = REGEX_UNITES.search(texte)

    if match:
        q = float(
            normaliser_decimal(match.group("q"))
        )

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": q,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "unites",
            }
        )

        return resultat

    # --------------------------------------------------------
    # CONTENANTS
    # --------------------------------------------------------

    match = REGEX_CONTENANTS.search(texte)

    if match:
        q = float(
            normaliser_decimal(match.group("q"))
        )

        texte_match = match.group(0)

        resultat.update(
            {
                "conditionnement_original": texte_match,
                "quantite_totale": q,
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": texte_match,
                "type_conditionnement": "contenants",
            }
        )

        return resultat

    return resultat


# ============================================================
# EXTRACTION VECTORISÉE DU CONDITIONNEMENT
# ============================================================

def extraire_conditionnements_vectorises(series):
    """
    Version optimisée :
    évite d'utiliser iterrows() sur le DataFrame.

    Les regex Pandas sont utilisées pour détecter les formats
    les plus courants en bloc.
    """

    texte = series.fillna("").astype(str)

    resultat = pd.DataFrame(
        index=series.index
    )

    resultat["conditionnement_original"] = ""
    resultat["quantite_totale"] = np.nan
    resultat["unite_standard"] = None
    resultat["conditionnement_detecte"] = False
    resultat["texte_conditionnement"] = ""
    resultat["type_conditionnement"] = "inconnu"

    # --------------------------------------------------------
    # MULTIPACK
    # --------------------------------------------------------

    extrait = texte.str.extract(
        REGEX_MULTIPACK.pattern,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    masque = extrait["q1"].notna()

    if masque.any():
        q1 = pd.to_numeric(
            extrait.loc[masque, "q1"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        q2 = pd.to_numeric(
            extrait.loc[masque, "q2"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        unites = extrait.loc[masque, "unite"].str.lower()

        q2_normalisee = np.select(
            [
                unites.isin(["g"]),
                unites.isin(["kg"]),
                unites.isin(["lb", "lbs"]),
                unites.isin(["oz"]),
                unites.isin(["ml"]),
                unites.isin(["cl"]),
                unites.isin(["l", "litre", "litres", "liter", "liters"]),
                unites.isin(["gal"]),
            ],
            [
                q2 / 1000,
                q2,
                q2 * 0.45359237,
                q2 * 0.028349523125,
                q2 / 1000,
                q2 / 100,
                q2,
                q2 * 3.785411784,
            ],
            default=np.nan,
        )

        unite_standard = np.select(
            [
                unites.isin(["g", "kg", "lb", "lbs", "oz"]),
                unites.isin(["ml", "cl", "l", "litre", "litres", "liter", "liters", "gal"]),
            ],
            [
                "KG",
                "L",
            ],
            default="U",
        )

        resultat.loc[masque, "quantite_totale"] = (
            q1 * q2_normalisee
        )

        resultat.loc[masque, "unite_standard"] = unite_standard

        # Extraction exacte du texte
        resultat.loc[masque, "texte_conditionnement"] = (
            texte.loc[masque]
            .str.extract(
                f"({REGEX_MULTIPACK.pattern})",
                flags=re.IGNORECASE | re.VERBOSE,
                expand=False,
            )
            .fillna("")
        )

        resultat.loc[masque, "conditionnement_original"] = (
            resultat.loc[masque, "texte_conditionnement"]
        )

        resultat.loc[masque, "conditionnement_detecte"] = True
        resultat.loc[masque, "type_conditionnement"] = "multipack"

    # --------------------------------------------------------
    # SIMPLE
    # --------------------------------------------------------

    restant = ~resultat["conditionnement_detecte"]

    extrait = texte.loc[restant].str.extract(
        REGEX_SIMPLE.pattern,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    masque_simple = extrait["q"].notna()

    if masque_simple.any():
        index_simple = extrait.index[masque_simple]

        q = pd.to_numeric(
            extrait.loc[index_simple, "q"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        unites = extrait.loc[index_simple, "unite"].str.lower()

        quantite_normalisee = np.select(
            [
                unites.isin(["g"]),
                unites.isin(["kg"]),
                unites.isin(["lb", "lbs"]),
                unites.isin(["oz"]),
                unites.isin(["ml"]),
                unites.isin(["cl"]),
                unites.isin(["l", "litre", "litres", "liter", "liters"]),
                unites.isin(["fl oz"]),
                unites.isin(["gal"]),
            ],
            [
                q / 1000,
                q,
                q * 0.45359237,
                q * 0.028349523125,
                q / 1000,
                q / 100,
                q,
                q * 0.0295735295625,
                q * 3.785411784,
            ],
            default=np.nan,
        )

        unite_standard = np.select(
            [
                unites.isin(["g", "kg", "lb", "lbs", "oz"]),
                unites.isin(
                    [
                        "ml",
                        "cl",
                        "l",
                        "litre",
                        "litres",
                        "liter",
                        "liters",
                        "fl oz",
                        "gal",
                    ]
                ),
            ],
            [
                "KG",
                "L",
            ],
            default="U",
        )

        resultat.loc[index_simple, "quantite_totale"] = (
            quantite_normalisee
        )

        resultat.loc[index_simple, "unite_standard"] = (
            unite_standard
        )

        textes_matches = (
            texte.loc[index_simple]
            .str.extract(
                f"({REGEX_SIMPLE.pattern})",
                flags=re.IGNORECASE | re.VERBOSE,
                expand=False,
            )
            .fillna("")
        )

        resultat.loc[index_simple, "texte_conditionnement"] = (
            textes_matches
        )

        resultat.loc[index_simple, "conditionnement_original"] = (
            textes_matches
        )

        resultat.loc[index_simple, "conditionnement_detecte"] = True
        resultat.loc[index_simple, "type_conditionnement"] = "simple"

    # --------------------------------------------------------
    # PACK
    # --------------------------------------------------------

    restant = ~resultat["conditionnement_detecte"]

    extrait = texte.loc[restant].str.extract(
        REGEX_PACK.pattern,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    masque_pack = extrait["q"].notna()

    if masque_pack.any():
        index_pack = extrait.index[masque_pack]

        q = pd.to_numeric(
            extrait.loc[index_pack, "q"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        textes_matches = (
            texte.loc[index_pack]
            .str.extract(
                f"({REGEX_PACK.pattern})",
                flags=re.IGNORECASE | re.VERBOSE,
                expand=False,
            )
            .fillna("")
        )

        resultat.loc[index_pack, "quantite_totale"] = q
        resultat.loc[index_pack, "unite_standard"] = "U"
        resultat.loc[index_pack, "texte_conditionnement"] = textes_matches
        resultat.loc[index_pack, "conditionnement_original"] = textes_matches
        resultat.loc[index_pack, "conditionnement_detecte"] = True
        resultat.loc[index_pack, "type_conditionnement"] = "pack"

    # --------------------------------------------------------
    # X PACK
    # --------------------------------------------------------

    restant = ~resultat["conditionnement_detecte"]

    extrait = texte.loc[restant].str.extract(
        REGEX_PACK_REVERSE.pattern,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    masque_pack_reverse = extrait["q"].notna()

    if masque_pack_reverse.any():
        index_pack = extrait.index[masque_pack_reverse]

        q = pd.to_numeric(
            extrait.loc[index_pack, "q"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        textes_matches = (
            texte.loc[index_pack]
            .str.extract(
                f"({REGEX_PACK_REVERSE.pattern})",
                flags=re.IGNORECASE | re.VERBOSE,
                expand=False,
            )
            .fillna("")
        )

        resultat.loc[index_pack, "quantite_totale"] = q
        resultat.loc[index_pack, "unite_standard"] = "U"
        resultat.loc[index_pack, "texte_conditionnement"] = textes_matches
        resultat.loc[index_pack, "conditionnement_original"] = textes_matches
        resultat.loc[index_pack, "conditionnement_detecte"] = True
        resultat.loc[index_pack, "type_conditionnement"] = "pack"

    # --------------------------------------------------------
    # UNITÉS
    # --------------------------------------------------------

    restant = ~resultat["conditionnement_detecte"]

    extrait = texte.loc[restant].str.extract(
        REGEX_UNITES.pattern,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    masque_unites = extrait["q"].notna()

    if masque_unites.any():
        index_unites = extrait.index[masque_unites]

        q = pd.to_numeric(
            extrait.loc[index_unites, "q"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        textes_matches = (
            texte.loc[index_unites]
            .str.extract(
                f"({REGEX_UNITES.pattern})",
                flags=re.IGNORECASE | re.VERBOSE,
                expand=False,
            )
            .fillna("")
        )

        resultat.loc[index_unites, "quantite_totale"] = q
        resultat.loc[index_unites, "unite_standard"] = "U"
        resultat.loc[index_unites, "texte_conditionnement"] = textes_matches
        resultat.loc[index_unites, "conditionnement_original"] = textes_matches
        resultat.loc[index_unites, "conditionnement_detecte"] = True
        resultat.loc[index_unites, "type_conditionnement"] = "unites"

    # --------------------------------------------------------
    # CONTENANTS
    # --------------------------------------------------------

    restant = ~resultat["conditionnement_detecte"]

    extrait = texte.loc[restant].str.extract(
        REGEX_CONTENANTS.pattern,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    masque_contenants = extrait["q"].notna()

    if masque_contenants.any():
        index_contenants = extrait.index[masque_contenants]

        q = pd.to_numeric(
            extrait.loc[index_contenants, "q"].str.replace(
                ",",
                ".",
                regex=False,
            ),
            errors="coerce",
        )

        textes_matches = (
            texte.loc[index_contenants]
            .str.extract(
                f"({REGEX_CONTENANTS.pattern})",
                flags=re.IGNORECASE | re.VERBOSE,
                expand=False,
            )
            .fillna("")
        )

        resultat.loc[index_contenants, "quantite_totale"] = q
        resultat.loc[index_contenants, "unite_standard"] = "U"
        resultat.loc[index_contenants, "texte_conditionnement"] = textes_matches
        resultat.loc[index_contenants, "conditionnement_original"] = textes_matches
        resultat.loc[index_contenants, "conditionnement_detecte"] = True
        resultat.loc[index_contenants, "type_conditionnement"] = "contenants"

    return resultat


def extraire_produit_base_vectorise(series, conditionnements):
    """
    Retire uniquement le texte correspondant au conditionnement.
    """
    produits = series.fillna("").astype(str).copy()

    motifs = (
        conditionnements["texte_conditionnement"]
        .fillna("")
        .astype(str)
    )

    masque = (
        conditionnements["conditionnement_detecte"]
        & motifs.ne("")
    )

    produits.loc[masque] = [
        re.sub(
            re.escape(motif),
            "",
            produit,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        for produit, motif in zip(
            produits.loc[masque],
            motifs.loc[masque],
        )
    ]

    produits = (
        produits
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    return produits


# ============================================================
# MATCHING
# ============================================================

def score_matching(cle_a, cle_b):
    if not cle_a or not cle_b:
        return 0.0

    if cle_a == cle_b:
        return 1.0

    if RAPIDFUZZ_DISPONIBLE:
        score_global = fuzz.ratio(
            cle_a,
            cle_b,
        ) / 100.0

        score_tokens = fuzz.token_set_ratio(
            cle_a,
            cle_b,
        ) / 100.0

        # Le ratio global reste majoritaire afin d'éviter
        # qu'un nom court contenu dans un nom long obtienne
        # artificiellement un score trop élevé.
        return (
            0.60 * score_global
            + 0.40 * score_tokens
        )

    ratio_global = SequenceMatcher(
        None,
        cle_a,
        cle_b,
    ).ratio()

    tokens_a = set(cle_a.split())
    tokens_b = set(cle_b.split())

    if not tokens_a or not tokens_b:
        ratio_tokens = 0.0
    else:
        ratio_tokens = (
            len(tokens_a & tokens_b)
            / len(tokens_a | tokens_b)
        )

    return (
        0.60 * ratio_global
        + 0.40 * ratio_tokens
    )


def trouver_meilleur_groupe(
    cle,
    unite,
    groupes,
    index_exact,
    index_unite_token,
    index_unite,
):
    # ============================================================
    # SÉCURISATION DE LA CLÉ PRODUIT
    # ============================================================

    if cle is None:
        return None, 0.0, "nouveau"

    try:
        if pd.isna(cle):
            return None, 0.0, "nouveau"
    except (TypeError, ValueError):
        pass

    cle = str(cle).strip()

    if not cle:
        return None, 0.0, "nouveau"

    # ============================================================
    # SÉCURISATION DE L'UNITÉ
    # ============================================================

    if unite is None:
        unite = "U"
    else:
        try:
            if pd.isna(unite):
                unite = "U"
        except (TypeError, ValueError):
            pass

    unite = str(unite).strip()

    if not unite:
        unite = "U"

    # ============================================================
    # FONCTION INTERNE :
    # transforme un ID de groupe en dictionnaire de groupe
    # ============================================================

    def obtenir_groupe(candidat):
        # Cas 1 : le candidat est déjà un dictionnaire
        if isinstance(candidat, dict):
            return candidat

        # Cas 2 : le candidat est un ID entier
        if isinstance(candidat, (int, np.integer)):
            try:
                # groupes est généralement une liste
                return groupes[int(candidat)]
            except (IndexError, KeyError, TypeError):
                pass

            # Au cas où groupes serait un dictionnaire
            try:
                return groupes[candidat]
            except (KeyError, TypeError):
                pass

        return None

    # ============================================================
    # CORRESPONDANCE EXACTE
    # ============================================================

    cle_exacte = (unite, cle)

    if cle_exacte in index_exact:
        candidat = index_exact[cle_exacte]

        groupe = obtenir_groupe(candidat)

        if groupe is not None:
            return groupe, 1.0, "exact"

    # ============================================================
    # PREMIER TOKEN
    # ============================================================

    tokens = cle.split()

    if not tokens:
        return None, 0.0, "nouveau"

    premier_token = tokens[0]

    candidats = index_unite_token.get(
        (unite, premier_token),
        [],
    )

    # ============================================================
    # FALLBACK : TOUS LES GROUPES DE LA MÊME UNITÉ
    # ============================================================

    if not candidats:
        candidats = index_unite.get(
            unite,
            [],
        )

    # ============================================================
    # FALLBACK : TOKEN COMMUN
    # ============================================================

    if not candidats:
        tokens_cle = set(tokens)

        for i, groupe in enumerate(groupes):

            if isinstance(groupe, dict):
                unite_groupe = groupe.get(
                    "Unite_Comparaison",
                    "U",
                )

                if unite_groupe != unite:
                    continue

                cle_groupe = groupe.get(
                    "Cle_Produit"
                )

            else:
                continue

            if cle_groupe is None:
                continue

            try:
                if pd.isna(cle_groupe):
                    continue
            except (TypeError, ValueError):
                pass

            tokens_groupe = set(
                str(cle_groupe).split()
            )

            if tokens_cle & tokens_groupe:
                candidats.append(i)

    # ============================================================
    # AUCUN CANDIDAT
    # ============================================================

    if not candidats:
        return None, 0.0, "nouveau"

    # ============================================================
    # CONVERTIR LES IDs EN GROUPES
    # ============================================================

    groupes_candidats = []

    for candidat in candidats:
        groupe = obtenir_groupe(candidat)

        if groupe is not None:
            groupes_candidats.append(groupe)

    if not groupes_candidats:
        return None, 0.0, "nouveau"

    # ============================================================
    # RAPIDFUZZ
    # ============================================================

    meilleur_groupe = None
    meilleur_score = 0.0

    if RAPIDFUZZ_DISPONIBLE:

        cles_candidats = []

        groupes_valides = []

        for groupe in groupes_candidats:

            cle_groupe = groupe.get(
                "Cle_Produit"
            )

            if cle_groupe is None:
                continue

            try:
                if pd.isna(cle_groupe):
                    continue
            except (TypeError, ValueError):
                continue

            cle_groupe = str(cle_groupe).strip()

            if not cle_groupe:
                continue

            cles_candidats.append(cle_groupe)
            groupes_valides.append(groupe)

        if cles_candidats:

            resultat = process.extractOne(
                cle,
                cles_candidats,
                scorer=fuzz.token_set_ratio,
            )

            if resultat:

                _, _, index_candidat = resultat

                candidat = groupes_valides[index_candidat]

                cle_candidat = str(
                    candidat.get(
                        "Cle_Produit",
                        "",
                    )
                )

                # IMPORTANT :
                # on utilise notre score pondéré final,
                # et non directement token_set_ratio.
                score = score_matching(
                    cle,
                    cle_candidat,
                )

                meilleur_groupe = candidat
                meilleur_score = score

    # ============================================================
    # FALLBACK SANS RAPIDFUZZ
    # ============================================================

    else:

        for candidat in groupes_candidats:

            cle_candidat = candidat.get(
                "Cle_Produit"
            )

            if cle_candidat is None:
                continue

            try:
                if pd.isna(cle_candidat):
                    continue
            except (TypeError, ValueError):
                continue

            score = score_matching(
                cle,
                str(cle_candidat),
            )

            if score > meilleur_score:
                meilleur_score = score
                meilleur_groupe = candidat

    # ============================================================
    # CLASSIFICATION
    # ============================================================

    if meilleur_groupe is None:
        return None, 0.0, "nouveau"

    if meilleur_score >= SEUIL_MATCHING_FORT:
        statut = "fort"

    elif meilleur_score >= SEUIL_MATCHING_PROBABLE:
        statut = "probable"

    else:
        return None, meilleur_score, "nouveau"

    return (
        meilleur_groupe,
        meilleur_score,
        statut,
    )


def appliquer_matching(df):
    travail = df.copy()

    groupes = {}
    index_exact = {}
    index_unite_token = {}
    index_unite = {}

    groupes_produit = []
    scores = []
    types = []

    prochain_gid = 0

    for ligne in travail.itertuples(index=False):
        cle = getattr(ligne, "Cle_Produit")
        unite = getattr(ligne, "Unite_Etalon")

        if pd.isna(unite) or not unite:
            unite = "U"

        gid, score, type_match = trouver_meilleur_groupe(
            cle,
            unite,
            groupes,
            index_exact,
            index_unite_token,
            index_unite,
        )

        if gid is None:
            gid = prochain_gid
            prochain_gid += 1

            groupes[gid] = {
                "id": gid,
                "cle": cle,
                "nom": getattr(ligne, "Produit_Affichage"),
                "unite_etalon": unite,
            }

            index_exact[
                (unite, cle)
            ] = gid

            index_unite.setdefault(
                unite,
                set(),
            ).add(gid)

            for token in set(cle.split()):
                index_unite_token.setdefault(
                    (unite, token),
                    set(),
                ).add(gid)

        groupes_produit.append(gid)
        scores.append(score)
        types.append(type_match)

    travail["Groupe_Produit"] = groupes_produit
    travail["Score_Matching"] = scores
    travail["Type_Matching"] = types

    return travail, groupes


# ============================================================
# PRÉPARATION VECTORISÉE
# ============================================================

def preparer_donnees(
    df,
    nom_fournisseur,
    colonne_produit,
    colonne_prix,
    region,
):
    travail = normaliser_noms_colonnes(df)

    if colonne_produit not in travail.columns:
        raise ValueError(
            f"La colonne produit '{colonne_produit}' "
            f"n'existe plus après normalisation."
        )

    if colonne_prix not in travail.columns:
        raise ValueError(
            f"La colonne prix '{colonne_prix}' "
            f"n'existe plus après normalisation."
        )

    travail = travail.copy()

    # --------------------------------------------------------
    # PRODUIT
    # --------------------------------------------------------

    travail["Produit_Affichage"] = (
        travail[colonne_produit]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    travail["Cle_Produit_Brut"] = (
        travail["Produit_Affichage"]
        .map(cle_produit_fuzzy)
    )

    # --------------------------------------------------------
    # PRIX
    # --------------------------------------------------------

    travail["Prix_Brut"] = travail[colonne_prix]

    travail["Prix_Numerique"] = (
        travail["Prix_Brut"]
        .map(
            lambda x: convertir_prix_international(
                x,
                region["pays"],
            )
        )
    )

    travail["Base_Prix_Colonne"] = (
        detecter_base_prix_colonne(
            colonne_prix
        )
    )

    travail["Base_Prix_Valeur"] = (
        travail["Prix_Brut"]
        .map(
            lambda x: detecter_base_prix_valeur(
                x,
                region["pays"],
            )
        )
    )

    travail["Base_Prix"] = (
        travail["Base_Prix_Colonne"]
        .where(
            travail["Base_Prix_Colonne"].notna(),
            travail["Base_Prix_Valeur"],
        )
    )

    # --------------------------------------------------------
    # CONDITIONNEMENT
    # --------------------------------------------------------

    conditionnements = extraire_conditionnements_vectorises(
        travail["Produit_Affichage"]
    )

    travail["Conditionnement"] = (
        conditionnements[
            "conditionnement_original"
        ]
    )

    travail["Quantite_Normalisee"] = (
        conditionnements[
            "quantite_totale"
        ]
    )

    travail["Unite_Etalon"] = (
        conditionnements[
            "unite_standard"
        ]
    )

    travail["Conditionnement_Detecte"] = (
        conditionnements[
            "conditionnement_detecte"
        ]
    )

    travail["Type_Conditionnement"] = (
        conditionnements[
            "type_conditionnement"
        ]
    )

    # --------------------------------------------------------
    # PRODUIT SANS CONDITIONNEMENT
    # --------------------------------------------------------

    travail["Produit_Base"] = (
        extraire_produit_base_vectorise(
            travail["Produit_Affichage"],
            conditionnements,
        )
    )

    travail["Cle_Produit"] = (
        travail["Produit_Base"]
        .map(cle_produit_fuzzy)
    )

    # --------------------------------------------------------
    # PRIX COMPARABLE
    # --------------------------------------------------------

    # Prix déjà exprimé directement au kg/L/u
    masque_direct = (
        travail["Base_Prix"].isin(
            ["KG", "LB", "OZ", "L", "ML", "CL", "GAL", "U"]
        )
    )

    prix_direct = pd.Series(
        np.nan,
        index=travail.index,
        dtype=float,
    )

    unite_directe = pd.Series(
        None,
        index=travail.index,
        dtype=object,
    )

    # Conversion vectorisée par unité
    for unite_source in [
        "KG",
        "LB",
        "OZ",
        "L",
        "ML",
        "CL",
        "GAL",
        "U",
    ]:
        masque = (
            masque_direct
            & travail["Base_Prix"].eq(unite_source)
        )

        if not masque.any():
            continue

        if unite_source == "KG":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
            )
            unite_directe.loc[masque] = "KG"

        elif unite_source == "LB":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
                / 0.45359237
            )
            unite_directe.loc[masque] = "KG"

        elif unite_source == "OZ":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
                / 0.028349523125
            )
            unite_directe.loc[masque] = "KG"

        elif unite_source == "L":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
            )
            unite_directe.loc[masque] = "L"

        elif unite_source == "ML":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
                * 1000
            )
            unite_directe.loc[masque] = "L"

        elif unite_source == "CL":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
                * 100
            )
            unite_directe.loc[masque] = "L"

        elif unite_source == "GAL":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
                / 3.785411784
            )
            unite_directe.loc[masque] = "L"

        elif unite_source == "U":
            prix_direct.loc[masque] = (
                travail.loc[masque, "Prix_Numerique"]
            )
            unite_directe.loc[masque] = "U"

    # --------------------------------------------------------
    # PRIX DIRECT
    # --------------------------------------------------------

    travail["Prix_Comparable"] = prix_direct
    travail["Unite_Comparaison"] = unite_directe

    # --------------------------------------------------------
    # PRIX DE PACK / CONDITIONNEMENT
    # --------------------------------------------------------

    masque_pack = (
        ~masque_direct
        & travail["Quantite_Normalisee"].notna()
        & travail["Unite_Etalon"].notna()
        & travail["Prix_Numerique"].notna()
        & travail["Quantite_Normalisee"].gt(0)
    )

    travail.loc[
        masque_pack,
        "Prix_Comparable",
    ] = (
        travail.loc[
            masque_pack,
            "Prix_Numerique",
        ]
        / travail.loc[
            masque_pack,
            "Quantite_Normalisee",
        ]
    )

    travail.loc[
        masque_pack,
        "Unite_Comparaison",
    ] = travail.loc[
        masque_pack,
        "Unite_Etalon",
    ]

    # --------------------------------------------------------
    # FOURNISSEUR
    # --------------------------------------------------------

    travail["Fournisseur"] = nom_fournisseur

    # --------------------------------------------------------
    # NETTOYAGE
    # --------------------------------------------------------

    travail = travail[
        travail["Produit_Affichage"].str.strip().ne("")
    ]

    travail = travail[
        travail["Prix_Numerique"].notna()
    ]

    travail = travail[
        travail["Prix_Numerique"] >= 0
    ]

    travail = travail.drop_duplicates(
        subset=[
            "Produit_Base",
            "Prix_Comparable",
            "Conditionnement",
            "Fournisseur",
        ]
    )

    return travail.reset_index(drop=True)


# ============================================================
# LECTURE EXCEL
# ============================================================

@st.cache_data(show_spinner=False)
def lire_excel(contenu_bytes):
    dfs = {}

    diagnostic = {
        "type": "excel",
        "message": "",
    }

    try:
        with pd.ExcelFile(
            io.BytesIO(contenu_bytes)
        ) as excel:

            for feuille in excel.sheet_names:
                try:
                    df = excel.parse(feuille)

                    if df is not None and not df.empty:
                        dfs[feuille] = normaliser_noms_colonnes(
                            df
                        )

                except Exception:
                    continue

        if not dfs:
            diagnostic["message"] = (
                "Aucune feuille Excel exploitable "
                "n'a été trouvée."
            )

    except Exception as e:
        diagnostic["message"] = (
            f"Erreur lors de la lecture Excel : {e}"
        )

    return dfs, diagnostic


# ============================================================
# LECTURE CSV
# ============================================================

@st.cache_data(show_spinner=False)
def lire_csv(contenu_bytes):
    dfs = {}

    diagnostic = {
        "type": "csv",
        "message": "",
    }

    encodages = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    separateurs = [
        ";",
        ",",
    ]

    trouve = False

    for encodage in encodages:
        if trouve:
            break

        for separateur in separateurs:
            try:
                df = pd.read_csv(
                    io.BytesIO(contenu_bytes),
                    encoding=encodage,
                    sep=separateur,
                )

                if df is not None and not df.empty:
                    dfs["CSV"] = normaliser_noms_colonnes(
                        df
                    )
                    trouve = True
                    break

            except Exception:
                continue

    # Fallback autodetection
    if not trouve:
        try:
            df = pd.read_csv(
                io.BytesIO(contenu_bytes),
                encoding="utf-8-sig",
                sep=None,
                engine="python",
            )

            if df is not None and not df.empty:
                dfs["CSV"] = normaliser_noms_colonnes(
                    df
                )
                trouve = True

        except Exception:
            pass

    if not trouve:
        diagnostic["message"] = (
            "Impossible de lire le CSV. "
            "Vérifie l'encodage et le séparateur."
        )

    return dfs, diagnostic


# ============================================================
# PDF
# ============================================================

def nettoyer_table_pdf(table):
    if not table:
        return None

    lignes = [
        [
            "" if cellule is None else str(cellule).strip()
            for cellule in ligne
        ]
        for ligne in table
        if ligne
    ]

    if len(lignes) < 2:
        return None

    entetes = lignes[0]

    entetes_finales = []
    compteurs = {}

    for i, entete in enumerate(entetes):
        nom = str(entete).strip()

        if not nom:
            nom = f"Colonne_{i + 1}"

        compteurs[nom] = compteurs.get(nom, 0) + 1

        if compteurs[nom] > 1:
            nom = f"{nom}_{compteurs[nom]}"

        entetes_finales.append(nom)

    df = pd.DataFrame(
        lignes[1:],
        columns=entetes_finales,
    )

    return normaliser_noms_colonnes(df)


@st.cache_data(show_spinner=False)
def lire_pdf(contenu_bytes):
    dfs = {}

    diagnostic = {
        "type": "pdf",
        "message": "",
        "pages": 0,
        "pages_avec_texte": 0,
        "tables": 0,
    }

    try:
        with pdfplumber.open(
            io.BytesIO(contenu_bytes)
        ) as pdf:

            diagnostic["pages"] = len(pdf.pages)

            compteur_table = 0

            for numero_page, page in enumerate(
                pdf.pages,
                start=1,
            ):
                texte = page.extract_text()

                if texte and texte.strip():
                    diagnostic["pages_avec_texte"] += 1

                tables = page.extract_tables()

                for table in tables:
                    df = nettoyer_table_pdf(table)

                    if df is not None and not df.empty:
                        nom = (
                            f"Page {numero_page} - "
                            f"Table {compteur_table + 1}"
                        )

                        dfs[nom] = df

                        compteur_table += 1

            diagnostic["tables"] = compteur_table

        if not dfs:
            if diagnostic["pages_avec_texte"] == 0:
                diagnostic["message"] = (
                    "Aucun tableau exploitable n'a été trouvé. "
                    "Ce PDF semble probablement être un PDF "
                    "scanné/image. Une étape OCR est nécessaire."
                )
            else:
                diagnostic["message"] = (
                    "Le PDF contient du texte, mais aucune structure "
                    "de tableau exploitable n'a été détectée par "
                    "pdfplumber."
                )

    except Exception as e:
        diagnostic["message"] = (
            f"Erreur lors de la lecture PDF : {e}"
        )

    return dfs, diagnostic


# ============================================================
# ROUTEUR FICHIER
# ============================================================

def lire_fichier_fournisseur(fichier):
    nom = fichier.name.lower()

    contenu = fichier.getvalue()

    if nom.endswith((".xlsx", ".xls")):
        return lire_excel(contenu)

    if nom.endswith(".csv"):
        return lire_csv(contenu)

    if nom.endswith(".pdf"):
        return lire_pdf(contenu)

    return (
        {},
        {
            "type": "inconnu",
            "message": "Format non supporté.",
        },
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("⚙️ Configuration")

    region_nom = st.selectbox(
        "Pays / région",
        list(REGIONS.keys()),
    )

    region = REGIONS[region_nom]

    st.markdown(
        f"""
        **Devise :** {region["devise"]}

        **Symbole :** {region["symbole"]}
        """
    )

    st.divider()

    st.markdown(
        "### 📌 Matching produit"
    )

    st.caption(
        f"Fort : ≥ {SEUIL_MATCHING_FORT:.0%}"
    )

    st.caption(
        f"Probable : ≥ {SEUIL_MATCHING_PROBABLE:.0%}"
    )

    st.divider()

    if RAPIDFUZZ_DISPONIBLE:
        st.success(
            "⚡ RapidFuzz disponible"
        )
    else:
        st.warning(
            "RapidFuzz absent : fallback difflib."
        )


# ============================================================
# UPLOAD
# ============================================================

fichiers = st.file_uploader(
    "📂 Dépose les listes fournisseurs",
    type=[
        "xlsx",
        "xls",
        "csv",
        "pdf",
    ],
    accept_multiple_files=True,
    help=(
        "Formats acceptés : Excel, CSV et PDF "
        "contenant des tableaux."
    ),
)


if not fichiers:
    st.info(
        "👆 Ajoute au moins une liste fournisseur "
        "pour commencer."
    )

    st.stop()


# ============================================================
# LECTURE DES FOURNISSEURS
# ============================================================

donnees_fournisseurs = {}

compteur_fournisseurs = {}

diagnostics_fichiers = []


for i, fichier in enumerate(fichiers):

    nom_base = fichier.name.rsplit(
        ".",
        1,
    )[0]

    compteur_fournisseurs[nom_base] = (
        compteur_fournisseurs.get(
            nom_base,
            0,
        )
        + 1
    )

    if compteur_fournisseurs[nom_base] == 1:
        nom_fournisseur = nom_base
    else:
        nom_fournisseur = (
            f"{nom_base} "
            f"({compteur_fournisseurs[nom_base]})"
        )

    with st.expander(
        f"📄 {nom_fournisseur}",
        expanded=True,
    ):

        dfs, diagnostic = lire_fichier_fournisseur(
            fichier
        )

        diagnostics_fichiers.append(
            (
                nom_fournisseur,
                diagnostic,
            )
        )

        if diagnostic.get("message"):
            if diagnostic.get("type") == "pdf":
                st.warning(
                    diagnostic["message"]
                )
            else:
                st.error(
                    diagnostic["message"]
                )

        if diagnostic.get("type") == "pdf":
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                st.metric(
                    "Pages",
                    diagnostic.get("pages", 0),
                )

            with col_b:
                st.metric(
                    "Pages avec texte",
                    diagnostic.get(
                        "pages_avec_texte",
                        0,
                    ),
                )

            with col_c:
                st.metric(
                    "Tables",
                    diagnostic.get(
                        "tables",
                        0,
                    ),
                )

        if not dfs:
            st.error(
                "Aucune donnée exploitable "
                "pour ce fichier."
            )
            continue

        noms_feuilles = list(dfs.keys())

        if len(noms_feuilles) > 1:
            nom_feuille = st.selectbox(
                "Feuille / tableau",
                noms_feuilles,
                key=f"feuille_{i}_{fichier.name}",
            )
        else:
            nom_feuille = noms_feuilles[0]

        # ----------------------------------------------------
        # NORMALISATION DES COLONNES AVANT DÉTECTION
        # ----------------------------------------------------

        df_brut = normaliser_noms_colonnes(
            dfs[nom_feuille].copy()
        )

        colonnes = list(
            df_brut.columns
        )

        if not colonnes:
            st.error(
                "Aucune colonne trouvée."
            )
            continue

        colonne_produit_auto = (
            detecter_colonne_produit(
                df_brut,
                region,
            )
        )

        colonne_prix_auto = (
            detecter_colonne_prix(
                df_brut,
                region,
            )
        )

        col1, col2 = st.columns(2)

        with col1:
            index_produit = (
                colonnes.index(
                    colonne_produit_auto
                )
                if colonne_produit_auto in colonnes
                else 0
            )

            colonne_produit = st.selectbox(
                "🛒 Colonne produit",
                colonnes,
                index=index_produit,
                key=f"produit_{i}_{fichier.name}",
            )

        with col2:
            index_prix = (
                colonnes.index(
                    colonne_prix_auto
                )
                if colonne_prix_auto in colonnes
                else 0
            )

            colonne_prix = st.selectbox(
                "💰 Colonne prix",
                colonnes,
                index=index_prix,
                key=f"prix_{i}_{fichier.name}",
            )

        # ----------------------------------------------------
        # APERÇU
        # ----------------------------------------------------

        st.caption(
            f"Détection automatique : "
            f"produit = `{colonne_produit_auto}` | "
            f"prix = `{colonne_prix_auto}`"
        )

        st.dataframe(
            df_brut.head(8),
            width="stretch",
            hide_index=True,
        )

        # ----------------------------------------------------
        # PRÉPARATION
        # ----------------------------------------------------

        try:
            df_propre = preparer_donnees(
                df_brut,
                nom_fournisseur,
                colonne_produit,
                colonne_prix,
                region,
            )

        except Exception as e:
            st.error(
                f"Erreur pendant la préparation : {e}"
            )
            continue

        if df_propre.empty:
            st.warning(
                "Aucune ligne exploitable après nettoyage."
            )
            continue

        # ----------------------------------------------------
        # IDENTIFIANT UNIQUE
        # ----------------------------------------------------

        identifiant_fichier = (
            f"{i}_{fichier.name}"
        )

        donnees_fournisseurs[
            identifiant_fichier
        ] = df_propre

        # ----------------------------------------------------
        # MÉTRIQUES
        # ----------------------------------------------------

        total_lignes = len(df_propre)

        comparables = int(
            df_propre["Prix_Comparable"]
            .notna()
            .sum()
        )

        non_comparables = (
            total_lignes - comparables
        )

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            st.metric(
                "Lignes",
                total_lignes,
            )

        with col_b:
            st.metric(
                "Comparables",
                comparables,
            )

        with col_c:
            st.metric(
                "Non comparables",
                non_comparables,
            )

        st.markdown(
            '<div class="success-box">'
            "✅ Fichier préparé avec succès."
            "</div>",
            unsafe_allow_html=True,
        )


# ============================================================
# VÉRIFICATION
# ============================================================

if not donnees_fournisseurs:
    st.error(
        "Aucun fournisseur n'a pu être préparé."
    )
    st.stop()


# ============================================================
# CONSOLIDATION
# ============================================================

df_tous = pd.concat(
    donnees_fournisseurs.values(),
    ignore_index=True,
)


# ============================================================
# MATCHING
# ============================================================

with st.spinner(
    "🔎 Analyse et rapprochement des produits..."
):

    df_match, groupes = appliquer_matching(
        df_tous
    )


# ============================================================
# CALCUL DES GAGNANTS
# ============================================================

df_comparables = df_match[
    df_match["Prix_Comparable"].notna()
    & df_match["Unite_Comparaison"].notna()
].copy()


df_non_comparables = df_match[
    ~(
        df_match["Prix_Comparable"].notna()
        & df_match["Unite_Comparaison"].notna()
    )
].copy()


if df_comparables.empty:
    st.warning(
        "Aucune offre avec prix comparable n'a été trouvée."
    )
    st.stop()


# ============================================================
# PRIX MINIMUMS PAR GROUPE + UNITÉ
# ============================================================

minimums = (
    df_comparables
    .groupby(
        [
            "Groupe_Produit",
            "Unite_Comparaison",
        ],
        as_index=False,
        dropna=False,
    )["Prix_Comparable"]
    .min()
    .rename(columns={"Prix_Comparable": "Prix_Minimum"})
)

# On récupère uniquement les offres dont le prix est
# exactement égal au minimum de leur groupe.
# Le prix fait partie de la jointure afin d'éviter
# une multiplication inutile des lignes.
df_resultat = df_comparables.merge(
    minimums,
    on=[
        "Groupe_Produit",
        "Unite_Comparaison",
    ],
    how="inner",
)

df_resultat = df_resultat[
    df_resultat["Prix_Comparable"].eq(
        df_resultat["Prix_Minimum"]
    )
].copy()

# Évite uniquement les doublons strictement identiques.
# Les vrais ex æquo entre fournisseurs sont conservés.
df_resultat = (
    df_resultat
    .drop_duplicates(
        subset=[
            "Groupe_Produit",
            "Unite_Comparaison",
            "Fournisseur",
            "Produit_Affichage",
            "Prix_Comparable",
        ]
    )
    .reset_index(drop=True)
)

# ------------------------------------------------------------
# CONSERVATION DES EX ÆQUO
# ------------------------------------------------------------

df_resultat = df_resultat[
    np.isclose(
        df_resultat["Prix_Comparable"],
        df_resultat["Prix_Minimum"],
        rtol=1e-9,
        atol=1e-9,
    )
].copy()


# ============================================================
# NOM CANONIQUE DU PRODUIT
# ============================================================

# Le nom affiché est choisi parmi les offres gagnantes.
noms_canoniques = (
    df_resultat[
        [
            "Groupe_Produit",
            "Produit_Affichage",
            "Fournisseur",
        ]
    ]
    .drop_duplicates()
    .assign(
        longueur=lambda x:
        x["Produit_Affichage"].str.len()
    )
    .sort_values(
        [
            "Groupe_Produit",
            "longueur",
            "Fournisseur",
            "Produit_Affichage",
        ]
    )
    .drop_duplicates(
        "Groupe_Produit",
        keep="first",
    )
    [
        [
            "Groupe_Produit",
            "Produit_Affichage",
        ]
    ]
    .rename(
        columns={
            "Produit_Affichage": "Produit_Canonique"
        }
    )
)


df_resultat = df_resultat.merge(
    noms_canoniques,
    on="Groupe_Produit",
    how="left",
)


# ============================================================
# FORMATAGE AFFICHAGE
# ============================================================

df_resultat["Prix_affiche"] = (
    df_resultat["Prix_Numerique"]
    .map(
        lambda x: (
            "—"
            if pd.isna(x)
            else f"{region['symbole']}{x:.2f}"
        )
    )
)

df_resultat["Prix_comparable_affiche"] = (
    df_resultat.apply(
        lambda ligne: format_prix_comparable(
            ligne["Prix_Comparable"],
            ligne["Unite_Comparaison"],
            region["symbole"],
        ),
        axis=1,
    )
)

df_resultat["Score_affiche"] = (
    df_resultat["Score_Matching"]
    .map(
        lambda x: f"{x:.0%}"
    )
)


df_resultat["Conditionnement_affiche"] = (
    df_resultat["Conditionnement"]
    .replace(
        "",
        "—",
    )
)


df_resultat["Correspondance_affiche"] = (
    df_resultat["Type_Matching"]
    .map(
        {
            "exact": "Exact",
            "fort": "Fort",
            "probable": "Probable",
            "nouveau": "Nouveau",
        }
    )
    .fillna("—")
)


# ============================================================
# EN-TÊTE RÉSULTATS
# ============================================================

st.divider()

st.subheader(
    "🏆 Meilleures offres"
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Produits comparés",
        df_resultat["Groupe_Produit"].nunique(),
    )

with col2:
    st.metric(
        "Offres gagnantes",
        len(df_resultat),
    )

with col3:
    st.metric(
        "Fournisseurs",
        df_match["Fournisseur"].nunique(),
    )

with col4:
    st.metric(
        "Offres analysées",
        len(df_match),
    )


# ============================================================
# TABLEAU PRINCIPAL
# ============================================================

resultat_affichage = (
    df_resultat[
        [
            "Produit_Canonique",
            "Fournisseur",
            "Produit_Affichage",
            "Prix_affiche",
            "Conditionnement_affiche",
            "Prix_comparable_affiche",
            "Correspondance_affiche",
            "Score_affiche",
        ]
    ]
    .rename(
        columns={
            "Produit_Canonique": "Produit",
            "Produit_Affichage": "Libellé fournisseur",
            "Prix_affiche": "Prix affiché",
            "Conditionnement_affiche": "Conditionnement affiché",
            "Prix_comparable_affiche": "Prix comparable",
            "Correspondance_affiche": "Correspondance",
            "Score_affiche": "Score matching",
        }
    )
)


st.dataframe(
    resultat_affichage,
    width="stretch",
    hide_index=True,
    column_config={
        "Produit": st.column_config.TextColumn(
            "Produit",
            width="medium",
        ),
        "Fournisseur": st.column_config.TextColumn(
            "Fournisseur",
            width="medium",
        ),
        "Libellé fournisseur": st.column_config.TextColumn(
            "Libellé fournisseur",
            width="large",
        ),
        "Prix affiché": st.column_config.TextColumn(
            "Prix affiché",
        ),
        "Conditionnement affiché": st.column_config.TextColumn(
            "Conditionnement",
        ),
        "Prix comparable": st.column_config.TextColumn(
            "Prix comparable",
        ),
        "Correspondance": st.column_config.TextColumn(
            "Correspondance",
        ),
        "Score matching": st.column_config.TextColumn(
            "Score",
        ),
    },
)


# ============================================================
# DÉTAILS
# ============================================================

with st.expander(
    "🔍 Voir les détails du calcul",
    expanded=False,
):

    details = df_resultat[
        [
            "Produit_Canonique",
            "Fournisseur",
            "Produit_Affichage",
            "Prix_Numerique",
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

    details["Prix_Numerique"] = (
        details["Prix_Numerique"]
        .round(4)
    )

    details["Prix_Comparable"] = (
        details["Prix_Comparable"]
        .round(4)
    )

    details["Score_Matching"] = (
        details["Score_Matching"]
        .map(
            lambda x: f"{x:.2%}"
        )
    )

    details = details.rename(
        columns={
            "Produit_Canonique": "Produit",
            "Produit_Affichage": "Libellé fournisseur",
            "Prix_Numerique": "Prix numérique",
            "Base_Prix": "Base prix",
            "Conditionnement": "Conditionnement",
            "Quantite_Normalisee": "Quantité normalisée",
            "Unite_Etalon": "Unité étalon",
            "Prix_Comparable": "Prix comparable",
            "Unite_Comparaison": "Unité comparaison",
            "Type_Matching": "Type matching",
            "Score_Matching": "Score matching",
        }
    )

    st.dataframe(
        details,
        width="stretch",
        hide_index=True,
    )


# ============================================================
# OFFRES NON COMPARABLES
# ============================================================

if not df_non_comparables.empty:

    st.divider()

    with st.expander(
        f"⚠️ Offres non comparables ({len(df_non_comparables)})",
        expanded=False,
    ):

        non_comp = df_non_comparables[
            [
                "Fournisseur",
                "Produit_Affichage",
                "Prix_Numerique",
                "Base_Prix",
                "Conditionnement",
                "Quantite_Normalisee",
                "Unite_Etalon",
            ]
        ].copy()

        non_comp["Prix_Numerique"] = (
            non_comp["Prix_Numerique"]
            .map(
                lambda x: (
                    "—"
                    if pd.isna(x)
                    else f"{region['symbole']}{x:.2f}"
                )
            )
        )

        non_comp = non_comp.rename(
            columns={
                "Produit_Affichage": "Produit",
                "Prix_Numerique": "Prix",
                "Base_Prix": "Base prix",
                "Conditionnement": "Conditionnement",
                "Quantite_Normalisee": "Quantité normalisée",
                "Unite_Etalon": "Unité",
            }
        )

        st.dataframe(
            non_comp,
            width="stretch",
            hide_index=True,
        )

        st.caption(
            "Ces offres n'ont pas pu être ramenées "
            "à une unité comparable. Elles ne participent "
            "donc pas à la sélection du meilleur prix."
        )


# ============================================================
# DIAGNOSTICS
# ============================================================

with st.expander(
    "🩺 Diagnostics",
    expanded=False,
):

    st.write(
        {
            "RapidFuzz": RAPIDFUZZ_DISPONIBLE,
            "Lignes analysées": len(df_match),
            "Groupes produits": df_match[
                "Groupe_Produit"
            ].nunique(),
            "Offres comparables": len(df_comparables),
            "Offres non comparables": len(df_non_comparables),
            "Offres gagnantes": len(df_resultat),
            "Fournisseurs": df_match[
                "Fournisseur"
            ].nunique(),
        }
    )

    if diagnostics_fichiers:
        st.markdown(
            "### Fichiers"
        )

        for nom, diagnostic in diagnostics_fichiers:
            message = diagnostic.get(
                "message",
                "",
            )

            if message:
                st.warning(
                    f"**{nom}** : {message}"
                )
            else:
                st.success(
                    f"**{nom}** : lecture OK"
                )


# ============================================================
# EXPORT GAGNANTS
# ============================================================

st.divider()

st.subheader(
    "📥 Export"
)

export_gagnants = df_resultat[
    [
        "Produit_Canonique",
        "Groupe_Produit",
        "Fournisseur",
        "Produit_Affichage",
        "Prix_Numerique",
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


export_gagnants = export_gagnants.rename(
    columns={
        "Produit_Canonique": "Produit",
        "Produit_Affichage": "Libelle_Fournisseur",
        "Prix_Numerique": "Prix_Affiche",
        "Quantite_Normalisee": "Quantite_Normalisee",
        "Unite_Etalon": "Unite_Etalon",
        "Prix_Comparable": "Prix_Comparable",
        "Unite_Comparaison": "Unite_Comparaison",
        "Type_Matching": "Type_Matching",
        "Score_Matching": "Score_Matching",
    }
)


csv_gagnants = export_gagnants.to_csv(
    index=False,
    sep=";",
    decimal=",",
).encode("utf-8-sig")

col1, col2 = st.columns(2)

with col1:
    st.download_button(
        "🏆 Télécharger les gagnants",
        data=csv_gagnants,
        file_name="optimarge_gagnants.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# EXPORT COMPLET
# ============================================================

export_complet = df_match.copy()

csv_complet = export_complet.to_csv(
    index=False,
    sep=";",
    decimal=",",
).encode("utf-8-sig")


with col2:
    st.download_button(
        "📊 Télécharger toutes les offres",
        data=csv_complet,
        file_name="optimarge_toutes_offres.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.caption(
    "OptiMarge Food — comparaison normalisée des offres fournisseurs."
)