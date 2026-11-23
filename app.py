import streamlit as st
import os
import requests
import feedparser
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types
from pydantic import BaseModel

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="Tableau de Bord Privé", page_icon="🔒", layout="wide")

# --- 2. VERROU PAR MOT DE PASSE POUR ENTRER SUR TON SITE ---
MOT_DE_PASSE_SECRET = "#Ak300112@"  # <-- Tu peux changer ce mot de passe d'accès

if "connecte" not in st.session_state:
    st.session_state["connecte"] = False

if not st.session_state["connecte"]:
    st.title("🔒 Espace Privé — Connexion requise")
    mdp_saisi = st.text_input("Entre le mot de passe pour accéder aux outils :", type="password")
    if st.button("Déverrouiller"):
        if mdp_saisi == MOT_DE_PASSE_SECRET:
            st.session_state["connecte"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# --- 3. RÉCUPÉRATION SÉCURISÉE DE TA CLÉ GOOGLE ---
st.title("🚀 Mon Tableau de Bord Commercial")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ Clé GEMINI_API_KEY manquante dans les Secrets de Streamlit Cloud.")
    st.stop()

client = genai.Client(api_key=api_key)

# --- 4. FONCTIONS NEWSLETTER ---
def collecter_actualites(rss_urls, max_articles=4):
    articles = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in rss_urls:
        try:
            rep = requests.get(url, headers=headers, timeout=8)
            flux = feedparser.parse(rep.content)
            for entry in flux.entries[:max_articles]:
                titre = entry.get("title", "")
                resume = entry.get("summary", "")[:300]
                articles.append(f"- {titre} : {resume}")
        except Exception:
            pass
    if not articles:
        return "Actualité : Les commerces locaux cherchent à attirer des clients grâce à leur vitrine et leurs enseignes."
    return "\n".join(articles)

def appel_ia_news(prompt):
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.7)
    )
    return response.text

def generer_newsletter(matiere, secteur):
    prompt = f"""Tu es le directeur éditorial d'une entreprise spécialisée dans : {secteur}.
Rédige une newsletter LinkedIn courte et percutante.
Structure :
1. Un titre accrocheur (moins de 60 caractères).
2. Une introduction courte sur l'importance de la visibilité physique.
3. 3 conseils pratiques (enseignes, affiches) avec "Ce que ça change pour vous".
4. Une question ouverte à la fin.
Infos : {matiere}"""

    executor = ThreadPoolExecutor(max_workers=1)
    futur = executor.submit(appel_ia_news, prompt)
    try:
        texte = futur.result(timeout=12)
        executor.shutdown(wait=False)
        return texte
    except Exception:
        executor.shutdown(wait=False)
        return """# Votre façade est votre meilleur commercial (24h/24)

Bonjour à toutes et à tous,

Des centaines de personnes passent chaque jour devant votre local ou vos chantiers sans même savoir ce que vous faites. Voici 3 réflexes simples pour transformer votre visibilité physique en clients :

1. **La règle des 3 secondes :** Un passant doit comprendre votre métier en moins de 3 secondes grâce à une enseigne contrastée et lisible de loin.
2. **Ne laissez aucune vitrine ou chantier muet :** Un panneau de chantier ou une vitrophanie transforme chaque intervention en publicité gratuite auprès des voisins.
3. **L'affiche saisonnière :** Changer son affiche extérieure 4 fois par an montre que votre commerce est actif et donne une raison de pousser votre porte.

**Et vous ?** Quand avez-vous refait ou nettoyé votre enseigne extérieure pour la dernière fois ?"""

# --- 5. FONCTIONS PROSPECTION ---
class QualificationProspect(BaseModel):
    score_pertinence: int
    angle_approche: str
    accroche_linkedin: str
    objet_email: str

def chercher_entreprises(code_postal, activite, limite):
    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {"q": activite, "code_postal": code_postal, "etat_administratif": "A", "per_page": limite}
    try:
        rep = requests.get(url, params=params, timeout=10)
        rep.raise_for_status()
        return rep.json().get("results", [])
    except Exception:
        return []

def appel_ia_prospect(prompt):
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": QualificationProspect}
    )
    return QualificationProspect.model_validate_json(response.text)

def qualifier_prospect(entreprise, offre, activite, ia_active):
    nom = entreprise.get("nom_complet", "Entreprise")
    naf = entreprise.get("activite_principale", "")

    if ia_active:
        prompt = f"Analyse {nom} (Code NAF {naf}) pour vendre : {offre}. Donne un score sur 10, un produit à vendre, un message LinkedIn et un objet d'email."
        executor = ThreadPoolExecutor(max_workers=1)
        futur = executor.submit(appel_ia_prospect, prompt)
        try:
            res = futur.result(timeout=8)
            executor.shutdown(wait=False)
            return res, True
        except Exception:
            executor.shutdown(wait=False)
            ia_active = False

    return QualificationProspect(
        score_pertinence=8,
        angle_approche=f"Enseigne de façade et habillage vitrine ({activite})",
        accroche_linkedin=f"Bonjour, j'accompagne les professionnels autour de {nom} pour leurs enseignes et panneaux.",
        objet_email=f"Une idée pour booster la visibilité de {nom}"
    ), ia_active

# --- 6. LES DEUX ONGLETS DU SITE ---
tab1, tab2 = st.tabs(["📝 Ma Newsletter LinkedIn", "🎯 Prospection Locale"])

with tab1:
    st.header("Générer l'édition de la semaine")
    if st.button("✨ Rédiger la Newsletter"):
        with st.spinner("Rédaction en cours (15 sec max)..."):
            actus = collecter_actualites(["https://www.bpifrance.fr/rss.xml"])
            texte = generer_newsletter(actus, "Impression grand format, enseignes de façade et affiches")
            st.success("Newsletter prête !")
            st.text_area("Copie-colle ce texte sur LinkedIn :", value=texte, height=400)

with tab2:
    st.header("Trouver des commerçants à démarcher")
    col1, col2 = st.columns(2)
    with col1:
        code_postal = st.text_input("Code Postal cible :", value="34670")
    with col2:
        metier = st.text_input("Métier visé :", value="restaurant")

    limite = st.slider("Nombre de prospects à analyser :", 1, 15, 5)

    if st.button("🔍 Lancer la recherche"):
        with st.spinner("Recherche dans l'annuaire officiel..."):
            entreprises = chercher_entreprises(code_postal, metier, limite)
            if not entreprises:
                st.error("Aucune entreprise trouvée.")
            else:
                barre = st.progress(0)
                tableau = []
                ia_ok = True
                for i, ent in enumerate(entreprises):
                    analyse, ia_ok = qualifier_prospect(ent, "Enseignes, logos sur bâtiment et panneaux", metier, ia_ok)
                    tableau.append({
                        "Entreprise": ent.get("nom_complet", "Inconnu"),
                        "Adresse": ent.get("siege", {}).get("adresse", ""),
                        "Note /10": analyse.score_pertinence,
                        "Produit recommandé": analyse.angle_approche,
                        "Message LinkedIn": analyse.accroche_linkedin,
                        "Objet Email": analyse.objet_email
                    })
                    barre.progress((i + 1) / len(entreprises))

                st.success("Analyse terminée !")
                st.dataframe(tableau, use_container_width=True)
