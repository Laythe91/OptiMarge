import streamlit as st
import pandas as pd
import numpy as np
import re
import unicodedata
import io
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

    .provider-card {
        padding: 0.8rem 1rem;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        margin-bottom: 0.8rem;
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
    "Compare automatiquement les tarifs de tes fournisseurs et identifie "
    "le meilleur prix comparable pour chaque produit."
)


# ============================================================
# OUTILS TEXTE
# ============================================================

def normaliser_texte(texte):
    """Supprime les accents, passe en minuscules et nettoie les espaces."""
    if texte is None:
        return ""

    texte = str(texte)

    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(
        c for c in texte
        if not unicodedata.combining(c)
    )

    texte = texte.lower()
    texte = texte.replace("×", "x")
    texte = re.sub(r"\s+", " ", texte).strip()

    return texte


def normaliser_produit(texte):
    """
    Normalisation du nom de produit.

    Les chiffres du produit sont conservés volontairement.
    Le conditionnement est retiré AVANT cette fonction.
    """
    texte = normaliser_texte(texte)
    texte = texte.upper()

    texte = re.sub(r"[^A-Z0-9À-ÿ]+", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()

    return texte


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

def convertir_prix_international(valeur, pays="FR"):
    """
    Convertit différentes écritures de prix vers un float.

    Exemples :
        12,50
        12.50
        1 234,50
        $12.50
        CA$ 12,50
        €1 234,50
        1,234.50
    """

    if pd.isna(valeur):
        return np.nan

    if isinstance(valeur, (int, float, np.integer, np.floating)):
        valeur = float(valeur)
        return valeur if valeur >= 0 else np.nan

    s = str(valeur).strip()

    if not s:
        return np.nan

    # Retrait des devises et caractères parasites
    s = s.replace("\u00a0", " ")
    s = re.sub(
        r"(CA\$|CAD|USD|EUR|EURO|DOLLARS?|DOLLARS?\s+CANADIENS?|€|\$|£)",
        "",
        s,
        flags=re.IGNORECASE,
    )

    s = s.strip()

    # Ne conserver que chiffres, séparateurs et signe
    s = re.sub(r"[^0-9,\.\-]", "", s)

    if not s:
        return np.nan

    if s.count("-") > 0:
        if not s.startswith("-"):
            return np.nan

    try:
        # Cas avec virgule ET point
        if "," in s and "." in s:
            derniere_virgule = s.rfind(",")
            dernier_point = s.rfind(".")

            if derniere_virgule > dernier_point:
                # 1.234,56
                s = s.replace(".", "")
                s = s.replace(",", ".")
            else:
                # 1,234.56
                s = s.replace(",", "")

        # Seulement virgule
        elif "," in s:
            morceaux = s.split(",")

            if len(morceaux) > 2:
                # 1,234,567
                s = "".join(morceaux)
            else:
                avant, apres = morceaux

                if len(apres) == 3 and pays == "CA":
                    # Cas canadien possible : 1,234
                    s = avant + apres
                else:
                    # 12,50
                    s = avant + "." + apres

        # Seulement plusieurs points
        elif s.count(".") > 1:
            morceaux = s.split(".")

            # 1.234.567 -> 1234567
            s = "".join(morceaux)

        resultat = float(s)

        if resultat < 0:
            return np.nan

        return resultat

    except (ValueError, TypeError):
        return np.nan


# ============================================================
# CONDITIONNEMENT
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
    "floz": ("L", 0.0295735295625),
    "fl oz": ("L", 0.0295735295625),
    "fluidounce": ("L", 0.0295735295625),
    "fluidounces": ("L", 0.0295735295625),
    "gal": ("L", 3.785411784),
    "gallon": ("L", 3.785411784),
    "gallons": ("L", 3.785411784),
}

MOTS_UNITE = [
    "u",
    "unite",
    "unites",
    "unit",
    "units",
    "piece",
    "pieces",
    "pc",
    "pcs",
    "piece(s)",
    "bte",
    "boite",
    "boites",
    "box",
    "boxes",
    "bottle",
    "bottles",
    "btl",
    "can",
    "cans",
    "tin",
    "tins",
    "sac",
    "sacs",
    "bag",
    "bags",
]

