import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import unicodedata

st.set_page_config(
    page_title="OptiMarge - Comparateur Instantané",
    page_icon="🛒",
    layout="wide"
)

st.title("🛒 OptiMarge Food")
st.caption(
    "Dépose tes mercuriales Excel, CSV ou PDF. "
    "L'application détecte automatiquement les colonnes produit/prix et compare les offres à l'instant T."
)

# ============================================================
# OUTILS DE NORMALISATION
# ============================================================

def normaliser_texte(val):
    """Normalise un texte pour faciliter la détection des colonnes."""
    if pd.isna(val):
        return ""
    texte = str(val).strip().lower()
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"\s+", " ", texte)
    return texte


def nettoyer_nom_colonne(col):
    return normaliser_texte(col).replace("_", " ").replace("-", " ")


def convertir_prix_international(val, region):
    """Convertit un prix selon le format régional France/EUR ou Montréal/CAD."""
    if pd.isna(val):
        return None

    s = str(val).strip()
    if not s:
        return None

    # Supprimer les symboles monétaires
    s = re.sub(
        r"[€$]|CAD|EUR|USD",
        "",
        s,
        flags=re.IGNORECASE
    ).strip()

    s = s.replace("\xa0", " ")
    s = s.replace(" ", "")

    # Nettoyage des caractères non numériques
    s = re.sub(r"[^0-9,.\-+]", "", s)
    if not s:
        return None

    if region == "Montréal / Canada (CAD)":
        # Canada : 1,250.50 ou 12.50
        if "," in s and "." in s:
            # Dans 1,250.50, la virgule est un séparateur de milliers
            if s.rfind(".") > s.rfind(","):
                s = s.replace(",", "")
            else:
                # Cas exceptionnel 1.250,50
                s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            # 12,50 peut aussi apparaître dans certains fichiers canadiens
            morceaux = s.split(",")
            if len(morceaux) == 2 and len(morceaux[1]) <= 2:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")
    else:
        # France : 1.250,50 ou 12,50
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        elif s.count(".") > 1:
            morceaux = s.split(".")
            s = "".join(morceaux[:-1]) + "." + morceaux[-1]

    try:
        return float(s)
    except ValueError:
        return None


# Alias de compatibilité : le reste du code peut continuer à appeler
# convertir_prix si besoin.
def convertir_prix(val):
    return convertir_prix_international(val, "France (EUR)")


# ============================================================
# DÉTECTION AUTOMATIQUE DES COLONNES
# ============================================================

MOTS_PRODUIT_FORTS_COMMUNS = [
    "produit", "designation", "libelle", "article",
    "description", "denree", "marchandise", "intitule",
    "item", "nom", "ingredient"
]

MOTS_PRODUIT_MOYENS_COMMUNS = [
    "ref produit", "designation produit", "article libelle"
]

MOTS_PRIX_FORTS_COMMUNS = [
    "prix", "prix ht", "prix ttc", "tarif", "tarif ht",
    "prix unitaire", "pu", "p u", "montant", "cout",
    "cout unitaire", "minimum", "prix mini", "tarif mini",
    "net ht", "net"
]

MOTS_PRODUIT_EXCLUS = [
    "code", "reference", "ref", "sku",
    "quantite", "qte", "poids", "colis", "carton"
]

MOTS_PRIX_EXCLUS = [
    "quantite", "qte", "stock", "code", "reference",
    "ref", "tva", "remise", "pourcentage", "%",
    "poids", "colis", "carton"
]


def configuration_region(region):
    """Retourne les mots-clés régionaux utilisés pour la détection."""
    if region == "Montréal / Canada (CAD)":
        devise = "$"
        mots_prix_region = [
            "prix", "tarif", "cout", "pu", "net",
            "prix cad", "cad", "price", "cost", "unit price"
        ]
        mots_produit_region = [
            "produit", "description", "article",
            "item", "nom", "product"
        ]
    else:
        devise = "€"
        mots_prix_region = [
            "prix", "prix ht", "prix ttc", "tarif",
            "tarif ht", "pu", "net ht", "mini"
        ]
        mots_produit_region = [
            "produit", "designation", "libelle",
            "article", "denree"
        ]

    return devise, mots_prix_region, mots_produit_region


