import streamlit as st
import pandas as pd
import numpy as np
import re
import unicodedata
import io
import pdfplumber
from difflib import SequenceMatcher

# ============================================================
# RAPIDFUZZ : optionnel mais recommandé pour gros volumes
# ============================================================

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


# ============================================================
# CSS MOBILE-FIRST
# ============================================================

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 1600px;
        }

        .main-title {
            font-size: 2.2rem;
            font-weight: 800;
            margin-bottom: 0.15rem;
        }

        .small-muted {
            color: #6b7280;
            font-size: 0.85rem;
        }

        .provider-card {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
        }

        div[data-testid="stMetric"] {
            padding: 0.5rem;
        }

        div[data-testid="stMetricValue"] {
            font-size: 1.8rem;
        }

        .warning-box {
            border-radius: 10px;
            padding: 12px;
            border: 1px solid #f59e0b;
            background: #fffbeb;
        }

        .success-box {
            border-radius: 10px;
            padding: 12px;
            border: 1px solid #10b981;
            background: #ecfdf5;
        }

        @media (max-width: 600px) {
            .main-title {
                font-size: 1.65rem;
            }

            div[data-testid="stMetricValue"] {
                font-size: 1.35rem;
            }

            .block-container {
                padding-left: 0.7rem;
                padding-right: 0.7rem;
            }

            button,
            [data-testid="stDownloadButton"] button {
                width: 100%;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CONSTANTES MATCHING
# ============================================================

SEUIL_MATCHING_FORT = 0.92
SEUIL_MATCHING_PROBABLE = 0.86


# ============================================================
# NORMALISATION TEXTE
# ============================================================

def normaliser_texte(texte):
    if texte is None:
        return ""

    if pd.isna(texte):
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


def normaliser_produit(texte):
    texte = normaliser_texte(texte)

    if not texte:
        return ""

    texte = re.sub(r"[^a-z0-9]+", " ", texte)

    mots_inutiles = {
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
        if token not in mots_inutiles
    ]

    return " ".join(tokens).upper()


def cle_produit_fuzzy(texte):
    texte = normaliser_produit(texte)

    if not texte:
        return ""

    # Harmonisation de quelques variantes fréquentes.
    texte = re.sub(r"^JUS\s+D\s+", "JUS ", texte)
    texte = re.sub(r"^JUS\s+DE\s+", "JUS ", texte)

    return texte.strip()


# ============================================================
# REGION / DEVISE
# ============================================================

def configuration_region(region):
    if region == "France 🇫🇷":
        return {
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
                "item",
                "product",
                "name",
            ],
            "mots_prix": [
                "prix",
                "tarif",
                "cout",
                "coût",
                "montant",
                "price",
                "tarif unitaire",
                "prix unitaire",
                "prix/kg",
                "prix/l",
                "prix/litre",
                "prix au kg",
                "prix au kilo",
                "prix par kg",
                "prix par kilo",
            ],
        }

    return {
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
            "item",
            "product",
            "name",
            "product name",
        ],
        "mots_prix": [
            "prix",
            "tarif",
            "cout",
            "coût",
            "montant",
            "price",
            "unit price",
            "prix unitaire",
            "price/kg",
            "price/l",
            "price/litre",
            "price per kg",
            "price per kilo",
            "price/kg",
            "$/kg",
            "$/lb",
            "$/l",
            "$/gal",
        ],
    }


# ============================================================
# PRIX / DEVISE
# ============================================================

def convertir_prix_international(valeur, pays="FR"):
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

    texte = texte.replace("\u00a0", " ")
    texte = texte.replace("−", "-")

    if "-" in texte:
        return np.nan

    # Supprime symboles monétaires / codes.
    texte = re.sub(
        r"(CAD|C\$|CA\$|USD|US\$|EUR|€|£|\$)",
        "",
        texte,
        flags=re.IGNORECASE,
    )

    texte = texte.strip()

    # Ne conserve que chiffres, séparateurs décimaux.
    texte = re.sub(r"[^0-9,.\s]", "", texte)
    texte = texte.replace(" ", "")

    if not texte:
        return np.nan

    # Cas :
    # 1.234,56
    # 1,234.56
    # 12,50
    # 12.50
    if "," in texte and "." in texte:
        if texte.rfind(",") > texte.rfind("."):
            texte = texte.replace(".", "")
            texte = texte.replace(",", ".")
        else:
            texte = texte.replace(",", "")

    elif "," in texte:
        parties = texte.split(",")

        if len(parties) == 2 and len(parties[1]) in (1, 2):
            texte = texte.replace(",", ".")
        else:
            texte = texte.replace(",", "")

    elif "." in texte:
        parties = texte.split(".")

        if len(parties) > 2:
            texte = "".join(parties[:-1]) + "." + parties[-1]

    try:
        resultat = float(texte)

        if resultat < 0:
            return np.nan

        return resultat

    except Exception:
        return np.nan


def detecter_base_prix_colonne(nom_colonne):
    texte = normaliser_texte(nom_colonne)

    if not texte:
        return None

    # Prix directs au poids.
    if re.search(
        r"(?:prix|price|tarif|cout|coût).{0,20}"
        r"(?:/|par|au|a)\s*"
        r"(?:kg|kilo|kilogramme|kilogrammes)",
        texte,
    ):
        return "KG"

    if re.search(r"(?:/|par|au|a)\s*lb\b", texte):
        return "LB"

    if re.search(r"(?:/|par|au|a)\s*oz\b", texte):
        return "OZ"

    # Prix directs au volume.
    if re.search(
        r"(?:prix|price|tarif|cout|coût).{0,20}"
        r"(?:/|par|au|a)\s*"
        r"(?:l|litre|litres|liter|liters)",
        texte,
    ):
        return "L"

    if re.search(r"(?:/|par|au|a)\s*ml\b", texte):
        return "ML"

    if re.search(r"(?:/|par|au|a)\s*(?:gal|gallon|gallons)", texte):
        return "GAL"

    if re.search(
        r"(?:prix|price|tarif|cout|coût).{0,20}"
        r"(?:/|par|au|a)\s*"
        r"(?:u|unite|unité|piece|pièce|item)",
        texte,
    ):
        return "U"

    if re.search(r"\b(?:package|paquet|colis|caisse|case)\b", texte):
        return "PACKAGE"

    # Unités explicites.
    if re.search(
        r"\b(?:prix|price|tarif).{0,10}"
        r"(?:unitaire|unit|piece|pièce)\b",
        texte,
    ):
        return "U"

    return None