MOTS_COLIS = [
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


def normaliser_unite(quantite, unite):
    """Convertit une quantité vers KG, L ou U."""

    unite = normaliser_texte(unite)
    unite = unite.replace(" ", "")

    # Masse
    if unite in UNITE_MASSE:
        unite_standard, facteur = UNITE_MASSE[unite]
        return quantite * facteur, unite_standard

    # Volume
    if unite in UNITE_VOLUME:
        unite_standard, facteur = UNITE_VOLUME[unite]
        return quantite * facteur, unite_standard

    return quantite, "U"


def extraire_conditionnement(libelle):
    """
    Extrait le conditionnement d'un libellé.

    Formats pris en charge notamment :

        500 g
        1 kg
        2 lb
        16 oz
        750 ml
        1 L
        12 x 355 ml
        12X355ML
        6 × 1 L
        4 x 2.5 kg
        6/750 ml
        12/1 L
        24/355 ml
        2 x 5 gal
        pack de 6
        pack of 6
        case of 24
        caisse de 24
        24 pcs
        24 pieces
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
    s = normaliser_texte(original)

    # --------------------------------------------------------
    # Sécurité :
    # remplacement de virgule décimale
    # --------------------------------------------------------

    s = s.replace(",", ".")

    # --------------------------------------------------------
    # 1. MULTIPACK :
    # 12 x 355 ml
    # 12x355ml
    # 6 * 1 kg
    # 6/750 ml
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
        nb = float(match.group("nb"))
        qte = float(match.group("qte"))
        unite = match.group("unite").lower()

        quantite_totale, unite_standard = normaliser_unite(
            nb * qte,
            unite,
        )

        texte = match.group(0)

        return {
            "conditionnement_original": original,
            "quantite_totale": quantite_totale,
            "unite_standard": unite_standard,
            "conditionnement_detecte": True,
            "texte_conditionnement": texte,
            "type_conditionnement": "multipack",
        }

    # --------------------------------------------------------
    # Format fraction :
    # 6/750 ml
    # 12/1 L
    # 24/355 ml
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
        nb = float(match.group("nb"))
        qte = float(match.group("qte"))
        unite = match.group("unite").lower()

        quantite_totale, unite_standard = normaliser_unite(
            nb * qte,
            unite,
        )

        texte = match.group(0)

        return {
            "conditionnement_original": original,
            "quantite_totale": quantite_totale,
            "unite_standard": unite_standard,
            "conditionnement_detecte": True,
            "texte_conditionnement": texte,
            "type_conditionnement": "multipack",
        }

    # --------------------------------------------------------
    # 2. SIMPLE :
    # 500 g
    # 2 kg
    # 750 ml
    # 1 L
    # 16 oz
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
        qte = float(match.group("qte"))
        unite = match.group("unite").lower()

        quantite_totale, unite_standard = normaliser_unite(
            qte,
            unite,
        )

        texte = match.group(0)

        return {
            "conditionnement_original": original,
            "quantite_totale": quantite_totale,
            "unite_standard": unite_standard,
            "conditionnement_detecte": True,
            "texte_conditionnement": texte,
            "type_conditionnement": "simple",
        }

    # --------------------------------------------------------
    # 3. "PACK DE 6"
    # "PACK OF 6"
    # "CASE OF 24"
    # "CAISSE DE 24"
    # --------------------------------------------------------

    mots_colis_regex = "|".join(
        re.escape(mot) for mot in MOTS_COLIS
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
        nb = float(match.group("nb"))

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
    # 4. "24 PCS", "24 UNITS", "24 PIECES"
    # --------------------------------------------------------

    regex_unites_explicit = re.compile(
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

    match = regex_unites_explicit.search(s)

    if match:
        nb = float(match.group("nb"))

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
    # 5. "12 BOTTLES", "24 CANS", "6 BAGS"
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
        re.escape(mot) for mot in mots_comptage
    )

    regex_comptage = re.compile(
        rf"""
        (?P<nb>\d+(?:\.\d+)?)
        \s*
        (?P<unite>{mots_comptage_regex})
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = regex_comptage.search(s)

    if match:
        nb = float(match.group("nb"))

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
    # 6. Aucun conditionnement détecté
    # --------------------------------------------------------

    return {
        "conditionnement_original": original,
        "quantite_totale": np.nan,
        "unite_standard": None,
        "conditionnement_detecte": False,
        "texte_conditionnement": "",
        "type_conditionnement": "inconnu",
    }


def extraire_produit_base(libelle):
    """
    Retire uniquement le texte du conditionnement détecté.

    Exemple :
        "Jus orange 12 x 1 L"
        -> "Jus orange"

    Cela permet de comparer :
        Jus orange 12 x 1 L
        Jus orange 6 x 1 L
        Jus orange 5 L
    comme un même produit.
    """

    if libelle is None or pd.isna(libelle):
        return ""

    original = str(libelle)

    info = extraire_conditionnement(original)

    texte_conditionnement = info["texte_conditionnement"]

    if not texte_conditionnement:
        return normaliser_produit(original)

    base = original.replace(
        texte_conditionnement,
        " ",
        1,
    )

    base = re.sub(r"\s+", " ", base).strip()

    # Nettoyage de séparateurs restants
    base = re.sub(r"[\-_/|]+$", "", base).strip()
    base = re.sub(r"^[\-_/|]+", "", base).strip()

    return normaliser_produit(base)


def formater_conditionnement(quantite, unite):
    """Format d'affichage lisible."""

    if pd.isna(quantite) or not unite:
        return "Non détecté"

    if unite == "KG":
        if quantite >= 1:
            valeur = quantite
            return f"{valeur:g} kg"
        return f"{quantite * 1000:g} g"

    if unite == "L":
        if quantite >= 1:
            return f"{quantite:g} L"
        return f"{quantite * 1000:g} ml"

    if unite == "U":
        return f"{quantite:g} U"

    return f"{quantite:g} {unite}"


def calculer_prix_comparable(prix, quantite, unite):
    """
    Calcule le prix selon l'unité étalon :

        KG -> prix/kg
        L  -> prix/L
        U  -> prix/U
    """

    if pd.isna(prix):
        return np.nan

    if pd.isna(quantite):
        return np.nan

    if quantite <= 0:
        return np.nan

    return prix / quantite


def format_prix_comparable(prix, unite, symbole):
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
# DETECTION DES COLONNES
# ============================================================

def score_colonne_produit(nom_colonne, config):
    nom = normaliser_texte(nom_colonne)

    score = 0

    for mot in config["mots_produit"]:
        mot = normaliser_texte(mot)

        if nom == mot:
            score += 100
        elif mot in nom:
            score += 50

    return score


def score_colonne_prix(nom_colonne, config):
    nom = normaliser_texte(nom_colonne)

    score = 0

    for mot in config["mots_prix"]:
        mot = normaliser_texte(mot)

        if nom == mot:
            score += 100
        elif mot in nom:
            score += 50

    # Bonus pour les indicateurs monétaires
    if any(x in nom for x in ["€", "$", "eur", "cad", "price", "prix"]):
        score += 15

    return score


def detecter_colonnes(df, config):
    colonnes = list(df.columns)

    if not colonnes:
        return None, None

    scores_produit = {
        col: score_colonne_produit(col, config)
        for col in colonnes
    }

    scores_prix = {
        col: score_colonne_prix(col, config)
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

    if scores_produit[colonne_produit] == 0:
        colonne_produit = colonnes[0]

    if scores_prix[colonne_prix] == 0:
        colonnes_numeriques = []

        for col in colonnes:
            valeurs = pd.to_numeric(
                df[col],
                errors="coerce",
            )

            if valeurs.notna().sum() > 0:
                colonnes_numeriques.append(col)

        if colonnes_numeriques:
            colonne_prix = max(
                colonnes_numeriques,
                key=lambda c: pd.to_numeric(
                    df[c],
                    errors="coerce",
                ).notna().sum(),
            )
        else:
            colonne_prix = colonnes[-1]

    # Si la même colonne a été détectée pour les deux,
    # chercher une autre colonne prix.
    if colonne_produit == colonne_prix:
        alternatives = [
            col for col in colonnes
            if col != colonne_produit
            and scores_prix[col] > 0
        ]

        if alternatives:
            colonne_prix = max(
                alternatives,
                key=scores_prix.get,
            )

    return colonne_produit, colonne_prix


# ============================================================
# LECTURE EXCEL
# ============================================================

@st.cache_data(show_spinner=False)
def lire_excel(contenu_bytes):
    dfs = {}

    with pd.ExcelFile(io.BytesIO(contenu_bytes)) as excel:
        for feuille in excel.sheet_names:
            try:
                df = excel.parse(feuille)

                if df is not None and not df.empty:
                    dfs[feuille] = df

            except Exception:
                continue

    return dfs


# ============================================================
# LECTURE CSV
# ============================================================

@st.cache_data(show_spinner=False)
def lire_csv(contenu_bytes):
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
                io.BytesIO(contenu_bytes),
                encoding=encodage,
                sep=separateur,
            )

            if df.shape[1] >= 2:
                return {"CSV": df}

        except Exception:
            continue

    # Dernière tentative avec autodétection
    for encodage in ["utf-8", "utf-8-sig", "cp1252", "latin1"]:
        try:
            df = pd.read_csv(
                io.BytesIO(contenu_bytes),
                encoding=encodage,
                sep=None,
                engine="python",
            )

            if df.shape[1] >= 1:
                return {"CSV": df}

        except Exception:
            continue

    return {}


# ============================================================
# PDF
# ============================================================

def nettoyer_table_pdf(table):
    if not table:
        return None

    lignes = []

    for ligne in table:
        if not ligne:
            continue

        ligne_nettoyee = [
            "" if valeur is None else str(valeur).strip()
            for valeur in ligne
        ]

        if any(ligne_nettoyee):
            lignes.append(ligne_nettoyee)

    if len(lignes) < 2:
        return None

    premiere_ligne = lignes[0]

    # Si première ligne ressemble à des en-têtes
    colonnes = []

    for i, valeur in enumerate(premiere_ligne):
        nom = valeur if valeur else f"Colonne_{i + 1}"
        colonnes.append(nom)

    donnees = lignes[1:]

    largeur = len(colonnes)

    donnees_corrigees = []

    for ligne in donnees:
        if len(ligne) < largeur:
            ligne = ligne + [""] * (largeur - len(ligne))

        elif len(ligne) > largeur:
            ligne = ligne[:largeur]

        donnees_corrigees.append(ligne)

    return pd.DataFrame(
        donnees_corrigees,
        columns=colonnes,
    )


@st.cache_data(show_spinner=False)
def lire_pdf(contenu_bytes):
    dfs = {}

    try:
        with pdfplumber.open(io.BytesIO(contenu_bytes)) as pdf:
            compteur = 1

            for page in pdf.pages:
                try:
                    tables = page.extract_tables()

                    for table in tables:
                        df = nettoyer_table_pdf(table)

                        if df is not None and not df.empty:
                            dfs[f"Page {page.page_number} - Tableau {compteur}"] = df
                            compteur += 1

                except Exception:
                    continue

    except Exception:
        return {}

    return dfs


# ============================================================
# LECTURE GENERALE
# ============================================================

def lire_fichier_fournisseur(fichier):
    extension = fichier.name.lower().split(".")[-1]
    contenu_bytes = fichier.getvalue()

    if extension in ["xlsx", "xls"]:
        return lire_excel(contenu_bytes)

    if extension == "csv":
        return lire_csv(contenu_bytes)

    if extension == "pdf":
        return lire_pdf(contenu_bytes)

    return {}


# ============================================================
# PREPARATION DES DONNEES
# ============================================================

def preparer_donnees(
    df,
    colonne_produit,
    colonne_prix,
    fournisseur,
    pays,
):
    travail = df.copy()

    travail["Produit_Affichage"] = (
        travail[colonne_produit]
        .astype(str)
        .str.strip()
    )

    travail["Prix_Unitaire"] = travail[colonne_prix].apply(
        lambda x: convertir_prix_international(
            x,
            pays=pays,
        )
    )

    # Extraction du conditionnement
    infos_conditionnement = travail["Produit_Affichage"].apply(
        extraire_conditionnement
    )

    travail["Conditionnement"] = infos_conditionnement.apply(
        lambda x: x["conditionnement_original"]
    )

    travail["Quantite_Normalisee"] = infos_conditionnement.apply(
        lambda x: x["quantite_totale"]
    )

    travail["Unite_Etalon"] = infos_conditionnement.apply(
        lambda x: x["unite_standard"]
    )

    travail["Conditionnement_Detecte"] = infos_conditionnement.apply(
        lambda x: x["conditionnement_detecte"]
    )

    travail["Type_Conditionnement"] = infos_conditionnement.apply(
        lambda x: x["type_conditionnement"]
    )

    travail["Produit_Base"] = travail["Produit_Affichage"].apply(
        extraire_produit_base
    )

    # Prix comparable
    travail["Prix_Comparable"] = travail.apply(
        lambda ligne: calculer_prix_comparable(
            ligne["Prix_Unitaire"],
            ligne["Quantite_Normalisee"],
            ligne["Unite_Etalon"],
        ),
        axis=1,
    )

    travail["Fournisseur"] = fournisseur

    # On garde les informations utiles
    colonnes = [
        "Produit_Affichage",
        "Produit_Base",
        "Prix_Unitaire",
        "Conditionnement",
        "Quantite_Normalisee",
        "Unite_Etalon",
        "Conditionnement_Detecte",
        "Type_Conditionnement",
        "Prix_Comparable",
        "Fournisseur",
    ]

    travail = travail[colonnes].copy()

    # Produit vide
    travail = travail[
        travail["Produit_Base"].notna()
        & (travail["Produit_Base"].astype(str).str.strip() != "")
    ]

    # Prix valide
    travail = travail[
        travail["Prix_Unitaire"].notna()
        & (travail["Prix_Unitaire"] >= 0)
    ]

    # Doublons exacts
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
    st.header("⚙️ Configuration")

    region = st.selectbox(
        "Région",
        [
            "🇫🇷 France",
            "🇨🇦 Canada",
        ],
    )

    config = configuration_region(region)

    st.info(
        f"Devise : **{config['devise']} ({config['symbole']})**"
    )

    st.markdown("---")

    st.markdown(
        """
        **Comparaison normalisée**

        Les prix sont ramenés automatiquement à :
        - €/kg ou CA$/kg
        - €/L ou CA$/L
        - €/U ou CA$/U

        Les produits sans conditionnement détecté sont signalés.
        """
    )


# ============================================================
# IMPORT
# ============================================================

st.subheader("📥 Importer les tarifs fournisseurs")

fichiers = st.file_uploader(
    "Dépose tes fichiers ici",
    type=["xlsx", "xls", "csv", "pdf"],
    accept_multiple_files=True,
    help="Excel, CSV et PDF sont acceptés.",
)


# ============================================================
# PAS DE FICHIER
# ============================================================

if not fichiers:
    st.info(
        "👆 Importe les tarifs de tes fournisseurs pour commencer."
    )

    st.markdown(
        """
        ### Exemples de formats acceptés

        **Excel / CSV**

        | Produit | Prix |
        |---|---:|
        | Jus orange 12 x 1 L | 18,00 |
        | Jus orange 6 x 1 L | 10,50 |
        | Jus orange 5 L | 7,50 |

        **Conditionnements reconnus**

        `500 g` · `1 kg` · `2 lb` · `750 ml` · `1 L`  
        `12 x 355 ml` · `6 x 1 L` · `4 x 2,5 kg`  
        `6/750 ml` · `case of 24` · `pack de 6` · `24 pcs`
        """
    )

    st.stop()


# ============================================================
# TRAITEMENT FOURNISSEURS
# ============================================================

donnees_fournisseurs = {}
diagnostics_globaux = []

for fichier in fichiers:

    nom_fournisseur = fichier.name.rsplit(".", 1)[0]

    with st.container(border=True):
        st.markdown(
            f"### 🏪 {nom_fournisseur}"
        )

        try:
            feuilles = lire_fichier_fournisseur(fichier)

        except Exception as e:
            st.error(
                f"Impossible de lire **{fichier.name}** : {e}"
            )
            continue

        if not feuilles:
            st.error(
                "Aucune donnée exploitable n'a été trouvée."
            )
            continue

        noms_feuilles = list(feuilles.keys())

        if len(noms_feuilles) > 1:
            feuille_selectionnee = st.selectbox(
                "Feuille / tableau",
                noms_feuilles,
                key=f"feuille_{fichier.name}",
            )
        else:
            feuille_selectionnee = noms_feuilles[0]

        df_brut = feuilles[feuille_selectionnee].copy()

        if df_brut.empty:
            st.warning("Le tableau est vide.")
            continue

        colonne_produit_auto, colonne_prix_auto = detecter_colonnes(
            df_brut,
            config,
        )

        st.markdown(
            '<div class="small-muted">Colonnes détectées automatiquement</div>',
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)

        with col1:
            colonne_produit = st.selectbox(
                "Colonne produit",
                list(df_brut.columns),
                index=list(df_brut.columns).index(
                    colonne_produit_auto
                ),
                key=f"produit_{fichier.name}",
            )

        with col2:
            colonne_prix = st.selectbox(
                "Colonne prix",
                list(df_brut.columns),
                index=list(df_brut.columns).index(
                    colonne_prix_auto
                ),
                key=f"prix_{fichier.name}",
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

        nombre_lignes = len(df_propre)
        nombre_conditionnements = int(
            df_propre["Conditionnement_Detecte"].sum()
        )
        nombre_non_detectes = (
            nombre_lignes - nombre_conditionnements
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Lignes valides",
            f"{nombre_lignes:,}",
        )

        c2.metric(
            "Conditionnements détectés",
            f"{nombre_conditionnements:,}",
        )

        c3.metric(
            "Non détectés",
            f"{nombre_non_detectes:,}",
        )

        if nombre_non_detectes > 0:
            st.warning(
                f"⚠️ {nombre_non_detectes} ligne(s) n'ont pas "
                "de conditionnement détecté. "
                "Elles ne seront pas utilisées pour calculer "
                "un prix au kg/L/U."
            )

        donnees_fournisseurs[fichier.name] = df_propre

        diagnostics_globaux.append(
            {
                "Fournisseur": nom_fournisseur,
                "Lignes valides": nombre_lignes,
                "Conditionnements détectés": nombre_conditionnements,
                "Conditionnements manquants": nombre_non_detectes,
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
# COMPARAISON
# ============================================================

st.markdown("---")
st.subheader("🏆 Meilleurs prix comparables")


# On compare uniquement les lignes ayant :
# - un conditionnement détecté
# - une unité étalon
# - un prix comparable

df_comparable = df_total[
    df_total["Conditionnement_Detecte"]
    & df_total["Unite_Etalon"].notna()
    & df_total["Prix_Comparable"].notna()
    & (df_total["Prix_Comparable"] >= 0)
].copy()


if df_comparable.empty:
    st.error(
        "Aucun prix comparable n'a pu être calculé. "
        "Vérifie les colonnes produit/prix et les conditionnements."
    )
    st.stop()


# ------------------------------------------------------------
# IMPORTANT :
# On ne mélange JAMAIS KG, L et U.
#
# Exemple :
#   poulet  -> 2 KG
#   poulet  -> 2 L
#
# sont considérés comme deux bases de comparaison différentes.
# ------------------------------------------------------------

groupes = [
    "Produit_Base",
    "Unite_Etalon",
]


prix_minimum = (
    df_comparable
    .groupby(groupes)["Prix_Comparable"]
    .transform("min")
)


resultat = df_comparable[
    df_comparable["Prix_Comparable"] == prix_minimum
].copy()


# ============================================================
# EX AEQUO
# ============================================================

nombre_produits = resultat["Produit_Base"].nunique()

nombre_fournisseurs = df_total["Fournisseur"].nunique()

nombre_offres = len(df_total)

ex_aequo_par_produit = (
    resultat
    .groupby(["Produit_Base", "Unite_Etalon"])
    ["Fournisseur"]
    .nunique()
)

nombre_ex_aequo = int(
    (ex_aequo_par_produit > 1).sum()
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
# PREPARATION AFFICHAGE
# ============================================================

resultat = resultat.copy()

resultat["Prix affiché"] = resultat.apply(
    lambda ligne: (
        f"{ligne['Prix_Unitaire']:.2f} {config['symbole']}"
    ),
    axis=1,
)

resultat["Conditionnement affiché"] = resultat.apply(
    lambda ligne: formater_conditionnement(
        ligne["Quantite_Normalisee"],
        ligne["Unite_Etalon"],
    ),
    axis=1,
)

resultat["Prix comparable affiché"] = resultat.apply(
    lambda ligne: format_prix_comparable(
        ligne["Prix_Comparable"],
        ligne["Unite_Etalon"],
        config["symbole"],
    ),
    axis=1,
)

resultat["Détection"] = resultat[
    "Conditionnement_Detecte"
].map(
    {
        True: "✓ Détecté",
        False: "⚠ Non détecté",
    }
)


resultat = resultat.sort_values(
    by=[
        "Produit_Base",
        "Prix_Comparable",
        "Fournisseur",
    ],
    ascending=[
        True,
        True,
        True,
    ],
)


# ============================================================
# TABLEAU RESULTATS
# ============================================================

colonnes_affichage = [
    "Produit_Base",
    "Fournisseur",
    "Prix affiché",
    "Conditionnement affiché",
    "Prix comparable affiché",
    "Détection",
]


st.dataframe(
    resultat[colonnes_affichage],
    width="stretch",
    hide_index=True,
    column_config={
        "Produit_Base": st.column_config.TextColumn(
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
        "Détection": st.column_config.TextColumn(
            "Conditionnement",
            width="small",
        ),
    },
)


# ============================================================
# DETAIL DES CALCULS
# ============================================================

with st.expander(
    "🧮 Voir les détails des calculs",
    expanded=False,
):
    details = resultat[
        [
            "Produit_Affichage",
            "Produit_Base",
            "Fournisseur",
            "Prix_Unitaire",
            "Conditionnement",
            "Quantite_Normalisee",
            "Unite_Etalon",
            "Prix_Comparable",
            "Type_Conditionnement",
        ]
    ].copy()

    details["Prix_Unitaire"] = details[
        "Prix_Unitaire"
    ].round(4)

    details["Quantite_Normalisee"] = details[
        "Quantite_Normalisee"
    ].round(6)

    details["Prix_Comparable"] = details[
        "Prix_Comparable"
    ].round(4)

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
        "Produit_Base",
        "Fournisseur",
        "Prix_Unitaire",
        "Conditionnement",
        "Quantite_Normalisee",
        "Unite_Etalon",
        "Prix_Comparable",
    ]
].copy()

export = export.rename(
    columns={
        "Produit_Base": "Produit",
        "Prix_Unitaire": f"Prix fournisseur ({config['devise']})",
        "Quantite_Normalisee": "Quantite normalisee",
        "Unite_Etalon": "Unite etalon",
        "Prix_Comparable": f"Prix comparable ({config['devise']})",
    }
)

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
    f"✅ Comparaison terminée : {nombre_produits} produit(s), "
    f"{nombre_fournisseurs} fournisseur(s), "
    f"{nombre_offres} offre(s) analysée(s)."
)