def score_colonne_produit(df, col, region):
    nom = nettoyer_nom_colonne(col)
    _, _, mots_produit_region = configuration_region(region)
    score = 0

    # Priorité aux termes régionaux
    for mot in mots_produit_region:
        mot = nettoyer_nom_colonne(mot)
        if nom == mot:
            score += 120
        elif mot in nom:
            score += 75

    # Termes communs
    for mot in MOTS_PRODUIT_FORTS_COMMUNS:
        mot = nettoyer_nom_colonne(mot)
        if nom == mot:
            score += 100
        elif mot in nom:
            score += 60

    for mot in MOTS_PRODUIT_MOYENS_COMMUNS:
        if mot in nom:
            score += 40

    for mot in MOTS_PRIX_FORTS_COMMUNS:
        if mot in nom:
            score -= 80

    for mot in MOTS_PRODUIT_EXCLUS:
        if nom == mot or mot in nom:
            score -= 70

    serie = df[col].dropna().astype(str).str.strip()

    if len(serie) == 0:
        return -999

    valeurs_non_vides = serie[serie != ""]
    if len(valeurs_non_vides):
        ratio_texte = valeurs_non_vides.map(
            lambda x: convertir_prix_international(x, region) is None
        ).mean()

        if ratio_texte > 0.70:
            score += 35
        elif ratio_texte > 0.45:
            score += 15

        longueur_moyenne = valeurs_non_vides.str.len().mean()
        if 4 <= longueur_moyenne <= 100:
            score += 10

    return score


def score_colonne_prix(df, col, region):
    nom = nettoyer_nom_colonne(col)
    _, mots_prix_region, _ = configuration_region(region)
    score = 0

    # Priorité aux termes régionaux
    for mot in mots_prix_region:
        mot = nettoyer_nom_colonne(mot)
        if nom == mot:
            score += 120
        elif mot in nom:
            score += 75

    for mot in MOTS_PRIX_FORTS_COMMUNS:
        mot = nettoyer_nom_colonne(mot)
        if nom == mot:
            score += 100
        elif mot in nom:
            score += 60

    for mot in MOTS_PRIX_EXCLUS:
        mot = nettoyer_nom_colonne(mot)
        if nom == mot or mot in nom:
            score -= 70

    serie = df[col].dropna()

    if len(serie) == 0:
        return -999

    prix = serie.map(lambda x: convertir_prix_international(x, region))
    ratio_numerique = prix.notna().mean()

    if ratio_numerique >= 0.90:
        score += 45
    elif ratio_numerique >= 0.70:
        score += 30
    elif ratio_numerique >= 0.40:
        score += 10
    else:
        score -= 50

    prix_valides = prix.dropna()
    if len(prix_valides):
        positifs = (prix_valides >= 0).mean()
        if positifs > 0.95:
            score += 10

        if prix_valides.nunique() <= 2:
            score -= 20

    return score


def detecter_colonnes(df, region):
    """Détecte automatiquement Produit et Prix selon la région."""
    if df is None or df.empty:
        return None, None, [], []

    scores_prod = sorted(
        [(col, score_colonne_produit(df, col, region)) for col in df.columns],
        key=lambda x: x[1],
        reverse=True
    )

    scores_prix = sorted(
        [(col, score_colonne_prix(df, col, region)) for col in df.columns],
        key=lambda x: x[1],
        reverse=True
    )

    col_prod = scores_prod[0][0] if scores_prod else None

    col_prix = None
    for col, _ in scores_prix:
        if col != col_prod:
            col_prix = col
            break

    return col_prod, col_prix, scores_prod, scores_prix


# ============================================================
# LECTURE DES FICHIERS
# ============================================================