def detecter_base_prix_valeur(valeur, pays="FR"):
    if valeur is None or pd.isna(valeur):
        return None

    texte = normaliser_texte(valeur)

    if not texte:
        return None

    if re.search(r"(?:/|par|au|a)\s*(?:kg|kilo|kilogramme)", texte):
        return "KG"

    if re.search(r"(?:/|par|au|a)\s*lb\b", texte):
        return "LB"

    if re.search(r"(?:/|par|au|a)\s*oz\b", texte):
        return "OZ"

    if re.search(r"(?:/|par|au|a)\s*(?:l|litre|liter)\b", texte):
        return "L"

    if re.search(r"(?:/|par|au|a)\s*ml\b", texte):
        return "ML"

    if re.search(r"(?:/|par|au|a)\s*(?:gal|gallon)", texte):
        return "GAL"

    if re.search(
        r"(?:/|par|au|a)\s*(?:u|unite|unité|piece|pièce|item)",
        texte,
    ):
        return "U"

    return None


def convertir_prix_direct(prix, unite_source):
    if prix is None or pd.isna(prix):
        return np.nan, None

    unite_source = str(unite_source).upper()

    prix = float(prix)

    if prix < 0:
        return np.nan, None

    # Masse -> KG
    if unite_source == "KG":
        return prix, "KG"

    if unite_source == "LB":
        return prix / 0.45359237, "KG"

    if unite_source == "OZ":
        return prix / 0.028349523125, "KG"

    # Volume -> L
    if unite_source == "L":
        return prix, "L"

    if unite_source == "ML":
        return prix * 1000 / 1000, "L"

    if unite_source == "GAL":
        return prix / 3.785411784, "L"

    # Unité
    if unite_source == "U":
        return prix, "U"

    return np.nan, None


# ============================================================
# CONDITIONNEMENT
# ============================================================

def conditionnement_vide(libelle=""):
    return {
        "conditionnement_original": "",
        "quantite_totale": np.nan,
        "unite_standard": None,
        "conditionnement_detecte": False,
        "texte_conditionnement": "",
        "type_conditionnement": "inconnu",
    }


def _convertir_quantite(unite, quantite):
    unite = normaliser_texte(unite)

    try:
        quantite = float(quantite)
    except Exception:
        return np.nan, None

    if quantite <= 0:
        return np.nan, None

    # Masse
    if unite in {"g", "gramme", "grammes"}:
        return quantite / 1000, "KG"

    if unite in {"kg", "kilo", "kilos", "kilogramme", "kilogrammes"}:
        return quantite, "KG"

    if unite in {"lb", "lbs", "pound", "pounds"}:
        return quantite * 0.45359237, "KG"

    if unite in {"oz", "ounce", "ounces"}:
        return quantite * 0.028349523125, "KG"

    # Volume
    if unite in {"ml", "millilitre", "millilitres", "milliliter", "milliliters"}:
        return quantite / 1000, "L"

    if unite in {"cl", "centilitre", "centilitres"}:
        return quantite / 100, "L"

    if unite in {"l", "litre", "litres", "liter", "liters"}:
        return quantite, "L"

    if unite in {"fl oz", "floz", "fluid ounce", "fluid ounces"}:
        return quantite * 0.0295735295625, "L"

    if unite in {"gal", "gallon", "gallons"}:
        return quantite * 3.785411784, "L"

    return np.nan, None


def extraire_conditionnement(libelle):
    resultat = conditionnement_vide(libelle)

    texte = normaliser_texte(libelle)

    if not texte:
        return resultat

    # --------------------------------------------------------
    # 1. Multipack : 12 x 355 ml
    # --------------------------------------------------------

    pattern_multipack = re.compile(
        r"(?P<nb>\d+(?:[.,]\d+)?)\s*x\s*"
        r"(?P<qte>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unite>kg|kilo|kilos|kilogramme|kilogrammes|"
        r"g|gramme|grammes|lb|lbs|pound|pounds|oz|ounce|ounces|"
        r"l|litre|litres|liter|liters|ml|cl|fl\s*oz|floz|"
        r"gal|gallon|gallons)\b"
    )

    match = pattern_multipack.search(texte)

    if match:
        nb = float(match.group("nb").replace(",", "."))
        qte = float(match.group("qte").replace(",", "."))
        unite = match.group("unite")

        qte_unitaire, unite_standard = _convertir_quantite(unite, qte)

        if unite_standard:
            resultat.update(
                {
                    "conditionnement_original": match.group(0),
                    "quantite_totale": nb * qte_unitaire,
                    "unite_standard": unite_standard,
                    "conditionnement_detecte": True,
                    "texte_conditionnement": match.group(0),
                    "type_conditionnement": "multipack",
                }
            )

            return resultat

    # --------------------------------------------------------
    # 2. Fraction : 6/750 ml
    # --------------------------------------------------------

    pattern_fraction = re.compile(
        r"(?P<nb>\d+)\s*/\s*"
        r"(?P<qte>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unite>kg|kilo|kilos|kilogramme|kilogrammes|"
        r"g|gramme|grammes|lb|lbs|pound|pounds|oz|ounce|ounces|"
        r"l|litre|litres|liter|liters|ml|cl|fl\s*oz|floz|"
        r"gal|gallon|gallons)\b"
    )

    match = pattern_fraction.search(texte)

    if match:
        nb = float(match.group("nb"))
        qte = float(match.group("qte").replace(",", "."))
        unite = match.group("unite")

        qte_unitaire, unite_standard = _convertir_quantite(unite, qte)

        if unite_standard:
            resultat.update(
                {
                    "conditionnement_original": match.group(0),
                    "quantite_totale": nb * qte_unitaire,
                    "unite_standard": unite_standard,
                    "conditionnement_detecte": True,
                    "texte_conditionnement": match.group(0),
                    "type_conditionnement": "fraction",
                }
            )

            return resultat

    # --------------------------------------------------------
    # 3. Quantité simple : 500 g / 1 kg / 750 ml
    # --------------------------------------------------------

    pattern_simple = re.compile(
        r"(?P<qte>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unite>kg|kilo|kilos|kilogramme|kilogrammes|"
        r"g|gramme|grammes|lb|lbs|pound|pounds|oz|ounce|ounces|"
        r"l|litre|litres|liter|liters|ml|cl|fl\s*oz|floz|"
        r"gal|gallon|gallons)\b"
    )

    matches = list(pattern_simple.finditer(texte))

    if matches:
        # On privilégie le dernier conditionnement détecté,
        # car il est souvent le plus proche de la fin du produit.
        match = matches[-1]

        qte = float(match.group("qte").replace(",", "."))
        unite = match.group("unite")

        qte_standard, unite_standard = _convertir_quantite(
            unite,
            qte,
        )

        if unite_standard:
            resultat.update(
                {
                    "conditionnement_original": match.group(0),
                    "quantite_totale": qte_standard,
                    "unite_standard": unite_standard,
                    "conditionnement_detecte": True,
                    "texte_conditionnement": match.group(0),
                    "type_conditionnement": "simple",
                }
            )

            return resultat

    # --------------------------------------------------------
    # 4. Pack de 6 / pack of 6 / case of 24
    # --------------------------------------------------------

    pattern_pack_avant = re.compile(
        r"\b(?:pack|packs|paquet|paquets|case|cases|"
        r"caisse|caisses|colis|carton|cartons)"
        r"\s*(?:de|of|à|a)?\s*"
        r"(?P<nb>\d+)\b"
    )

    match = pattern_pack_avant.search(texte)

    if match:
        nb = int(match.group("nb"))

        resultat.update(
            {
                "conditionnement_original": match.group(0),
                "quantite_totale": float(nb),
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "pack",
            }
        )

        return resultat

    # --------------------------------------------------------
    # 5. 6 pack / 12 packs / 24 case
    # --------------------------------------------------------

    pattern_pack_apres = re.compile(
        r"\b(?P<nb>\d+)\s*"
        r"(?:pack|packs|case|cases|"
        r"paquet|paquets|colis|carton|cartons)\b"
    )

    match = pattern_pack_apres.search(texte)

    if match:
        nb = int(match.group("nb"))

        resultat.update(
            {
                "conditionnement_original": match.group(0),
                "quantite_totale": float(nb),
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "pack",
            }
        )

        return resultat

    # --------------------------------------------------------
    # 6. Unités explicites : 24 pcs / 24 units / 24 pièces
    # --------------------------------------------------------

    pattern_unites = re.compile(
        r"\b(?P<nb>\d+)\s*"
        r"(?:pcs?|pieces?|pièces?|units?|unites?|unités?)\b"
    )

    match = pattern_unites.search(texte)

    if match:
        nb = int(match.group("nb"))

        resultat.update(
            {
                "conditionnement_original": match.group(0),
                "quantite_totale": float(nb),
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "unites",
            }
        )

        return resultat

    # --------------------------------------------------------
    # 7. Bouteilles / canettes / boîtes / sacs
    # --------------------------------------------------------

    pattern_colis = re.compile(
        r"\b(?P<nb>\d+)\s*"
        r"(?:bouteilles?|bottles?|"
        r"cans?|canettes?|"
        r"boites?|boîtes?|boxes?|"
        r"sacs?|bags?|"
        r"bidons?|jars?)\b"
    )

    match = pattern_colis.search(texte)

    if match:
        nb = int(match.group("nb"))

        resultat.update(
            {
                "conditionnement_original": match.group(0),
                "quantite_totale": float(nb),
                "unite_standard": "U",
                "conditionnement_detecte": True,
                "texte_conditionnement": match.group(0),
                "type_conditionnement": "colis_unites",
            }
        )

        return resultat

    return resultat


