import streamlit as st
import pandas as pd
import numpy as np
import re
import unicodedata
import io
import pdfplumber


# ============================================================
# CONFIGURATION STREAMLIT
# ============================================================

st.set_page_config(
    page_title="OptiMarge - Comparateur Instantané",
    page_icon="🛒",
    layout="wide",
)


# ============================================================
# CSS — MOBILE FIRST
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .main-title {
        font-size: clamp(1.8rem, 5vw, 3rem);
        font-weight: 800;
        line-height: 1.1;
        margin-bottom: 0.35rem;
    }

    .small-muted {
        color: #777;
        font-size: 0.85rem;
    }

    .provider-card {
        padding: 0.8rem;
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        margin-bottom: 0.5rem;
    }

    div.stButton > button,
    div.stDownloadButton > button {
        width: 100%;
        min-height: 3.1rem;
    }

    [data-testid="stFileUploader"] {
        border-radius: 12px;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.7rem;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.9rem;
    }

    @media (max-width: 600px) {

        .block-container {
            padding-top: 1rem;
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }

        .main-title {
            font-size: 1.8rem;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.5rem;
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
    "et identifie le meilleur prix pour chaque produit."
)


# ============================================================
# NORMALISATION DU TEXTE
# ============================================================

def normaliser_texte(texte):
    """
    Normalise un texte :
    - suppression des accents
    - passage en minuscules
    - suppression des espaces inutiles
    """

    if pd.isna(texte):
        return ""

    texte = str(texte).strip().lower()

    texte = unicodedata.normalize(
        "NFKD",
        texte
    )

    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(caractere)
    )

    texte = re.sub(
        r"\s+",
        " ",
        texte
    )

    return texte.strip()


# ============================================================
# NORMALISATION DES PRODUITS
# ============================================================

def normaliser_produit(produit):
    """
    Normalisation volontairement légère.

    Exemple :
        "Poulet Fermier"
        "poulet   fermier"
        "POULET FERMIER"

    deviennent la même clé.

    ATTENTION :
    Le conditionnement n'est pas encore pris en compte.

    Exemple :
        500 g
        1 kg

    sont donc encore considérés comme le même produit.
    """

    s = normaliser_texte(produit)

    s = re.sub(
        r"[^a-z0-9]+",
        " ",
        s
    )

    s = re.sub(
        r"\s+",
        " ",
        s
    ).strip()

    return s.upper()


# ============================================================
# CONFIGURATION DES RÉGIONS
# ============================================================

def configuration_region(region):

    # ========================================================
    # FRANCE
    # ========================================================

    if region == "France 🇫🇷":

        return {
            "pays": "FR",
            "devise": "EUR",
            "symbole": "€",

            "mots_prix": [
                "prix",
                "tarif",
                "cout",
                "coût",
                "prix unitaire",
                "tarif unitaire",
                "pu",
                "p.u",
                "ht",
                "prix ht",
                "tarif ht",
                "montant",
                "prix achat",
                "prix fournisseur",
            ],

            "mots_produit": [
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
                "sku",
            ],
        }

    # ========================================================
    # CANADA
    # ========================================================

    return {
        "pays": "CA",
        "devise": "CAD",
        "symbole": "CA$",

        # Français + anglais
        "mots_prix": [
            "prix",
            "tarif",
            "cout",
            "coût",
            "prix unitaire",
            "tarif unitaire",
            "prix ht",
            "prix hors taxe",
            "pu",
            "price",
            "unit price",
            "unit cost",
            "cost",
            "wholesale price",
            "wholesale",
            "net price",
            "net cost",
            "sale price",
            "amount",
            "purchase price",
            "supplier price",
        ],

        "mots_produit": [
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
            "product",
            "product name",
            "product description",
            "sku",
            "item number",
            "item name",
        ],
    }


# ============================================================
# CONVERSION DES PRIX
# ============================================================

