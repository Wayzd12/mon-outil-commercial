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
MOT_DE_PASSE_SECRET = "Enseignes2026"  # <-- Remets ton mot de passe habituel ici

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
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.8)
    )
    return response.text

def generer_newsletter(matiere, secteur):
    prompt = f"""Tu es le directeur éditorial d'une entreprise spécialisée dans : {secteur}.
Rédige une newsletter LinkedIn courte, originale et percutante.
Structure :
1. Un titre accrocheur (moins de 60 caractères).
2. Une introduction courte sur l'importance de la visibilité physique.
3. 3 conseils pratiques (enseignes, affiches) avec "Ce que ça change pour vous".
4. Une question ouverte à la fin.
Infos : {matiere}"""

    executor = ThreadPoolExecutor(max_workers=1)
    futur = executor.submit(appel_ia_news, prompt)
    try:
        texte = futur.result(timeout=15)
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

def chercher_entreprises(code_postal, activite, limite, page=1):
    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {
        "q": activite,
        "code_postal": code_postal,
        "etat_administratif": "A",
        "per_page": limite,
        "page": page
    }
    try:
        rep = requests.get(url, params=params, timeout=10)
        rep.raise_for_status()
        return rep.json().get("results", [])
    except Exception:
        return []

def appel_ia_prospect(prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QualificationProspect,
            temperature=0.85  # Favorise des formulations variées et créatives
        )
    )
    return QualificationProspect.model_validate_json(response.text)

def qualifier_prospect(entreprise, offre, activite):
    nom = entreprise.get("nom_complet", "Entreprise")
    naf = entreprise.get("activite_principale", "")
    adresse = entreprise.get("siege", {}).get("adresse", "Adresse non précisée")
    date_creation = entreprise.get("date_creation", "Inconnue")

    prompt = f"""Tu es un commercial créatif spécialisé dans : {offre}.
Analyse cette entreprise précise et invente une approche UNIQUE adaptée à sa situation :
- Nom : {nom}
- Activité recherchée : {activite} (Code NAF : {naf})
- Adresse exacte : {adresse}
- Date de création : {date_creation}

Consignes d'interprétation obligatoires :
- Regarde l'adresse (avenue/route passante = visibilité voiture/totem/grande façade ; rue/centre = vitrine/enseigne drapeau/stop-trottoir ; zone artisanale = panneau directionnel/flocage).
- Regarde la date de création (récente = installation complète ; ancienne = rafraîchissement/modernisation d'enseigne).
- Varie ton style d'écriture pour ne jamais répéter les mêmes tournures de phrases.
- Donne une note sur 10, le produit précis à proposer, un message LinkedIn court (moins de 240 caractères) et un objet d'email original."""

    executor = ThreadPoolExecutor(max_workers=1)
    futur = executor.submit(appel_ia_prospect, prompt)
    try:
        res = futur.result(timeout=15)
        executor.shutdown(wait=False)
        return res, "IA sur mesure"
    except Exception:
        executor.shutdown(wait=False)
        return QualificationProspect(
            score_pertinence=7,
            angle_approche=f"Enseigne extérieure et habillage vitrine adaptés à {adresse}",
            accroche_linkedin=f"Bonjour, je travaille avec les commerces et pros du secteur ({activite}) autour de {nom} sur leur visibilité façade. Au plaisir d'échanger !",
            objet_email=f"Une idée visibilité pour {nom}"
        ), "Mode rapide"

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
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        code_postal = st.text_input("Code Postal cible :", value="34670")
    with col2:
        metier = st.text_input("Métier visé :", value="restaurant")
    with col3:
        page_num = st.number_input("Page (1, 2, 3...) :", min_value=1, max_value=20, value=1)

    limite = st.slider("Nombre de prospects à analyser sur cette page :", 1, 15, 5)

    if st.button("🔍 Lancer la recherche"):
        with st.spinner(f"Recherche page {page_num} dans l'annuaire officiel..."):
            entreprises = chercher_entreprises(code_postal, metier, limite, page_num)
            if not entreprises:
                st.error("Aucune entreprise trouvée sur cette page. Essaie la page 1 ou un autre métier.")
            else:
                barre = st.progress(0)
                tableau = []
                for i, ent in enumerate(entreprises):
                    analyse, source = qualifier_prospect(ent, "Enseignes, logos sur bâtiment, vitrophanie et panneaux", metier)
                    tableau.append({
                        "Entreprise": ent.get("nom_complet", "Inconnu"),
                        "Créée en": str(ent.get("date_creation", ""))[:4],
                        "Adresse": ent.get("siege", {}).get("adresse", ""),
                        "Note /10": analyse.score_pertinence,
                        "Idée sur mesure": analyse.angle_approche,
                        "Message LinkedIn": analyse.accroche_linkedin,
                        "Objet Email": analyse.objet_email,
                        "Rédaction": source
                    })
                    barre.progress((i + 1) / len(entreprises))

                st.success("Analyse terminée ! Passe à la page suivante la prochaine fois pour voir de nouveaux commerces.")
                st.dataframe(tableau, use_container_width=True)