def extraire_produit_base(libelle):
    texte = normaliser_texte(libelle)

    if not texte:
        return ""

    conditionnement = extraire_conditionnement(texte)

    texte_conditionnement = conditionnement.get(
        "texte_conditionnement",
        "",
    )

    if texte_conditionnement:
        # Retire uniquement le conditionnement détecté.
        # Cela évite de supprimer des chiffres intrinsèques
        # à des produits comme 7UP.
        texte = texte.replace(
            texte_conditionnement,
            " ",
            1,
        )

    return normaliser_produit(texte)


# ============================================================
# PRIX COMPARABLE
# ============================================================

def calculer_prix_comparable(prix, quantite, unite):
    if prix is None or pd.isna(prix):
        return np.nan

    if quantite is None or pd.isna(quantite):
        return np.nan

    if not unite:
        return np.nan

    try:
        prix = float(prix)
        quantite = float(quantite)
    except Exception:
        return np.nan

    if prix < 0 or quantite <= 0:
        return np.nan

    return prix / quantite


def format_prix_comparable(prix, unite, symbole="€"):
    if prix is None or pd.isna(prix):
        return ""

    if not unite:
        return ""

    if unite == "KG":
        return f"{prix:,.2f} {symbole}/kg".replace(",", " ")

    if unite == "L":
        return f"{prix:,.2f} {symbole}/L".replace(",", " ")

    if unite == "U":
        return f"{prix:,.2f} {symbole}/u".replace(",", " ")

    return f"{prix:,.2f} {symbole}"


# ============================================================
# DETECTION COLONNES
# ============================================================

def detecter_colonne_produit(df, config):
    meilleurs = []

    for colonne in df.columns:
        texte = normaliser_texte(colonne)

        score = 0

        for mot in config["mots_produit"]:
            if mot in texte:
                score += 10

        if re.search(
            r"(produit|product|designation|désignation|"
            r"libelle|libellé|description|item|name)",
            texte,
        ):
            score += 30

        if score > 0:
            meilleurs.append((score, colonne))

    if not meilleurs:
        # Fallback : colonne texte avec le plus de valeurs.
        colonnes_texte = []

        for colonne in df.columns:
            try:
                nb = df[colonne].astype(str).str.strip().ne("").sum()
                colonnes_texte.append((nb, colonne))
            except Exception:
                continue

        if colonnes_texte:
            colonnes_texte.sort(reverse=True)
            return colonnes_texte[0][1]

        return None

    meilleurs.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return meilleurs[0][1]