def convertir_prix_international(
    valeur,
    pays="FR",
):
    """
    Convertit plusieurs formats de prix.

    France :
        12,50
        12.50
        12,50 €
        €12,50
        1 234,50 €

    Canada :
        $12.50
        CA$12.50
        C$12.50
        12.50 CAD
        1,234.50
        1 234,50

    Retourne un float ou np.nan.
    """

    if pd.isna(valeur):
        return np.nan

    texte = str(valeur).strip()

    if not texte:
        return np.nan

    # Espaces spéciaux
    texte = texte.replace("\u00a0", " ")
    texte = texte.replace("\u202f", " ")

    # Passage en majuscules
    texte = texte.upper()

    # --------------------------------------------------------
    # Suppression des devises
    # --------------------------------------------------------

    devises = [
        "EUR",
        "EURO",
        "EUROS",
        "CAD",
        "CAN$",
        "CA$",
        "C$",
        "$",
        "€",
    ]

    for devise in devises:
        texte = texte.replace(
            devise,
            ""
        )

    texte = texte.strip()

    # --------------------------------------------------------
    # Conservation des caractères numériques
    # --------------------------------------------------------

    texte = re.sub(
        r"[^0-9,\.\-\s]",
        "",
        texte
    )

    texte = texte.strip()

    if not texte:
        return np.nan

    # Suppression des espaces
    texte = re.sub(
        r"\s+",
        "",
        texte
    )

    # ========================================================
    # CAS 1 :
    # POINT + VIRGULE
    # ========================================================

    if "," in texte and "." in texte:

        derniere_virgule = texte.rfind(",")
        dernier_point = texte.rfind(".")

        # 1.234,56
        if derniere_virgule > dernier_point:

            texte = texte.replace(
                ".",
                ""
            )

            texte = texte.replace(
                ",",
                "."
            )

        # 1,234.56
        else:

            texte = texte.replace(
                ",",
                ""
            )

    # ========================================================
    # CAS 2 :
    # UNIQUEMENT VIRGULE
    # ========================================================

    elif "," in texte:

        morceaux = texte.split(",")

        if len(morceaux) == 2:

            partie_avant = morceaux[0]
            partie_apres = morceaux[1]

            # Canada :
            # 1,234 peut représenter 1234.
            if (
                pays == "CA"
                and len(partie_apres) == 3
                and partie_avant.isdigit()
                and partie_apres.isdigit()
            ):

                texte = texte.replace(
                    ",",
                    ""
                )

            else:

                # 12,50 -> 12.50
                texte = texte.replace(
                    ",",
                    "."
                )

        else:

            # 1,234,567
            texte = texte.replace(
                ",",
                ""
            )

    # ========================================================
    # CAS 3 :
    # UNIQUEMENT POINT
    # ========================================================

    elif "." in texte:

        morceaux = texte.split(".")

        if len(morceaux) > 2:

            # 1.234.567
            texte = texte.replace(
                ".",
                ""
            )

    # ========================================================
    # CONVERSION
    # ========================================================

    try:

        prix = float(texte)

        if prix < 0:
            return np.nan

        return prix

    except (
        ValueError,
        TypeError,
    ):

        return np.nan


# ============================================================
# SCORE COLONNE PRODUIT
# ============================================================

def score_colonne_produit(
    colonne,
    config,
):

    nom = normaliser_texte(
        colonne
    )

    score = 0

    for mot in config["mots_produit"]:

        mot_normalise = normaliser_texte(
            mot
        )

        if nom == mot_normalise:

            score += 100

        elif mot_normalise in nom:

            score += 30

    termes_bonus = [
        "produit",
        "product",
        "designation",
        "description",
        "article",
        "item",
        "sku",
    ]

    for terme in termes_bonus:

        if terme in nom:

            score += 20

    return score


# ============================================================
# SCORE COLONNE PRIX
# ============================================================