def lire_excel(file):
    """Essaie de lire la première feuille puis les autres si nécessaire."""
    try:
        excel = pd.ExcelFile(file)
        for feuille in excel.sheet_names:
            df = pd.read_excel(file, sheet_name=feuille)
            if df is not None and not df.empty and len(df.columns) >= 2:
                return df
    except Exception as e:
        raise ValueError(f"Excel illisible : {e}")

    return pd.DataFrame()


def nettoyer_table_pdf(table):
    """Transforme une table PDF brute en DataFrame propre."""
    if not table:
        return pd.DataFrame()

    # Supprimer lignes entièrement vides
    lignes = []
    for row in table:
        if row and any(cell is not None and str(cell).strip() for cell in row):
            lignes.append(row)

    if len(lignes) < 2:
        return pd.DataFrame()

    # Nettoyage des cellules
    lignes = [
        [
            "" if cell is None else str(cell).replace("\n", " ").strip()
            for cell in row
        ]
        for row in lignes
    ]

    # Première ligne comme en-tête si elle semble pertinente
    header = lignes[0]

    # Eviter les colonnes sans nom
    header = [
        h if h else f"Colonne_{i+1}"
        for i, h in enumerate(header)
    ]

    # Rendre les noms uniques
    seen = {}
    header_unique = []
    for h in header:
        if h not in seen:
            seen[h] = 0
            header_unique.append(h)
        else:
            seen[h] += 1
            header_unique.append(f"{h}_{seen[h]}")

    data = lignes[1:]

    # Uniformiser la longueur
    largeur = len(header_unique)
    data = [
        row[:largeur] + [""] * max(0, largeur - len(row))
        for row in data
    ]

    return pd.DataFrame(data, columns=header_unique)


def lire_pdf(file):
    """Extrait les tableaux de toutes les pages d'un PDF."""
    tables = []

    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Première stratégie : extraction classique
            page_tables = page.extract_tables()

            for table in page_tables:
                df = nettoyer_table_pdf(table)
                if not df.empty and len(df.columns) >= 2:
                    tables.append(df)

            # Deuxième stratégie : extract_table si aucune table trouvée
            if not page_tables:
                table = page.extract_table()
                df = nettoyer_table_pdf(table)
                if not df.empty and len(df.columns) >= 2:
                    tables.append(df)

    if not tables:
        return pd.DataFrame()

    # On essaie de concaténer les tables compatibles
    # en gardant une structure souple.
    max_cols = max(len(df.columns) for df in tables)

    normalisees = []
    for df in tables:
        df = df.copy()
        while len(df.columns) < max_cols:
            df[f"Colonne_{len(df.columns)+1}"] = ""
        normalisees.append(df)

    return pd.concat(normalisees, ignore_index=True)


def lire_fichier_fournisseur(file, nom_fournisseur):
    nom = file.name.lower()

    try:
        file.seek(0)

        if nom.endswith((".xlsx", ".xls")):
            df = lire_excel(file)

        elif nom.endswith(".csv"):
            # Plusieurs séparateurs courants
            file.seek(0)
            contenu = file.read()

            essais = [
                ("utf-8-sig", ";"),
                ("utf-8-sig", ","),
                ("latin1", ";"),
                ("latin1", ","),
            ]

            df = pd.DataFrame()

            for encoding, sep in essais:
                try:
                    temp = pd.read_csv(
                        io.BytesIO(contenu),
                        encoding=encoding,
                        sep=sep
                    )
                    if len(temp.columns) > 1:
                        df = temp
                        break
                except Exception:
                    continue

            if df.empty:
                try:
                    df = pd.read_csv(
                        io.BytesIO(contenu),
                        encoding="utf-8-sig",
                        sep=None,
                        engine="python"
                    )
                except Exception as e:
                    raise ValueError(f"CSV illisible : {e}")

        elif nom.endswith(".pdf"):
            df = lire_pdf(file)

        else:
            raise ValueError("Format non supporté.")

    except Exception as e:
        st.error(f"❌ {file.name} : {e}")
        return None

    if df is None or df.empty:
        st.warning(
            f"⚠️ {file.name} : aucune table exploitable détectée."
        )
        return None

    # Nettoyage des noms de colonnes
    df.columns = [
        str(c).strip() if str(c).strip() else f"Colonne_{i+1}"
        for i, c in enumerate(df.columns)
    ]

    return df


