import streamlit as st
import os
import random
import io
import csv
import requests
import feedparser
from google import genai
from google.genai import types
from pydantic import BaseModel

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="Tableau de Bord Imprimerie", page_icon="🖨️", layout="wide")

# --- 2. VERROU PAR MOT DE PASSE ---
MOT_DE_PASSE_SECRET = "Enseignes2026"  # <-- Remets ton mot de passe ici

if "connecte" not in st.session_state:
    st.session_state["connecte"] = False

if not st.session_state["connecte"]:
    st.title("🔒 Espace Privé — Imprimerie & Signalétique")
    mdp_saisi = st.text_input("Entre le mot de passe pour accéder aux outils :", type="password")
    if st.button("Déverrouiller"):
        if mdp_saisi == MOT_DE_PASSE_SECRET:
            st.session_state["connecte"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# --- 3. CONNEXION À L'IA GOOGLE ---
st.title("🖨️ Tableau de Bord — Imprimerie & Enseignes")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ Clé GEMINI_API_KEY manquante dans les Secrets de Streamlit Cloud.")
    st.stop()

client = genai.Client(api_key=api_key)

def appeler_gemini(prompt: str, schema=None, temperature: float = 0.9):
    """Appelle l'IA avec bascule automatique si un modèle est saturé."""
    modeles_a_tester = ["gemini-2.5-flash", "gemini-3.8-flash"]
    derniere_erreur = ""

    config_args = {"temperature": temperature}
    if schema is not None:
        config_args["response_mime_type"] = "application/json"
        config_args["response_schema"] = schema

    for modele in modeles_a_tester:
        try:
            response = client.models.generate_content(
                model=modele,
                contents=prompt,
                config=types.GenerateContentConfig(**config_args)
            )
            if response.text:
                return response.text, None
        except Exception as e:
            derniere_erreur = str(e)
            continue

    return None, derniere_erreur

# --- 4. OUTILS POUR LA NEWSLETTER ---
THEMES_IMPRIMERIE = [
    "Les cartes de visite : pourquoi une carte fine ou banale finit à la poubelle, et comment un papier épais ou un vernis marque les esprits",
    "Les enseignes de façade et logos en relief : la règle des 3 secondes pour être vu par les passants et automobilistes",
    "Les panneaux de chantier (Akilux / Dibond) : comment les artisans transforment chaque chantier chez un voisin en publicité gratuite",
    "La vitrophanie et l'habillage de vitrine : attirer les passants sans surcharger sa boutique",
    "Les flyers, dépliants et brochures : comment réussir une distribution locale qui rapporte vraiment des appels",
    "Les menus, sets de table et stop-trottoirs pour restaurants et commerces : déclencher l'envie dès le trottoir",
    "Les salons professionnels, foires et événements : kakémonos, roll-ups et stands portables pour sortir du lot",
    "Les autocollants, étiquettes produits et packaging : donner une allure haut de gamme aux créateurs et producteurs locaux",
    "Le marquage de véhicules utilitaires : transformer ses trajets quotidiens en panneau publicitaire mobile",
    "La cohérence visuelle d'une entreprise : aligner ses cartes de visite, ses devis papier et sa façade pour rassurer ses clients"
]

def collecter_actualites(rss_urls, max_articles=5):
    articles = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in rss_urls:
        try:
            rep = requests.get(url, headers=headers, timeout=6)
            flux = feedparser.parse(rep.content)
            for entry in flux.entries[:max_articles]:
                titre = entry.get("title", "")
                resume = entry.get("summary", "")[:250]
                articles.append(f"- {titre} : {resume}")
        except Exception:
            pass
    return articles

def generer_newsletter(sujet_choisi: str):
    actus = collecter_actualites(["https://www.bpifrance.fr/rss.xml"])
    actu_du_jour = random.choice(actus) if actus else "Les commerces et artisans cherchent à se démarquer localement."
    style_ecriture = random.choice([
        "direct et percutant avec une anecdote terrain",
        "pédagogique avec des chiffres et des exemples concrets",
        "orienté erreurs à éviter absolument pour ne pas perdre d'argent"
    ])

    prompt = f"""Tu es le dirigeant d'une imprimerie moderne (petit et grand format : cartes de visite, flyers, brochures, affiches, enseignes de façade, logos sur bâtiment, panneaux de chantier, vitrophanie).
Rédige une édition INÉDITE de newsletter LinkedIn pour les dirigeants, artisans et commerçants locaux.

Angle obligatoire de cette édition : {sujet_choisi}
Ton et style : {style_ecriture}
Inspiration d'actualité : {actu_du_jour}

Structure obligatoire :
1. Un titre original et accrocheur (moins de 65 caractères).
2. Une introduction courte (3 lignes max) qui accroche le lecteur sur un problème concret.
3. 3 conseils pratiques d'imprimeur avec à chaque fois une ligne "**Ce que ça change pour vous :**".
4. Une conclusion courte avec une question ouverte pour encourager les commentaires.

Important : écris un texte totalement neuf, vivant et sans blabla."""

    texte, erreur = appeler_gemini(prompt, schema=None, temperature=0.95)
    if texte:
        return texte, None

    # Secours varié si l'API Google est indisponible
    secours = [
        """# Votre carte de visite finit-elle à la poubelle en 10 secondes ?

Bonjour à toutes et à tous,

On investit des heures à décrocher un rendez-vous, puis on tend une carte de visite fine, imprimée à la va-vite, qui se plie dans la poche. C'est souvent le dernier souvenir que le client garde de vous.

1. **Le poids du papier rassure immédiatement :** Un papier épais (350g ou 400g) envoie un signal inconscient de sérieux et de solidité avant même que le client lise votre nom.
**Ce que ça change pour vous :** Vous vous démarquez instantanément des concurrents qui distribuent des cartes souples bas de gamme.

2. **La finition qui attire le doigt :** Un pelliculage mat doux au toucher ou un vernis sélectif sur votre logo donne envie de garder la carte sur le bureau.
**Ce que ça change pour vous :** Votre carte n'est plus jetée, elle reste visible au moment où le client a besoin de vous.

3. **Un verso utile plutôt que vide :** Utilisez le dos de la carte pour afficher vos 3 spécialités clés ou un QR code vers vos réalisations.
**Ce que ça change pour vous :** Même 6 mois plus tard, le client sait exactement pourquoi vous appeler.

**Et vous ?** Quelle est la dernière carte de visite ou brochure que vous avez gardée parce que vous la trouviez réussie ?""",
        """# Chantier ou vitrine sans panneau : 3 clients offerts aux concurrents

Bonjour à toutes et à tous,

Chaque jour, des centaines de voisins et d'automobilistes passent devant vos chantiers ou votre local. S'ils ne voient ni logo clair ni coordonnées lisibles, ils iront chercher votre métier sur Internet... et appelleront un concurrent.

1. **La règle des 3 secondes :** En voiture ou à pied, on a 3 secondes pour lire un panneau ou une enseigne. Trop de texte tue la lecture.
**Ce que ça change pour vous :** Un logo contrasté, 3 mots sur votre métier et un numéro visible de loin suffisent à déclencher des appels.

2. **Le panneau de chantier rentable dès le 1er appel :** Un panneau rigide en Akilux ou Dibond coûte quelques dizaines d'euros et travaille pour vous 24h/24 pendant toute la durée des travaux.
**Ce que ça change pour vous :** Les voisins voient la qualité de votre travail en direct et vous appellent en confiance.

3. **L'harmonie de vos supports :** Quand votre panneau, votre utilitaire et vos devis portent la même identité visuelle, vous paraissez deux fois plus établi.
**Ce que ça change pour vous :** Vous rassurez les clients hésitants et justifiez plus facilement vos tarifs.

**Et vous ?** Vos panneaux et enseignes actuels sont-ils encore impeccables ou ont-ils pris le soleil ?"""
    ]
    return random.choice(secours), erreur

# --- 5. OUTILS POUR LA PROSPECTION ---
class AnalyseEntreprise(BaseModel):
    note_pertinence: int
    produit_imprimerie: str
    message_linkedin: str
    objet_email: str

class ListeAnalyses(BaseModel):
    resultats: list[AnalyseEntreprise]

def chercher_entreprises(codes_postaux_str: str, activite: str, limite: int, mode_tirage: str):
    codes = [c.strip() for c in codes_postaux_str.split(",") if c.strip()]
    toutes_entreprises = []
    url = "https://recherche-entreprises.api.gouv.fr/search"

    for cp in codes:
        # On pioche sur une page aléatoire si l'utilisateur veut du renouvellement
        page_api = random.randint(1, 3) if mode_tirage == "Nouveaux clients à chaque clic" else 1
        params = {
            "q": activite,
            "code_postal": cp,
            "etat_administratif": "A",
            "per_page": 25,
            "page": page_api
        }
        try:
            rep = requests.get(url, params=params, timeout=10)
            rep.raise_for_status()
            res = rep.json().get("results", [])
            # Si la page aléatoire était vide (petite commune), on revient à la page 1
            if not res and page_api > 1:
                params["page"] = 1
                rep = requests.get(url, params=params, timeout=10)
                res = rep.json().get("results", [])
            toutes_entreprises.extend(res)
        except Exception:
            pass

    # Suppression des doublons éventuels par SIREN
    uniques = {}
    for ent in toutes_entreprises:
        siren = ent.get("siren") or ent.get("nom_complet")
        uniques[siren] = ent
    liste_propre = list(uniques.values())

    if mode_tirage == "Les plus récentes en premier":
        liste_propre.sort(key=lambda x: str(x.get("date_creation") or "0000"), reverse=True)
    elif mode_tirage == "Nouveaux clients à chaque clic":
        random.shuffle(liste_propre)

    return liste_propre[:limite]

def qualifier_liste_prospects(entreprises: list[dict], metier: str):
    """Analyse toutes les entreprises en 1 seul appel IA pour un résultat 100 % sur mesure."""
    resume_clients = []
    for idx, ent in enumerate(entreprises, start=1):
        nom = ent.get("nom_complet", "Entreprise")
        adresse = ent.get("siege", {}).get("adresse", "Adresse inconnue")
        creation = str(ent.get("date_creation") or "Inconnue")[:4]
        resume_clients.append(f"{idx}. Nom: {nom} | Créée en: {creation} | Adresse: {adresse}")

    bloc_clients = "\n".join(resume_clients)

    prompt = f"""Tu es le commercial d'une imprimerie complète (cartes de visite, flyers, brochures, menus, étiquettes, affiches, enseignes de façade, logos sur bâtiment, vitrophanie, panneaux de chantier, kakémonos).
Analyse ces {len(entreprises)} entreprises locales du secteur '{metier}' et crée une proposition UNIQUE pour chacune (dans le même ordre, de 1 à {len(entreprises)}) :

{bloc_clients}

Règles strictes pour que chaque ligne soit différente :
- Adapte l'idée à l'adresse exacte (avenue/route passante = grande enseigne façade ou panneau visible en voiture ; rue/centre-ville = vitrophanie, stop-trottoir, flyers ou menus ; zone artisanale = panneaux de chantier, cartes de visite et marquage véhicule).
- Adapte à l'année de création (2024-2026 = pack lancement avec cartes de visite + enseigne ; plus ancienne = modernisation de façade, nouveaux supports promotionnels ou renouvellement de papeterie).
- Interdiction de répéter les mêmes phrases d'une entreprise à l'autre.
- Donne pour chacune : une note sur 10, le produit d'imprimerie précis à proposer, un court message LinkedIn (max 230 caractères) et un objet d'email accrocheur."""

    texte_json, erreur = appeler_gemini(prompt, schema=ListeAnalyses, temperature=0.9)

    if texte_json:
        try:
            donnees = ListeAnalyses.model_validate_json(texte_json)
            if len(donnees.resultats) == len(entreprises):
                return donnees.resultats, "IA sur mesure", None
        except Exception as e:
            erreur = str(e)

    # Secours personnalisé si l'IA n'a pas pu répondre
    secours_liste = []
    idees_variees = [
        f"Pack cartes de visite premium + flyers locaux pour {metier}",
        f"Enseigne de façade et vitrophanie sur mesure pour {metier}",
        f"Panneaux rigides, affiches grand format et dépliants ({metier})",
        f"Habillage vitrine, stop-trottoir et cartes de fidélité ({metier})",
        f"Logos sur bâtiment, signalétique extérieure et papeterie pro ({metier})"
    ]
    for i, ent in enumerate(entreprises):
        nom = ent.get("nom_complet", "Entreprise")
        idee = idees_variees[i % len(idees_variees)]
        secours_liste.append(AnalyseEntreprise(
            note_pertinence=8,
            produit_imprimerie=idee,
            message_linkedin=f"Bonjour, notre imprimerie accompagne les pros ({metier}) autour de {nom} pour leurs cartes, affiches et enseignes. Au plaisir d'échanger !",
            objet_email=f"Une idée d'impression / visibilité pour {nom}"
        ))
    return secours_liste, "Mode secours", erreur

# --- 6. INTERFACE DU SITE ---
tab1, tab2 = st.tabs(["📝 Ma Newsletter LinkedIn", "🎯 Prospection & Carte Locale"])

with tab1:
    st.header("Générer une newsletter originale")
    choix_theme = st.selectbox(
        "Choisis un sujet (ou laisse en mode surprise pour varier à chaque clic) :",
        ["🎲 Sujet surprise (change à chaque clic)"] + THEMES_IMPRIMERIE
    )

    if st.button("✨ Rédiger une nouvelle édition"):
        with st.spinner("Rédaction d'une édition inédite par l'IA..."):
            sujet = random.choice(THEMES_IMPRIMERIE) if choix_theme.startswith("🎲") else choix_theme
            texte, err = generer_newsletter(sujet)
            st.info(f"**Thème traité :** {sujet}")
            st.text_area("Copie-colle ce texte sur LinkedIn :", value=texte, height=420)
            if err:
                st.caption(f"Note technique (secours activé) : {err}")

with tab2:
    st.header("Trouver et localiser des clients autour de toi")
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        codes_postaux = st.text_input("Code(s) postal(aux) :", value="34670, 34740, 34130", help="Tu peux mettre plusieurs codes postaux séparés par une virgule (ex: Saint-Brès, Vendargues, Mauguio)")
    with col2:
        metier = st.text_input("Activité ciblée :", value="restaurant")
    with col3:
        mode_tirage = st.selectbox(
            "Ordre des résultats :",
            ["Nouveaux clients à chaque clic", "Les plus récentes en premier", "Ordre classique"]
        )

    limite = st.slider("Nombre de prospects à analyser :", 3, 12, 5)

    if st.button("🔍 Lancer la recherche et afficher la carte"):
        with st.spinner("Recherche dans l'annuaire officiel et analyse par l'IA..."):
            entreprises = chercher_entreprises(codes_postaux, metier, limite, mode_tirage)

            if not entreprises:
                st.error("Aucune entreprise trouvée. Vérifie le code postal ou essaie un mot plus simple (ex: garage, coiffeur, maçon, agence).")
            else:
                analyses, source_ia, err_ia = qualifier_liste_prospects(entreprises, metier)

                tableau = []
                points_carte = []

                for ent, analyse in zip(entreprises, analyses):
                    siege = ent.get("siege", {})
                    nom_ent = ent.get("nom_complet", "Inconnu")
                    adresse_ent = siege.get("adresse", "")
                    creation_ent = str(ent.get("date_creation") or "")[:4]

                    tableau.append({
                        "Entreprise": nom_ent,
                        "Créée en": creation_ent,
                        "Adresse": adresse_ent,
                        "Note /10": analyse.note_pertinence,
                        "Idée Imprimerie": analyse.produit_imprimerie,
                        "Message LinkedIn": analyse.message_linkedin,
                        "Objet Email": analyse.objet_email
                    })

                    # Récupération des coordonnées GPS pour la mini-carte
                    lat = siege.get("latitude")
                    lon = siege.get("longitude")
                    if lat and lon:
                        try:
                            points_carte.append({"lat": float(lat), "lon": float(lon)})
                        except ValueError:
                            pass

                if source_ia == "IA sur mesure":
                    st.success(f"✅ {len(tableau)} prospects analysés sur mesure par l'IA !")
                else:
                    st.warning("⚠️ L'IA a mis trop de temps à répondre, le mode secours a pris le relais.")
                    if err_ia:
                        st.caption(f"Détail technique : {err_ia}")

                st.dataframe(tableau, use_container_width=True)

                # Bouton de téléchargement CSV pour Excel
                buffer_csv = io.StringIO()
                writer = csv.DictWriter(buffer_csv, fieldnames=tableau[0].keys(), delimiter=";")
                writer.writeheader()
                writer.writerows(tableau)
                st.download_button(
                    label="📥 Télécharger ce tableau pour Excel (.csv)",
                    data=buffer_csv.getvalue().encode("utf-8-sig"),
                    file_name=f"prospection_{metier}.csv",
                    mime="text/csv"
                )

                # Affichage de la mini-carte
                if points_carte:
                    st.subheader("🗺️ Localisation des prospects trouvés")
                    st.map(points_carte, zoom=11)