def score_colonne_prix(
    colonne,
    config,
):

    nom = normaliser_texte(
        colonne
    )

    score = 0

    for mot in config["mots_prix"]:

        mot_normalise = normaliser_texte(
            mot
        )

        if nom == mot_normalise:

            score += 100

        elif mot_normalise in nom:

            score += 30

    termes_bonus = [
        "prix",
        "price",
        "tarif",
        "cost",
        "cout",
        "pu",
        "unit price",
        "unit cost",
    ]

    for terme in termes_bonus:

        if terme in nom:

            score += 20

    return score


# ============================================================
# DÉTECTION AUTOMATIQUE DES COLONNES
# ============================================================

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
            []
        )

    scores_produit = {
        col: score_colonne_produit(
            col,
            config
        )
        for col in colonnes
    }

    scores_prix = {
        col: score_colonne_prix(
            col,
            config
        )
        for col in colonnes
    }

    col_produit = max(
        colonnes,
        key=lambda c: scores_produit[c]
    )

    col_prix = max(
        colonnes,
        key=lambda c: scores_prix[c]
    )

    # Évite d'utiliser la même colonne
    # pour le produit et le prix.
    if (
        col_produit == col_prix
        and len(colonnes) > 1
    ):

        autres = [
            col
            for col in colonnes
            if col != col_produit
        ]

        col_prix = max(
            autres,
            key=lambda c: scores_prix[c]
        )

    diagnostics = [
        {
            "Colonne": col,
            "Score Produit": scores_produit[col],
            "Score Prix": scores_prix[col],
        }
        for col in colonnes
    ]

    return (
        col_produit,
        col_prix,
        diagnostics
    )


# ============================================================
# LECTURE EXCEL
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_excel(
    contenu_bytes
):

    try:

        # Le context manager ferme proprement
        # le lecteur Excel après utilisation.
        with pd.ExcelFile(
            io.BytesIO(contenu_bytes)
        ) as excel:

            for feuille in excel.sheet_names:

                try:

                    df = excel.parse(
                        feuille
                    )

                    df = df.dropna(
                        how="all"
                    )

                    if (
                        df.shape[1] >= 2
                        and not df.empty
                    ):

                        return df

                except Exception:

                    continue

    except Exception:

        return pd.DataFrame()

    return pd.DataFrame()


# ============================================================
# LECTURE CSV
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_csv(
    contenu_bytes
):

    essais = [

        # France / Europe
        ("utf-8-sig", ";"),
        ("utf-8", ";"),
        ("latin1", ";"),
        ("cp1252", ";"),

        # Canada / Amérique du Nord
        ("utf-8-sig", ","),
        ("utf-8", ","),
        ("latin1", ","),
        ("cp1252", ","),
    ]

    for encoding, separateur in essais:

        try:

            df = pd.read_csv(
                io.BytesIO(
                    contenu_bytes
                ),
                encoding=encoding,
                sep=separateur,
            )

            df = df.dropna(
                how="all"
            )

            if (
                df.shape[1] >= 2
                and not df.empty
            ):

                return df

        except Exception:

            continue

    # Dernier recours :
    # détection automatique du séparateur.
    try:

        df = pd.read_csv(
            io.BytesIO(
                contenu_bytes
            ),
            encoding="utf-8-sig",
            sep=None,
            engine="python",
        )

        return df.dropna(
            how="all"
        )

    except Exception:

        return pd.DataFrame()


# ============================================================
# NETTOYAGE D'UNE TABLE PDF
# ============================================================