# ============================================================
# NORMALISATION DES PRODUITS
# ============================================================

def normaliser_produit(produit):
    """
    Normalisation légère :
    - majuscules
    - accents supprimés
    - espaces normalisés
    - ponctuation simplifiée
    """
    s = normaliser_texte(produit)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()


def preparer_donnees(df_raw, col_prod, col_prix, fournisseur, region):
    df = pd.DataFrame()

    df["Produit_Affichage"] = (
        df_raw[col_prod]
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["Produit"] = df["Produit_Affichage"].map(normaliser_produit)
    df["Prix_Unitaire"] = df_raw[col_prix].map(
        lambda x: convertir_prix_international(x, region)
    )
    df["Fournisseur"] = fournisseur

    # Supprimer les lignes manifestement inutiles
    df = df[
        (df["Produit"] != "") &
        (df["Produit"] != "NAN") &
        df["Prix_Unitaire"].notna()
    ].copy()

    # Les prix négatifs ne sont pas des prix d'achat
    df = df[df["Prix_Unitaire"] >= 0].copy()

    return df


# ============================================================
# INTERFACE
# ============================================================

# ============================================================
# RÉGION / DEVISE
# ============================================================

region = st.sidebar.selectbox(
    "📍 Région d'utilisation",
    ["France (EUR)", "Montréal / Canada (CAD)"]
)

devise, mots_prix_region, mots_produit_region = configuration_region(region)

st.sidebar.info(
    f"Devise détectée : **{devise}**"
)

uploaded_files = st.file_uploader(
    "📂 Dépose tous les fichiers fournisseurs reçus aujourd'hui",
    type=["xlsx", "xls", "csv", "pdf"],
    accept_multiple_files=True
)

if uploaded_files:

    dfs = []
    diagnostics = []

    st.subheader("🤖 Analyse automatique")

    for file in uploaded_files:
        fournisseur = file.name.rsplit(".", 1)[0].upper()

        df_raw = lire_fichier_fournisseur(file, fournisseur)

        if df_raw is None or df_raw.empty:
            continue

        col_prod, col_prix, scores_prod, scores_prix = detecter_colonnes(
            df_raw, region
        )

        if col_prod is None or col_prix is None:
            st.error(
                f"❌ {file.name} : impossible de déterminer automatiquement "
                "les colonnes Produit et Prix."
            )
            continue

        # Sécurité absolue
        if col_prod == col_prix:
            candidats_prix = [
                col for col, _ in scores_prix if col != col_prod
            ]

            if candidats_prix:
                col_prix = candidats_prix[0]
            else:
                st.error(
                    f"❌ {file.name} : une colonne Produit et une colonne Prix "
                    "distinctes sont nécessaires."
                )
                continue

        df_clean = preparer_donnees(
            df_raw,
            col_prod,
            col_prix,
            fournisseur,
            region
        )

        diagnostics.append({
            "Fichier": file.name,
            "Produit détecté": col_prod,
            "Prix détecté": col_prix,
            "Lignes exploitables": len(df_clean),
            "Lignes source": len(df_raw)
        })

        if not df_clean.empty:
            dfs.append(df_clean)

        # Affichage compact + correction manuelle facultative
        with st.expander(
            f"✅ {file.name} — Produit : {col_prod} | Prix : {col_prix}"
        ):
            st.write(
                f"**Détection automatique :** "
                f"`{col_prod}` → Produit | `{col_prix}` → Prix"
            )

            modifier = st.checkbox(
                "Modifier manuellement les colonnes",
                key=f"modifier_{file.name}"
            )

            if modifier:
                cols = list(df_raw.columns)

                c1, c2 = st.columns(2)

                with c1:
                    nouveau_prod = st.selectbox(
                        "Colonne Produit",
                        cols,
                        index=cols.index(col_prod),
                        key=f"prod_{file.name}"
                    )

                with c2:
                    choix_prix = [
                        c for c in cols if c != nouveau_prod
                    ]

                    index_prix = (
                        choix_prix.index(col_prix)
                        if col_prix in choix_prix
                        else 0
                    )

                    nouveau_prix = st.selectbox(
                        "Colonne Prix",
                        choix_prix,
                        index=index_prix,
                        key=f"prix_{file.name}"
                    )

                df_clean = preparer_donnees(
                    df_raw,
                    nouveau_prod,
                    nouveau_prix,
                    fournisseur,
                    region
                )

                # Remplacer la version automatique
                for i, d in enumerate(diagnostics):
                    if d["Fichier"] == file.name:
                        diagnostics[i]["Produit détecté"] = nouveau_prod
                        diagnostics[i]["Prix détecté"] = nouveau_prix
                        diagnostics[i]["Lignes exploitables"] = len(df_clean)

                # Retirer l'ancien DF correspondant si présent
                dfs = [
                    d for d in dfs
                    if d["Fournisseur"].iloc[0] != fournisseur
                ]

                if not df_clean.empty:
                    dfs.append(df_clean)

            st.dataframe(
                df_raw.head(5),
                use_container_width=True
            )

    # ========================================================
    # DIAGNOSTIC
    # ========================================================

    if diagnostics:
        with st.expander("🔎 Voir le diagnostic de détection"):
            st.dataframe(
                pd.DataFrame(diagnostics),
                use_container_width=True,
                hide_index=True
            )

    # ========================================================
    # COMPARAISON
    # ========================================================

    if dfs:
        df_total = pd.concat(dfs, ignore_index=True)

        # Pour chaque produit normalisé, conserver l'offre la moins chère
        idx_min = (
            df_total.groupby("Produit")["Prix_Unitaire"]
            .idxmin()
        )

        df_meilleurs = (
            df_total.loc[idx_min]
            .sort_values("Produit_Affichage")
            .reset_index(drop=True)
        )

        resultat = df_meilleurs[
            ["Produit_Affichage", "Prix_Unitaire", "Fournisseur"]
        ].rename(
            columns={
                "Produit_Affichage": "Produit",
                "Prix_Unitaire": "Prix_Unitaire",
                "Fournisseur": "Fournisseur"
            }
        )

        resultat["Prix"] = resultat["Prix_Unitaire"].map(
            lambda x: f"{x:.2f} {devise}"
        )

        # Option recommandée : garder uniquement le prix formaté
        resultat = resultat[
            ["Produit", f"Prix Unitaire ({devise})", "Fournisseur"]
        ]

        st.markdown("---")
        st.subheader("🎯 Meilleures Offres à l'Instant T")
        st.caption(f"Région : {region} · Devise : {devise}")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Produits détectés", len(resultat))

        with col2:
            st.metric(
                "Fournisseurs",
                df_total["Fournisseur"].nunique()
            )

        with col3:
            st.metric(
                "Offres analysées",
                len(df_total)
            )

        st.dataframe(
            resultat,
            use_container_width=True,
            hide_index=True
        )

        # ====================================================
        # EXPORT
        # ====================================================

        csv_data = resultat.to_csv(
            index=False,
            sep=";",
            decimal=","
        ).encode("utf-8-sig")

        st.download_button(
            label="📥 Télécharger la liste d'achats optimale",
            data=csv_data,
            file_name="meilleurs_prix_instant_t.csv",
            mime="text/csv"
        )

        st.success(
            "✅ Comparaison terminée. "
            "Aucune donnée n'est enregistrée dans une base historique par cette application."
        )

    else:
        st.warning(
            "⚠️ Aucun fichier n'a fourni de ligne exploitable. "
            "Vérifie que les fichiers contiennent bien un nom de produit et un prix."
        )

else:
    st.info(
        "👆 Dépose tes fichiers fournisseurs ci-dessus. "
        "La détection des colonnes Produit et Prix se fera automatiquement."
    )