def detecter_colonne_prix(df, config):
    meilleurs = []

    for colonne in df.columns:
        texte = normaliser_texte(colonne)

        score = 0

        for mot in config["mots_prix"]:
            if mot in texte:
                score += 10

        if re.search(
            r"(prix|price|tarif|cout|coût|montant)",
            texte,
        ):
            score += 25

        if re.search(
            r"(kg|kilo|lb|oz|litre|liter|ml|l|gal|unit|unite|unité|piece|pièce)",
            texte,
        ):
            score += 10

        if score > 0:
            meilleurs.append((score, colonne))

    if not meilleurs:
        return None

    meilleurs.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return meilleurs[0][1]


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
        with pd.ExcelFile(io.BytesIO(contenu_bytes)) as excel:
            for feuille in excel.sheet_names:
                try:
                    df = excel.parse(feuille)

                    if df is not None and not df.empty:
                        dfs[feuille] = df

                except Exception:
                    continue

        if not dfs:
            diagnostic["message"] = (
                "Aucune feuille Excel exploitable n'a été trouvée."
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

    essais = [
        ("utf-8", ";"),
        ("utf-8", ","),
        ("latin1", ";"),
        ("latin1", ","),
        ("cp1252", ";"),
        ("cp1252", ","),
    ]

    for encoding, separateur in essais:
        try:
            df = pd.read_csv(
                io.BytesIO(contenu_bytes),
                encoding=encoding,
                sep=separateur,
            )

            if df is not None and not df.empty:
                dfs["CSV"] = df
                return dfs, diagnostic

        except Exception:
            continue

    # Dernière tentative avec détection automatique.
    try:
        df = pd.read_csv(
            io.BytesIO(contenu_bytes),
            encoding="utf-8",
            sep=None,
            engine="python",
        )

        if df is not None and not df.empty:
            dfs["CSV"] = df
            return dfs, diagnostic

    except Exception:
        pass

    diagnostic["message"] = (
        "Impossible de lire le CSV avec les encodages/séparateurs "
        "courants."
    )

    return dfs, diagnostic


# ============================================================
# NETTOYAGE TABLE PDF
# ============================================================

def nettoyer_table_pdf(table):
    if not table:
        return None

    lignes = []

    for ligne in table:
        if ligne is None:
            continue

        ligne_nettoyee = [
            "" if cellule is None else str(cellule).strip()
            for cellule in ligne
        ]

        if any(cellule != "" for cellule in ligne_nettoyee):
            lignes.append(ligne_nettoyee)

    if len(lignes) < 2:
        return None

    header = lignes[0]

    # Rend les noms de colonnes uniques.
    colonnes = []
    compteurs = {}

    for i, nom in enumerate(header):
        nom = nom.strip()

        if not nom:
            nom = f"Colonne_{i + 1}"

        base = nom
        compteurs[base] = compteurs.get(base, 0) + 1

        if compteurs[base] > 1:
            nom = f"{base}_{compteurs[base]}"

        colonnes.append(nom)

    donnees = lignes[1:]

    try:
        df = pd.DataFrame(
            donnees,
            columns=colonnes,
        )

        df = df.dropna(
            how="all",
        )

        if df.empty:
            return None

        return df

    except Exception:
        return None


# ============================================================
# LECTURE PDF - DIAGNOSTIC RENFORCE
# ============================================================

@st.cache_data(show_spinner=False)
def lire_pdf(contenu_bytes):
    dfs = {}

    diagnostic = {
        "type": "pdf",
        "message": "",
        "pages": 0,
        "pages_avec_texte": 0,
        "tables_detectees": 0,
    }

    try:
        with pdfplumber.open(io.BytesIO(contenu_bytes)) as pdf:
            diagnostic["pages"] = len(pdf.pages)

            for numero_page, page in enumerate(
                pdf.pages,
                start=1,
            ):
                try:
                    texte_page = page.extract_text()

                    if texte_page and texte_page.strip():
                        diagnostic["pages_avec_texte"] += 1
                except Exception:
                    pass

                try:
                    tables = page.extract_tables()

                except Exception:
                    tables = []

                if not tables:
                    continue

                for numero_table, table in enumerate(
                    tables,
                    start=1,
                ):
                    try:
                        df = nettoyer_table_pdf(table)

                        if df is None or df.empty:
                            continue

                        nom_table = (
                            f"Page {numero_page} - "
                            f"Tableau {numero_table}"
                        )

                        dfs[nom_table] = df
                        diagnostic["tables_detectees"] += 1

                    except Exception:
                        continue

        # ----------------------------------------------------
        # Diagnostic final
        # ----------------------------------------------------

        if not dfs:
            if diagnostic["pages_avec_texte"] == 0:
                diagnostic["message"] = (
                    "⚠️ Aucun tableau exploitable n'a été détecté. "
                    "Ce PDF semble probablement être un PDF scanné "
                    "ou composé d'images. Une étape OCR peut être "
                    "nécessaire."
                )

            else:
                diagnostic["message"] = (
                    "⚠️ Aucun tableau exploitable n'a été détecté "
                    "dans ce PDF. Le PDF contient du texte, mais sa "
                    "structure tabulaire n'est probablement pas "
                    "reconnue par pdfplumber."
                )

    except Exception as e:
        diagnostic["message"] = (
            f"❌ Erreur lors de l'ouverture du PDF : {e}"
        )

    return dfs, diagnostic


# ============================================================
# ROUTEUR DE FICHIER
# ============================================================

def lire_fichier_fournisseur(fichier):
    contenu = fichier.getvalue()

    extension = fichier.name.lower().rsplit(".", 1)[-1]

    if extension in {"xlsx", "xls"}:
        return lire_excel(contenu)

    if extension == "csv":
        return lire_csv(contenu)

    if extension == "pdf":
        return lire_pdf(contenu)

    return {}, {
        "type": extension,
        "message": "Format de fichier non supporté.",
    }


# ============================================================
# PREPARATION DES DONNEES
# ============================================================

def preparer_donnees(
    df,
    colonne_produit,
    colonne_prix,
    fournisseur,
    pays="FR",
):
    travail = df.copy()

    # ========================================================
    # Normalisation des noms de colonnes
    # ========================================================

    travail.columns = [
        str(colonne).strip()
        for colonne in travail.columns
    ]

    # Remplace les colonnes anonymes de type :
    # "Unnamed: 0", "Unnamed: 1", etc.
    nouvelles_colonnes = []

    for i, colonne in enumerate(travail.columns):
        colonne_str = str(colonne).strip()

        if (
            not colonne_str
            or colonne_str.lower().startswith("unnamed:")
        ):
            colonne_str = f"Colonne_{i + 1}"

        nouvelles_colonnes.append(colonne_str)

    travail.columns = nouvelles_colonnes

    # ========================================================
    # Sécurisation des noms de colonnes sélectionnés
    # ========================================================

    colonne_produit = str(colonne_produit).strip()
    colonne_prix = str(colonne_prix).strip()

    if colonne_produit not in travail.columns:
        raise ValueError(
            f"La colonne produit '{colonne_produit}' "
            "n'existe plus après normalisation."
        )

    if colonne_prix not in travail.columns:
        raise ValueError(
            f"La colonne prix '{colonne_prix}' "
            "n'existe plus après normalisation."
        )

    # ========================================================
    # Produit
    # ========================================================

    travail["Produit_Affichage"] = (
        travail[colonne_produit]
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # Prix
    # ========================================================

    travail["Prix_Brut"] = travail[colonne_prix]

    base_colonne = detecter_base_prix_colonne(
        colonne_prix
    )

    travail["Base_Prix_Colonne"] = base_colonne

    travail["Prix_Numerique"] = travail[
        "Prix_Brut"
    ].apply(
        lambda x: convertir_prix_international(
            x,
            pays=pays,
        )
    )

    travail["Base_Prix_Valeur"] = travail[
        "Prix_Brut"
    ].apply(
        lambda x: detecter_base_prix_valeur(
            x,
            pays=pays,
        )
    )

    travail["Base_Prix"] = travail[
        "Base_Prix_Valeur"
    ].fillna(
        travail["Base_Prix_Colonne"]
    )

    # ========================================================
    # Conditionnement
    # ========================================================

    conditionnements = travail[
        "Produit_Affichage"
    ].apply(extraire_conditionnement)

    travail["Conditionnement"] = conditionnements.apply(
        lambda x: x["conditionnement_original"]
    )

    travail["Quantite_Normalisee"] = conditionnements.apply(
        lambda x: x["quantite_totale"]
    )

    travail["Unite_Etalon"] = conditionnements.apply(
        lambda x: x["unite_standard"]
    )

    travail["Conditionnement_Detecte"] = conditionnements.apply(
        lambda x: x["conditionnement_detecte"]
    )

    travail["Type_Conditionnement"] = conditionnements.apply(
        lambda x: x["type_conditionnement"]
    )

    # ========================================================
    # Produit de base
    # ========================================================

    travail["Produit_Base"] = travail[
        "Produit_Affichage"
    ].apply(
        extraire_produit_base
    )

    # ========================================================
    # Prix comparable
    # ========================================================

    prix_comparables = []
    unites_comparaison = []

    for _, ligne in travail.iterrows():
        prix = ligne["Prix_Numerique"]
        base_prix = ligne["Base_Prix"]

        if base_prix in {
            "KG",
            "LB",
            "OZ",
            "L",
            "ML",
            "GAL",
            "U",
        }:
            prix_direct, unite_directe = convertir_prix_direct(
                prix,
                base_prix,
            )

            prix_comparables.append(prix_direct)
            unites_comparaison.append(unite_directe)

            continue

        prix_comparable = calculer_prix_comparable(
            prix,
            ligne["Quantite_Normalisee"],
            ligne["Unite_Etalon"],
        )

        prix_comparables.append(prix_comparable)
        unites_comparaison.append(
            ligne["Unite_Etalon"]
        )

    travail["Prix_Comparable"] = prix_comparables
    travail["Unite_Comparaison"] = unites_comparaison

    travail["Fournisseur"] = fournisseur

    # ========================================================
    # Nettoyage
    # ========================================================

    travail["Produit_Affichage"] = (
        travail["Produit_Affichage"]
        .replace("nan", "")
        .replace("None", "")
        .str.strip()
    )

    travail["Produit_Base"] = (
        travail["Produit_Base"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    travail = travail[
        travail["Produit_Base"] != ""
    ].copy()

    travail = travail[
        travail["Prix_Numerique"].notna()
        & (travail["Prix_Numerique"] >= 0)
    ].copy()

    colonnes_doublons = [
        "Produit_Base",
        "Prix_Comparable",
        "Conditionnement",
        "Fournisseur",
    ]

    travail = travail.drop_duplicates(
        subset=colonnes_doublons
    )

    return travail.reset_index(drop=True)

# ============================================================
# MATCHING OPTIMISE
# ============================================================

def score_matching(cle_a, cle_b):
    if not cle_a or not cle_b:
        return 0.0

    if cle_a == cle_b:
        return 1.0

    if RAPIDFUZZ_DISPONIBLE:
        score_global = (
            fuzz.ratio(
                cle_a,
                cle_b,
            ) / 100.0
        )

        score_tokens = (
            fuzz.token_set_ratio(
                cle_a,
                cle_b,
            ) / 100.0
        )

        # Le score caractère reste majoritaire pour éviter
        # qu'une chaîne courte incluse dans une chaîne longue
        # soit considérée comme une correspondance quasi parfaite.
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


def token_principal(cle):
    tokens = cle.split()

    if not tokens:
        return ""

    return tokens[0]


def trouver_meilleur_groupe(
    produit,
    unite,
    groupes,
    index_exact,
    index_unite_token,
    index_unite,
):
    cle = cle_produit_fuzzy(produit)

    if not cle:
        return None, 0.0, "nouveau"

    # --------------------------------------------------------
    # 1. Exact global
    # --------------------------------------------------------

    cle_exact = (
        unite,
        cle,
    )

    if cle_exact in index_exact:
        gid = index_exact[cle_exact]
        return gid, 1.0, "exact"

    # --------------------------------------------------------
    # 2. Candidats par unité + premier token
    # --------------------------------------------------------

    token = token_principal(cle)

    candidats = set()

    if token:
        candidats.update(
            index_unite_token.get(
                (unite, token),
                [],
            )
        )

    # --------------------------------------------------------
    # 3. Si pas de candidat, même unité
    # --------------------------------------------------------

    if not candidats:
        candidats.update(
            index_unite.get(
                unite,
                [],
            )
        )

    # --------------------------------------------------------
    # 4. Dernier filet : groupes ayant au moins un token commun
    # --------------------------------------------------------

    if not candidats:
        tokens_produit = set(cle.split())

        for gid, groupe in groupes.items():
            if groupe["unite_etalon"] != unite:
                continue

            tokens_groupe = set(
                groupe["cle"].split()
            )

            if tokens_produit & tokens_groupe:
                candidats.add(gid)

    if not candidats:
        return None, 0.0, "nouveau"

    # --------------------------------------------------------
    # 5. RapidFuzz
    # --------------------------------------------------------

    if RAPIDFUZZ_DISPONIBLE:
        choix = {
            gid: groupes[gid]["cle"]
            for gid in candidats
        }

        resultat = process.extractOne(
            cle,
            choix,
            scorer=fuzz.token_set_ratio,
        )

        if resultat:
            cle_match, _, gid = resultat

            score_final = score_matching(
                cle,
                cle_match,
            )
        else:
            return None, 0.0, "nouveau"

    else:
        meilleur_gid = None
        meilleur_score = 0.0

        for gid in candidats:
            score = score_matching(
                cle,
                groupes[gid]["cle"],
            )

            if score > meilleur_score:
                meilleur_score = score
                meilleur_gid = gid

        gid = meilleur_gid
        score_final = meilleur_score

    # --------------------------------------------------------
    # 7. Classification
    # --------------------------------------------------------

    if score_final >= SEUIL_MATCHING_FORT:
        return gid, score_final, "fort"

    if score_final >= SEUIL_MATCHING_PROBABLE:
        return gid, score_final, "probable"

    return None, score_final, "nouveau"


def appliquer_matching(df):
    df = df.copy()

    groupes = {}

    index_exact = {}
    index_unite_token = {}
    index_unite = {}

    prochain_gid = 0

    groupes_produits = []
    scores = []
    types = []

    for _, ligne in df.iterrows():
        produit = ligne["Produit_Base"]
        unite = ligne["Unite_Comparaison"]

        if not unite or pd.isna(unite):
            groupes_produits.append(np.nan)
            scores.append(0.0)
            types.append("non comparable")
            continue

        # ----------------------------------------------------
        # Cherche un groupe compatible.
        # ----------------------------------------------------

        gid, score, type_match = trouver_meilleur_groupe(
            produit,
            unite,
            groupes,
            index_exact,
            index_unite_token,
            index_unite,
        )

        # ----------------------------------------------------
        # Crée nouveau groupe si nécessaire.
        # ----------------------------------------------------

        if gid is None:
            gid = prochain_gid
            prochain_gid += 1

            cle = cle_produit_fuzzy(produit)

            groupes[gid] = {
                "id": gid,
                "cle": cle,
                "nom": produit,
                "unite_etalon": unite,
            }

            # Index exact.
            index_exact[
                (unite, cle)
            ] = gid

            # Index par unité.
            index_unite.setdefault(
                unite,
                set(),
            ).add(gid)

            # Index par unité + token.
            token = token_principal(cle)

            if token:
                index_unite_token.setdefault(
                    (unite, token),
                    set(),
                ).add(gid)

            score = 1.0
            type_match = "nouveau"

        groupes_produits.append(gid)
        scores.append(score)
        types.append(type_match)

    df["Groupe_Produit"] = groupes_produits
    df["Score_Matching"] = scores
    df["Type_Matching"] = types

    return df, groupes


# ============================================================
# APPLICATION
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
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("⚙️ Configuration")

    region = st.selectbox(
        "Région",
        [
            "France 🇫🇷",
            "Canada 🇨🇦",
        ],
    )

    config = configuration_region(region)

    st.info(
        f"Devise : {config['devise']} "
        f"({config['symbole']})"
    )

    st.markdown("---")

    st.markdown(
        "**Formats acceptés**  \n"
        "Excel · CSV · PDF"
    )

    if RAPIDFUZZ_DISPONIBLE:
        st.success(
            "⚡ RapidFuzz activé pour le matching."
        )
    else:
        st.caption(
            "Matching fuzzy avec fallback Python. "
            "RapidFuzz peut accélérer les gros fichiers."
        )


# ============================================================
# UPLOAD
# ============================================================

st.header("📂 Importer les tarifs fournisseurs")

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
        "Importe au moins un fichier Excel, CSV ou PDF "
        "pour commencer."
    )

    st.markdown(
        """
        ### Comment ça marche ?

        1. 📂 Importe les tarifs fournisseurs
        2. 🔎 OptiMarge détecte produit et prix
        3. 📦 Le conditionnement est normalisé
        4. ⚖️ Les prix sont convertis en €/kg, €/L ou €/u
        5. 🏆 Le meilleur prix comparable est identifié
        """
    )

    st.stop()


# ============================================================
# LECTURE DES FOURNISSEURS
# ============================================================

donnees_fournisseurs = {}

diagnostics_fichiers = []

compteur_fournisseurs = {}


for i, fichier in enumerate(fichiers):
    # --------------------------------------------------------
    # Nom fournisseur
    # --------------------------------------------------------

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

    numero_fournisseur = compteur_fournisseurs[
        nom_base
    ]

    if numero_fournisseur == 1:
        nom_fournisseur = nom_base
    else:
        nom_fournisseur = (
            f"{nom_base} ({numero_fournisseur})"
        )

    # Identifiant réellement unique pour le stockage.
    identifiant_fichier = (
        f"{i}_{fichier.name}"
    )

    with st.expander(
        f"📄 {fichier.name}",
        expanded=True,
    ):
        with st.spinner(
            f"Lecture de {fichier.name}..."
        ):
            dfs, diagnostic = lire_fichier_fournisseur(
                fichier
            )

        diagnostics_fichiers.append(
            {
                "fichier": fichier.name,
                "diagnostic": diagnostic,
            }
        )

        # ----------------------------------------------------
        # Diagnostic fichier
        # ----------------------------------------------------

        if diagnostic.get("message"):
            if "❌" in diagnostic["message"]:
                st.error(
                    diagnostic["message"]
                )
            else:
                st.warning(
                    diagnostic["message"]
                )

        if diagnostic.get("type") == "pdf":
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Pages",
                    diagnostic.get(
                        "pages",
                        0,
                    ),
                )

            with col2:
                st.metric(
                    "Pages texte",
                    diagnostic.get(
                        "pages_avec_texte",
                        0,
                    ),
                )

            with col3:
                st.metric(
                    "Tableaux",
                    diagnostic.get(
                        "tables_detectees",
                        0,
                    ),
                )

        if not dfs:
            st.error(
                "Aucune donnée exploitable dans ce fichier."
            )
            continue

        # ----------------------------------------------------
        # Sélection feuille / tableau
        # ----------------------------------------------------

        if len(dfs) > 1:
            nom_feuille = st.selectbox(
                "Feuille / tableau",
                list(dfs.keys()),
                key=f"feuille_{i}_{fichier.name}",
            )
        else:
            nom_feuille = list(dfs.keys())[0]

        df_brut = dfs[nom_feuille].copy()

        if df_brut.empty:
            st.warning(
                "Cette feuille est vide."
            )
            continue

        st.markdown(
            f"""
            <div class="small-muted">
                Fournisseur détecté : <b>{nom_fournisseur}</b><br>
                Source : {nom_feuille}<br>
                Dimensions : {df_brut.shape[0]} lignes ×
                {df_brut.shape[1]} colonnes
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------
        # Détection colonnes
        # ----------------------------------------------------

        colonne_produit_auto = detecter_colonne_produit(
            df_brut,
            config,
        )

        colonne_prix_auto = detecter_colonne_prix(
            df_brut,
            config,
        )

        colonnes = list(df_brut.columns)

        if not colonnes:
            st.warning(
                "Aucune colonne disponible."
            )
            continue

        # ----------------------------------------------------
        # Sélection produit
        # ----------------------------------------------------

        index_produit = (
            colonnes.index(colonne_produit_auto)
            if colonne_produit_auto in colonnes
            else 0
        )

        colonne_produit = st.selectbox(
            "Colonne produit",
            colonnes,
            index=index_produit,
            key=f"produit_{i}_{fichier.name}",
        )

        # ----------------------------------------------------
        # Sélection prix
        # ----------------------------------------------------

        index_prix = (
            colonnes.index(colonne_prix_auto)
            if colonne_prix_auto in colonnes
            else 0
        )

        colonne_prix = st.selectbox(
            "Colonne prix",
            colonnes,
            index=index_prix,
            key=f"prix_{i}_{fichier.name}",
        )

        # ----------------------------------------------------
        # Aperçu
        # ----------------------------------------------------

        with st.expander(
            "👀 Aperçu des données",
            expanded=False,
        ):
            st.dataframe(
                df_brut.head(10),
                width="stretch",
            )

        # ----------------------------------------------------
        # Préparation
        # ----------------------------------------------------

        try:
            df_propre = preparer_donnees(
                df_brut,
                colonne_produit,
                colonne_prix,
                nom_fournisseur,
                pays=config["pays"],
            )

        except Exception as e:
            st.error(
                f"Erreur lors du nettoyage : {e}"
            )
            continue

        if df_propre.empty:
            st.warning(
                "Aucune offre exploitable après nettoyage."
            )
            continue

        # ----------------------------------------------------
        # Diagnostic conditionnements
        # ----------------------------------------------------

        nb_offres = len(df_propre)

        nb_conditionnements = int(
            df_propre[
                "Conditionnement_Detecte"
            ].sum()
        )

        nb_non_comparables = int(
            df_propre[
                "Prix_Comparable"
            ].isna().sum()
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric(
                "Offres",
                nb_offres,
            )

        with c2:
            st.metric(
                "Conditionnements détectés",
                nb_conditionnements,
            )

        with c3:
            st.metric(
                "Non comparables",
                nb_non_comparables,
            )

        if nb_non_comparables > 0:
            st.warning(
                f"{nb_non_comparables} offre(s) n'ont pas "
                "de prix comparable : conditionnement absent "
                "ou information insuffisante."
            )

        # Identifiant unique : évite toute collision
        # si deux fichiers portent le même nom.
        donnees_fournisseurs[
            identifiant_fichier
        ] = df_propre


# ============================================================
# VERIFICATION
# ============================================================

if not donnees_fournisseurs:
    st.error(
        "Aucun fournisseur exploitable n'a pu être chargé."
    )
    st.stop()


# ============================================================
# FUSION
# ============================================================

df_total = pd.concat(
    list(donnees_fournisseurs.values()),
    ignore_index=True,
)


if df_total.empty:
    st.error(
        "Aucune donnée exploitable après fusion."
    )
    st.stop()


# ============================================================
# MATCHING
# ============================================================

with st.spinner(
    "🔎 Regroupement intelligent des produits..."
):
    df_total, groupes = appliquer_matching(
        df_total
    )


# ============================================================
# OFFRES COMPARABLES
# ============================================================

df_comparable = df_total[
    df_total["Groupe_Produit"].notna()
    & df_total["Prix_Comparable"].notna()
    & df_total["Unite_Comparaison"].notna()
    & (df_total["Prix_Comparable"] >= 0)
].copy()


if df_comparable.empty:
    st.error(
        "Aucune offre comparable n'a été trouvée."
    )
    st.stop()


# ============================================================
# MEILLEURS PRIX
# ============================================================

prix_minimum = (
    df_comparable
    .groupby(
        [
            "Groupe_Produit",
            "Unite_Comparaison",
        ]
    )["Prix_Comparable"]
    .transform("min")
)


resultat = df_comparable[
    df_comparable["Prix_Comparable"]
    == prix_minimum
].copy()


# ============================================================
# NOM CANONIQUE DU PRODUIT
# ============================================================

# Le nom affiché est choisi parmi les offres gagnantes,
# et non plus selon l'ordre d'importation.
#
# En cas d'égalité :
# - on privilégie le libellé le plus court ;
# - puis le nom fournisseur pour rendre le choix déterministe.

noms_groupes = {}

for gid, groupe in resultat.groupby(
    "Groupe_Produit"
):
    groupe = groupe.copy()

    groupe["_longueur_libelle"] = (
        groupe["Produit_Affichage"]
        .astype(str)
        .str.len()
    )

    groupe = groupe.sort_values(
        [
            "_longueur_libelle",
            "Fournisseur",
            "Produit_Affichage",
        ]
    )

    noms_groupes[gid] = (
        groupe.iloc[0]["Produit_Affichage"]
    )


resultat["Produit"] = resultat[
    "Groupe_Produit"
].map(
    noms_groupes
)


# ============================================================
# LABEL PRIX / CONDITIONNEMENT
# ============================================================

resultat["Prix affiché"] = resultat.apply(
    lambda ligne: (
        f"{ligne['Prix_Numerique']:,.2f} "
        f"{config['symbole']}"
    ).replace(",", " "),
    axis=1,
)


resultat["Prix comparable affiché"] = resultat.apply(
    lambda ligne: format_prix_comparable(
        ligne["Prix_Comparable"],
        ligne["Unite_Comparaison"],
        config["symbole"],
    ),
    axis=1,
)


resultat["Conditionnement affiché"] = (
    resultat["Conditionnement"]
    .fillna("")
    .astype(str)
)


# ============================================================
# METRIQUES
# ============================================================

nombre_produits = resultat[
    "Groupe_Produit"
].nunique()

nombre_fournisseurs = df_total[
    "Fournisseur"
].nunique()

nombre_offres = len(df_total)

nombre_non_comparables = int(
    df_total[
        "Prix_Comparable"
    ].isna().sum()
)


groupes_ex_aequo = (
    resultat
    .groupby("Groupe_Produit")["Fournisseur"]
    .nunique()
)

nombre_ex_aequo = int(
    (groupes_ex_aequo > 1).sum()
)


# ============================================================
# RESULTATS
# ============================================================

st.markdown("---")

st.header("🏆 Meilleurs prix")


c1, c2, c3 = st.columns(3)

with c1:
    st.metric(
        "Produits comparés",
        nombre_produits,
    )

with c2:
    st.metric(
        "Fournisseurs",
        nombre_fournisseurs,
    )

with c3:
    st.metric(
        "Offres analysées",
        nombre_offres,
    )


if nombre_ex_aequo > 0:
    st.info(
        f"🤝 {nombre_ex_aequo} produit(s) ont plusieurs "
        "fournisseurs ex æquo au meilleur prix."
    )


if nombre_non_comparables > 0:
    st.warning(
        f"⚠️ {nombre_non_comparables} offre(s) ne peuvent "
        "pas être comparées automatiquement faute de "
        "conditionnement ou de base de prix exploitable."
    )


# ============================================================
# TABLEAU PRINCIPAL
# ============================================================

colonnes_resultat = [
    "Produit",
    "Fournisseur",
    "Produit_Affichage",
    "Prix affiché",
    "Conditionnement affiché",
    "Prix comparable affiché",
    "Type_Matching",
    "Score_Matching",
]

colonnes_resultat = [
    colonne
    for colonne in colonnes_resultat
    if colonne in resultat.columns
]

table_resultat = resultat[
    colonnes_resultat
].copy()

table_resultat = table_resultat.rename(
    columns={
        "Produit_Affichage": "Libellé fournisseur",
        "Type_Matching": "Correspondance",
        "Score_Matching": "Score matching",
    }
)

# Score en pourcentage.
if "Score matching" in table_resultat.columns:
    table_resultat["Score matching"] = (
        table_resultat["Score matching"] * 100
    ).round(1).astype(str) + "%"


st.dataframe(
    table_resultat,
    width="stretch",
    hide_index=True,
)


# ============================================================
# DETAILS
# ============================================================

st.markdown("---")

with st.expander(
    "🔍 Voir le détail des offres gagnantes",
    expanded=False,
):
    colonnes_details = [
        "Produit",
        "Fournisseur",
        "Produit_Affichage",
        "Prix_Brut",
        "Prix_Numerique",
        "Base_Prix",
        "Conditionnement",
        "Quantite_Normalisee",
        "Unite_Comparaison",
        "Prix_Comparable",
        "Type_Conditionnement",
        "Type_Matching",
        "Score_Matching",
    ]

    colonnes_details = [
        colonne
        for colonne in colonnes_details
        if colonne in resultat.columns
    ]

    details = resultat[
        colonnes_details
    ].copy()

    details = details.rename(
        columns={
            "Produit_Affichage": "Libellé fournisseur",
            "Prix_Brut": "Prix fournisseur brut",
            "Prix_Numerique": "Prix numérique",
            "Base_Prix": "Base prix",
            "Conditionnement": "Conditionnement",
            "Quantite_Normalisee": "Quantité normalisée",
            "Unite_Comparaison": "Unité comparaison",
            "Prix_Comparable": "Prix comparable",
            "Type_Conditionnement": "Type conditionnement",
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

offres_non_comparables = df_total[
    df_total["Prix_Comparable"].isna()
].copy()


if not offres_non_comparables.empty:
    st.markdown("---")

    with st.expander(
        f"⚠️ Offres non comparables ({len(offres_non_comparables)})",
        expanded=False,
    ):
        colonnes_non_comparables = [
            "Fournisseur",
            "Produit_Affichage",
            "Prix_Brut",
            "Base_Prix",
            "Conditionnement",
            "Type_Conditionnement",
            "Quantite_Normalisee",
            "Unite_Etalon",
        ]

        colonnes_non_comparables = [
            colonne
            for colonne in colonnes_non_comparables
            if colonne in offres_non_comparables.columns
        ]

        st.dataframe(
            offres_non_comparables[
                colonnes_non_comparables
            ].rename(
                columns={
                    "Produit_Affichage": "Produit",
                    "Prix_Brut": "Prix fournisseur",
                    "Base_Prix": "Base prix",
                    "Type_Conditionnement": "Type conditionnement",
                    "Quantite_Normalisee": "Quantité normalisée",
                    "Unite_Etalon": "Unité détectée",
                }
            ),
            width="stretch",
            hide_index=True,
        )


# ============================================================
# EXPORT CSV
# ============================================================

st.markdown("---")

st.header("📥 Export")


export = resultat.copy()

export["Produit"] = export[
    "Groupe_Produit"
].map(
    noms_groupes
)

colonnes_export = {
    "Produit": "Produit",
    "Fournisseur": "Fournisseur",
    "Produit_Affichage": "Libellé fournisseur",
    "Prix_Numerique": "Prix fournisseur",
    "Base_Prix": "Base prix",
    "Conditionnement": "Conditionnement",
    "Quantite_Normalisee": "Quantité normalisée",
    "Unite_Comparaison": "Unité comparaison",
    "Prix_Comparable": "Prix comparable",
    "Type_Conditionnement": "Type conditionnement",
    "Type_Matching": "Type matching",
    "Score_Matching": "Score matching",
}

colonnes_export_presentes = [
    colonne
    for colonne in colonnes_export
    if colonne in export.columns
]

export = export[
    colonnes_export_presentes
].rename(
    columns=colonnes_export
)

csv_bytes = export.to_csv(
    index=False,
    sep=";",
    encoding="utf-8-sig",
).encode(
    "utf-8-sig"
)

st.download_button(
    label="⬇️ Télécharger les meilleurs prix (CSV)",
    data=csv_bytes,
    file_name="optimarge_meilleurs_prix.csv",
    mime="text/csv",
)


# ============================================================
# EXPORT COMPLET DES OFFRES
# ============================================================

export_complet = df_total.copy()

colonnes_export_complet = [
    "Fournisseur",
    "Produit_Affichage",
    "Produit_Base",
    "Prix_Brut",
    "Prix_Numerique",
    "Base_Prix",
    "Conditionnement",
    "Quantite_Normalisee",
    "Unite_Etalon",
    "Prix_Comparable",
    "Unite_Comparaison",
    "Type_Conditionnement",
    "Groupe_Produit",
    "Type_Matching",
    "Score_Matching",
]

colonnes_export_complet = [
    colonne
    for colonne in colonnes_export_complet
    if colonne in export_complet.columns
]

export_complet = export_complet[
    colonnes_export_complet
].rename(
    columns={
        "Produit_Affichage": "Produit fournisseur",
        "Produit_Base": "Produit normalisé",
        "Prix_Brut": "Prix brut",
        "Prix_Numerique": "Prix numérique",
        "Base_Prix": "Base prix",
        "Quantite_Normalisee": "Quantité normalisée",
        "Unite_Etalon": "Unité étalon",
        "Prix_Comparable": "Prix comparable",
        "Unite_Comparaison": "Unité comparaison",
        "Type_Conditionnement": "Type conditionnement",
        "Groupe_Produit": "Groupe produit",
        "Type_Matching": "Type matching",
        "Score_Matching": "Score matching",
    }
)

csv_complet = export_complet.to_csv(
    index=False,
    sep=";",
    encoding="utf-8-sig",
).encode(
    "utf-8-sig"
)

st.download_button(
    label="⬇️ Télécharger toutes les offres nettoyées",
    data=csv_complet,
    file_name="optimarge_toutes_offres.csv",
    mime="text/csv",
)


# ============================================================
# DIAGNOSTICS TECHNIQUES
# ============================================================

with st.expander(
    "🛠️ Diagnostics techniques",
    expanded=False,
):
    st.write(
        f"**RapidFuzz disponible :** "
        f"{'Oui ⚡' if RAPIDFUZZ_DISPONIBLE else 'Non'}"
    )

    st.write(
        f"**Lignes analysées :** {len(df_total)}"
    )

    st.write(
        f"**Groupes produits :** "
        f"{df_total['Groupe_Produit'].nunique()}"
    )

    st.write(
        f"**Offres comparables :** "
        f"{len(df_comparable)}"
    )

    st.write(
        f"**Offres non comparables :** "
        f"{len(offres_non_comparables)}"
    )

    st.write(
        f"**Fournisseurs :** "
        f"{df_total['Fournisseur'].nunique()}"
    )

    if not RAPIDFUZZ_DISPONIBLE:
        st.caption(
            "Pour accélérer fortement le matching sur plusieurs "
            "milliers de lignes, installe : rapidfuzz"
        )