def nettoyer_table_pdf(
    table
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

        if any(ligne_nettoyee):

            lignes.append(
                ligne_nettoyee
            )

    if len(lignes) < 2:

        return pd.DataFrame()

    header = lignes[0]

    donnees = lignes[1:]

    # Donner un nom aux colonnes vides
    header = [
        col
        if col
        else f"Colonne_{i}"
        for i, col in enumerate(header)
    ]

    try:

        return pd.DataFrame(
            donnees,
            columns=header
        )

    except Exception:

        return pd.DataFrame()


# ============================================================
# LECTURE PDF
# ============================================================

@st.cache_data(
    show_spinner=False
)
def lire_pdf(
    contenu_bytes
):

    toutes_les_tables = []

    try:

        with pdfplumber.open(
            io.BytesIO(contenu_bytes)
        ) as pdf:

            for page in pdf.pages:

                tables = page.extract_tables()

                for table in tables:

                    df = nettoyer_table_pdf(
                        table
                    )

                    if (
                        not df.empty
                        and df.shape[1] >= 2
                    ):

                        toutes_les_tables.append(
                            df
                        )

    except Exception:

        return pd.DataFrame()

    if not toutes_les_tables:

        return pd.DataFrame()

    return pd.concat(
        toutes_les_tables,
        ignore_index=True
    )


# ============================================================
# LECTURE D'UN FICHIER FOURNISSEUR
# ============================================================

def lire_fichier_fournisseur(
    fichier
):

    contenu_bytes = fichier.getvalue()

    extension = (
        fichier.name
        .lower()
        .split(".")[-1]
    )

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

    return pd.DataFrame()


# ============================================================
# PRÉPARATION DES DONNÉES
# ============================================================

def preparer_donnees(
    df,
    col_produit,
    col_prix,
    fournisseur,
    config,
):

    if (
        df is None
        or df.empty
    ):

        return pd.DataFrame()

    if (
        col_produit not in df.columns
        or col_prix not in df.columns
    ):

        return pd.DataFrame()

    resultat = pd.DataFrame()

    # --------------------------------------------------------
    # Produit affiché
    # --------------------------------------------------------

    resultat["Produit_Affichage"] = (
        df[col_produit]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Produit normalisé
    # --------------------------------------------------------

    resultat["Produit"] = (
        resultat["Produit_Affichage"]
        .apply(
            normaliser_produit
        )
    )

    # --------------------------------------------------------
    # Prix
    # --------------------------------------------------------

    resultat["Prix_Unitaire"] = (
        df[col_prix]
        .apply(
            lambda valeur:
            convertir_prix_international(
                valeur,
                config["pays"]
            )
        )
    )

    # --------------------------------------------------------
    # Fournisseur
    # --------------------------------------------------------

    resultat["Fournisseur"] = (
        fournisseur
    )

    # --------------------------------------------------------
    # Nettoyage
    # --------------------------------------------------------

    resultat = resultat[
        resultat["Produit_Affichage"]
        != ""
    ]

    resultat = resultat[
        resultat["Produit"]
        != ""
    ]

    resultat = resultat[
        resultat["Prix_Unitaire"]
        .notna()
    ]

    resultat = resultat[
        resultat["Prix_Unitaire"]
        >= 0
    ]

    # --------------------------------------------------------
    # Suppression des doublons exacts
    # --------------------------------------------------------

    resultat = resultat.drop_duplicates(
        subset=[
            "Produit",
            "Prix_Unitaire",
            "Fournisseur",
        ]
    )

    return resultat.reset_index(
        drop=True
    )


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

devise = config["devise"]
symbole = config["symbole"]

st.sidebar.info(
    f"Devise utilisée : "
    f"**{devise} ({symbole})**"
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


# ============================================================
# AUCUN FICHIER
# ============================================================

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

diagnostics_globaux = []


# ============================================================
# TRAITEMENT DES FICHIERS
# ============================================================

for fichier in fichiers:

    nom_fournisseur = (
        fichier.name
        .rsplit(
            ".",
            1
        )[0]
    )

    # --------------------------------------------------------
    # Lecture
    # --------------------------------------------------------

    with st.spinner(
        f"Lecture de {fichier.name}..."
    ):

        df_brut = lire_fichier_fournisseur(
            fichier
        )

    # --------------------------------------------------------
    # Fichier illisible
    # --------------------------------------------------------

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
                "Colonne produit": "",
                "Colonne prix": "",
                "Statut": "Lecture impossible",
            }
        )

        continue

    # --------------------------------------------------------
    # Détection
    # --------------------------------------------------------

    (
        col_produit,
        col_prix,
        diagnostics,
    ) = detecter_colonnes(
        df_brut,
        config
    )

    # --------------------------------------------------------
    # Bloc fournisseur
    # --------------------------------------------------------

    with st.expander(
        f"📄 {nom_fournisseur}",
        expanded=True,
    ):

        st.markdown(
            f"""
            <div class="provider-card">
                <strong>{fichier.name}</strong><br>
                <span class="small-muted">
                    {len(df_brut)} lignes détectées
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write(
            f"**Produit détecté :** "
            f"`{col_produit}`"
        )

        st.write(
            f"**Prix détecté :** "
            f"`{col_prix}`"
        )

        # ----------------------------------------------------
        # Correction manuelle
        # ----------------------------------------------------

        correction = st.checkbox(
            "🛠️ Corriger les colonnes manuellement",
            key=f"correction_{fichier.name}",
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
                key=f"produit_{fichier.name}",
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

            index_prix = (
                choix_prix.index(
                    col_prix
                )
                if col_prix in choix_prix
                else 0
            )

            nouveau_prix = st.selectbox(
                "Colonne Prix",
                choix_prix,
                index=index_prix,
                key=f"prix_{fichier.name}",
            )

            col_produit = (
                nouveau_produit
            )

            col_prix = (
                nouveau_prix
            )

        # ----------------------------------------------------
        # Aperçu
        # ----------------------------------------------------

        with st.expander(
            "👀 Aperçu du fichier"
        ):

            st.dataframe(
                df_brut.head(10),
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------------------------
        # Diagnostics
        # ----------------------------------------------------

        with st.expander(
            "🔎 Scores de détection"
        ):

            df_diagnostics = pd.DataFrame(
                diagnostics
            )

            st.dataframe(
                df_diagnostics,
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------------------------
        # Préparation
        # ----------------------------------------------------

        df_clean = preparer_donnees(
            df_brut,
            col_produit,
            col_prix,
            nom_fournisseur,
            config,
        )

        if df_clean.empty:

            st.warning(
                "⚠️ Aucune offre exploitable "
                "après nettoyage."
            )

            diagnostics_globaux.append(
                {
                    "Fournisseur": nom_fournisseur,
                    "Fichier": fichier.name,
                    "Lignes brutes": len(df_brut),
                    "Offres exploitables": 0,
                    "Colonne produit": col_produit,
                    "Colonne prix": col_prix,
                    "Statut": "Aucune offre exploitable",
                }
            )

            continue

        st.success(
            f"✅ {len(df_clean)} offres exploitables"
        )

        # ----------------------------------------------------
        # Stockage
        # ----------------------------------------------------

        donnees_fournisseurs[
            fichier.name
        ] = df_clean

        diagnostics_globaux.append(
            {
                "Fournisseur": nom_fournisseur,
                "Fichier": fichier.name,
                "Lignes brutes": len(df_brut),
                "Offres exploitables": len(df_clean),
                "Colonne produit": col_produit,
                "Colonne prix": col_prix,
                "Statut": "OK",
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

    with st.expander(
        "🔎 Voir les détails"
    ):

        if diagnostics_globaux:

            st.dataframe(
                pd.DataFrame(
                    diagnostics_globaux
                ),
                width="stretch",
                hide_index=True,
            )

    st.stop()


# ============================================================
# FUSION DES FOURNISSEURS
# ============================================================

dfs = list(
    donnees_fournisseurs.values()
)

df_total = pd.concat(
    dfs,
    ignore_index=True
)


# ============================================================
# COMPARAISON DES PRIX
# ============================================================

# Prix minimum pour chaque produit
prix_minimum = (
    df_total
    .groupby(
        "Produit"
    )[
        "Prix_Unitaire"
    ]
    .transform(
        "min"
    )
)


# ============================================================
# GESTION DES EX ÆQUO
# ============================================================

# On conserve TOUS les fournisseurs ayant
# exactement le meilleur prix.
resultat = df_total[
    df_total["Prix_Unitaire"]
    == prix_minimum
].copy()


# ============================================================
# TRI
# ============================================================

resultat = resultat.sort_values(
    by=[
        "Prix_Unitaire",
        "Produit",
        "Fournisseur",
    ],
    ascending=[
        True,
        True,
        True,
    ],
)


# ============================================================
# NOMBRE DE PRODUITS UNIQUES
# ============================================================

nombre_produits = (
    resultat["Produit"]
    .nunique()
)


# ============================================================
# NOMBRE D'EX ÆQUO
# ============================================================

nombre_ex_aequo = int(
    (
        resultat
        .groupby("Produit")
        .size()
        > 1
    ).sum()
)


# ============================================================
# TABLEAU D'AFFICHAGE
# ============================================================

resultat_affichage = resultat[
    [
        "Produit_Affichage",
        "Prix_Unitaire",
        "Fournisseur",
    ]
].rename(
    columns={
        "Produit_Affichage": "Produit",
        "Prix_Unitaire": f"Prix ({devise})",
    }
)


# ============================================================
# RÉSULTATS
# ============================================================

st.divider()

st.subheader(
    "🏆 Meilleurs prix"
)


# ============================================================
# KPI — RESPONSIVE
# ============================================================

col1, col2, col3 = st.columns(
    3
)

col1.metric(
    "Produits",
    nombre_produits
)

col2.metric(
    "Fournisseurs",
    df_total[
        "Fournisseur"
    ].nunique()
)

col3.metric(
    "Offres",
    len(df_total)
)


# ============================================================
# INFORMATION EX ÆQUO
# ============================================================

if nombre_ex_aequo > 0:

    st.info(
        f"ℹ️ {nombre_ex_aequo} produit(s) "
        f"présente(nt) plusieurs fournisseurs "
        f"au même meilleur prix. "
        f"Tous les ex æquo sont conservés."
    )


# ============================================================
# TABLEAU DES MEILLEURS PRIX
# ============================================================

st.dataframe(
    resultat_affichage,
    width="stretch",
    hide_index=True,
    column_config={

        "Produit":
            st.column_config.TextColumn(
                "Produit"
            ),

        f"Prix ({devise})":
            st.column_config.NumberColumn(
                f"Prix ({devise})",
                format=f"{symbole} %.2f",
            ),

        "Fournisseur":
            st.column_config.TextColumn(
                "Fournisseur"
            ),
    },
)


# ============================================================
# EXPORT CSV
# ============================================================

st.subheader(
    "📥 Export"
)

csv_export = (
    resultat_affichage
    .to_csv(
        index=False,
        encoding="utf-8-sig",
    )
)

st.download_button(
    label=(
        "📥 Télécharger les meilleurs prix (CSV)"
    ),
    data=csv_export,
    file_name=(
        "optimarge_meilleurs_prix.csv"
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
            pd.DataFrame(
                diagnostics_globaux
            ),
            width="stretch",
            hide_index=True,
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
        f"**Produits avec meilleur prix :** "
        f"{nombre_produits}"
    )

    st.write(
        f"**Produits avec ex æquo :** "
        f"{nombre_ex_aequo}"
    )


# ============================================================
# MESSAGE FINAL
# ============================================================

st.success(
    f"✅ Comparaison terminée : "
    f"**{nombre_produits} produits** "
    f"comparés auprès de "
    f"**{df_total['Fournisseur'].nunique()} fournisseurs**."
)