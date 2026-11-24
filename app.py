import streamlit as st
import os
import time
import random
import io
import csv
import requests
import feedparser
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types
from pydantic import BaseModel

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="Tableau de Bord Imprimerie", page_icon="🖨️", layout="wide")

# --- 2. VERROU PAR MOT DE PASSE ---
MOT_DE_PASSE_SECRET = "outilcommercial4321"  # <-- Remets ton mot de passe ici

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

def _appel_unique_ia(modele: str, prompt: str, config_args: dict) -> str:
    response = client.models.generate_content(
        model=modele,
        contents=prompt,
        config=types.GenerateContentConfig(**config_args)
    )
    return response.text

def appeler_gemini_patient(prompt: str, schema=None, temperature: float = 0.9):
    """Appelle la vraie IA Google avec chronomètre de 20s max par essai (aucun texte préfait)."""
    modeles_actifs = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    zone_statut = st.empty()
    derniere_erreur = ""

    config_args = {"temperature": temperature}
    if schema is not None:
        config_args["response_mime_type"] = "application/json"
        config_args["response_schema"] = schema

    for cycle in range(1, 4):
        for modele in list(modeles_actifs):
            zone_statut.info(f"⏳ L'IA rédige sur mesure (essai {cycle}/3 — {modele})... 20 sec max.")
            executor = ThreadPoolExecutor(max_workers=1)
            futur = executor.submit(_appel_unique_ia, modele, prompt, config_args)
            try:
                texte = futur.result(timeout=20)
                executor.shutdown(wait=False)
                if texte:
                    zone_statut.empty()
                    return texte, None
            except Exception as e:
                executor.shutdown(wait=False)
                derniere_erreur = str(e) if str(e) else "Délai de 20 secondes dépassé"
                if "API_KEY_INVALID" in derniere_erreur or "API key not valid" in derniere_erreur:
                    zone_statut.empty()
                    return None, "Ta clé GEMINI_API_KEY dans les Secrets de Streamlit est invalide."
                if "404" in derniere_erreur or "not found" in derniere_erreur.lower():
                    modeles_actifs.remove(modele)
                time.sleep(1)

        if not modeles_actifs:
            break

        pause = cycle * 3
        zone_statut.warning(f"🚦 Serveurs Google occupés ({derniere_erreur[:80]}). Nouvel essai dans {pause}s...")
        time.sleep(pause)

    zone_statut.empty()
    return None, derniere_erreur

# --- 4. OUTILS POUR LA NEWSLETTER ---
THEMES_IMPRIMERIE = [
    "Les cartes de visite : pourquoi un papier épais ou un vernis marque les esprits face aux cartes banales",
    "Les enseignes de façade et logos en relief : la règle des 3 secondes pour être vu par les passants",
    "Les panneaux de chantier (Akilux / Dibond) : transformer chaque chantier chez un voisin en publicité gratuite",
    "La vitrophanie et l'habillage de vitrine : attirer les passants sans surcharger sa boutique",
    "Les flyers, dépliants et brochures : réussir une distribution locale qui rapporte vraiment des appels",
    "Les menus, sets de table et stop-trottoirs pour restaurants et commerces : déclencher l'envie dès le trottoir",
    "Les salons professionnels et événements : kakémonos, roll-ups et stands portables pour sortir du lot",
    "Les autocollants, étiquettes produits et packaging : donner une allure haut de gamme aux producteurs locaux",
    "Le marquage de véhicules utilitaires : transformer ses trajets quotidiens en panneau publicitaire mobile",
    "La cohérence visuelle d'une entreprise : aligner cartes de visite, devis papier et enseigne de façade"
]

def collecter_actualites(rss_urls, max_articles=5):
    articles = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in rss_urls:
        try:
            rep = requests.get(url, headers=headers, timeout=5)
            flux = feedparser.parse(rep.content)
            for entry in flux.entries[:max_articles]:
                titre = entry.get("title", "")
                resume = entry.get("summary", "")[:250]
                articles.append(f"- {titre} : {resume}")
        except Exception:
            pass
    return articles

# --- 5. OUTILS POUR LA PROSPECTION ---
class ProspectSelectionne(BaseModel):
    numero_entreprise: int
    note_pertinence: int
    interpretation_activite: str
    produit_imprimerie: str
    message_linkedin: str
    objet_email: str

class ListeAnalyses(BaseModel):
    resultats: list[ProspectSelectionne]

def chercher_entreprises_pool(codes_postaux_str: str, mot_cle: str, tous_types: bool, renouveler: bool):
    codes = [c.strip() for c in codes_postaux_str.split(",") if c.strip()]
    toutes_entreprises = []
    url = "https://recherche-entreprises.api.gouv.fr/search"

    for cp in codes:
        page_api = random.randint(1, 3) if renouveler else 1
        params = {
            "code_postal": cp,
            "etat_administratif": "A",
            "per_page": 25,
            "page": page_api
        }
        mots = mot_cle.strip().split()
        if not tous_types and len(mots) == 1:
            params["q"] = mot_cle.strip()

        try:
            rep = requests.get(url, params=params, timeout=8)
            rep.raise_for_status()
            res = rep.json().get("results", [])

            if len(res) < 5:
                params_larges = {
                    "code_postal": cp,
                    "etat_administratif": "A",
                    "per_page": 25,
                    "page": 1
                }
                rep2 = requests.get(url, params=params_larges, timeout=8)
                if rep2.status_code == 200:
                    res.extend(rep2.json().get("results", []))

            toutes_entreprises.extend(res)
        except Exception:
            pass

    uniques = {}
    for ent in toutes_entreprises:
        siren = ent.get("siren") or ent.get("nom_complet")
        uniques[siren] = ent

    liste_propre = list(uniques.values())
    if renouveler:
        random.shuffle(liste_propre)
    else:
        liste_propre.sort(key=lambda x: str(x.get("date_creation") or "0000"), reverse=True)

    return liste_propre[:25]

# --- 6. INTERFACE DU SITE ---
tab1, tab2 = st.tabs(["📝 Ma Newsletter LinkedIn", "🎯 Prospection & Carte Locale"])

# ==============================================================================
# ONGLET 1 : NEWSLETTER PERSONNALISABLE
# ==============================================================================
with tab1:
    st.header("Générer une newsletter 100 % rédigée par l'IA")

    col_th1, col_th2 = st.columns(2)
    with col_th1:
        choix_theme = st.selectbox(
            "1. Choisis un thème de base :",
            ["🎲 Sujet surprise (aléatoire parmi les thèmes)"] + THEMES_IMPRIMERIE
        )
    with col_th2:
        mots_cles_perso = st.text_input(
            "2. Ajoute ou modifie tes mots-clés / sujet précis (facultatif) :",
            placeholder="Ex: cartes de visite dorées, panneaux de chantier maçon, vitrine Noël..."
        )

    with st.expander("⚙️ Paramètres du prompt (Introduction, Style, Corps, Conclusion)"):
        st.caption("Modifie ces réglages pour changer la façon dont l'IA écrit ta newsletter :")

        p_identite = st.text_input(
            "Ton entreprise & tes produits :",
            value="Imprimerie moderne (cartes de visite, flyers, brochures, menus, affiches, enseignes de façade, logos sur bâtiment, vitrophanie, panneaux de chantier)"
        )
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            p_style = st.text_input(
                "Style et ton d'écriture :",
                value="Chaleureux, concret, direct, comme un artisan-conseil local qui parle simplement sans jargon"
            )
            p_intro = st.text_area(
                "Consigne pour l'Introduction :",
                value="Commence par un titre accrocheur (moins de 65 caractères), puis une introduction de 3 lignes maximum qui part d'une situation vécue par les commerçants ou artisans locaux.",
                height=100
            )
        with col_p2:
            p_corps = st.text_area(
                "Consigne pour le Corps (les conseils) :",
                value="Donne 3 conseils pratiques et actionnables liés à l'impression ou la signalétique. Pour chaque conseil, ajoute une ligne en gras '**Ce que ça change pour vous :**'.",
                height=100
            )
            p_conclusion = st.text_area(
                "Consigne pour la Conclusion :",
                value="Termine par 2 lignes de conclusion positives et une question ouverte simple pour inciter les lecteurs à commenter.",
                height=100
            )

    if st.button("✨ Générer ma newsletter sur mesure", type="primary"):
        actus = collecter_actualites(["https://www.bpifrance.fr/rss.xml"])
        actu_du_jour = random.choice(actus) if actus else "Les entreprises locales cherchent à attirer des clients."

        base_sujet = random.choice(THEMES_IMPRIMERIE) if choix_theme.startswith("🎲") else choix_theme
        if mots_cles_perso.strip():
            sujet_final = f"{base_sujet} — Focus spécifique demandé : {mots_cles_perso.strip()}"
        else:
            sujet_final = base_sujet

        prompt_complet = f"""Tu es le dirigeant de : {p_identite}.
Rédige une édition INÉDITE et ORIGINALE de newsletter LinkedIn destinée aux dirigeants, commerçants et artisans locaux.

SUJET À TRAITER : {sujet_final}
INSPIRATION DU MOMENT (facultative, à relier naturellement si pertinent) : {actu_du_jour}
STYLE ET TON : {p_style}

STRUCTURE OBLIGATOIRE À SUIVRE :
- Introduction : {p_intro}
- Développement : {p_corps}
- Conclusion : {p_conclusion}

Rédige uniquement la newsletter prête à publier sur LinkedIn, sans phrase d'introduction avant le titre."""

        texte_genere, erreur = appeler_gemini_patient(prompt_complet, schema=None, temperature=0.95)

        if texte_genere:
            st.success("✅ Newsletter rédigée par l'IA !")
            st.info(f"**Sujet traité :** {sujet_final}")
            st.text_area("Copie-colle ce texte sur LinkedIn :", value=texte_genere, height=450)
        else:
            st.error(f"❌ L'IA n'a pas pu répondre. Détail : {erreur}")

# ==============================================================================
# ONGLET 2 : PROSPECTION INTELLIGENTE & MINI-CARTE
# ==============================================================================
with tab2:
    st.header("Trouver des prospects selon un thème ou tous types d'activités")

    col1, col2 = st.columns([2, 2])
    with col1:
        codes_postaux = st.text_input(
            "Code(s) postal(aux) :",
            value="34670, 34740, 34130",
            help="Sépare plusieurs codes postaux par une virgule (ex: Saint-Brès, Vendargues, Mauguio)"
        )
        tous_types = st.checkbox(
            "🌐 Tous types d'activités (ne pas se limiter à un seul métier)",
            value=False
        )
    with col2:
        theme_recherche = st.text_input(
            "Thème ou mot-clé à faire interpréter par l'IA :",
            value="commerces avec vitrine ou restaurants",
            disabled=tous_types,
            help="Tu peux mettre un métier précis (ex: boulangerie) OU un thème large (ex: artisans qui font des chantiers, jeunes entreprises, agences...)"
        )
        renouveler = st.checkbox(
            "🎲 Varier les entreprises à chaque recherche (sinon : les plus récentes en premier)",
            value=True
        )

    limite = st.slider("Nombre de prospects à retenir et analyser :", 3, 12, 5)

    with st.expander("⚙️ Paramètres du prompt de prospection"):
        st.caption("Ajuste les critères utilisés par l'IA pour sélectionner et démarcher tes prospects :")
        prosp_offre = st.text_input(
            "Tes services d'imprimerie à mettre en avant :",
            value="Impression petit et grand format : cartes de visite, flyers, brochures, menus, étiquettes, enseignes de façade, logos en relief, vitrophanie, panneaux de chantier, marquage véhicule"
        )
        prosp_consignes = st.text_area(
            "Consignes d'interprétation pour l'IA :",
            value="1. Sélectionne en priorité les entreprises les plus pertinentes par rapport au thème demandé (en décodant leur code activité NAF et leur nom).\n2. Adapte le produit recommandé à l'adresse (avenue/zone = grande enseigne ou panneau ; rue commerçante = vitrine, flyers ou menus ; artisan = panneaux de chantier et cartes de visite) et à l'année de création (récente = pack création ; ancienne = modernisation).\n3. Écris un message LinkedIn court (max 230 caractères), poli, local et jamais répétitif d'une ligne à l'autre.",
            height=120
        )

    if st.button("🔍 Rechercher, analyser et afficher sur la carte", type="primary"):
        vivier = chercher_entreprises_pool(codes_postaux, theme_recherche, tous_types, renouveler)

        if not vivier:
            st.error("Aucune entreprise trouvée dans l'annuaire officiel pour ces codes postaux. Vérifie les chiffres saisis.")
        else:
            lignes_vivier = []
            for idx, ent in enumerate(vivier, start=1):
                nom = ent.get("nom_complet", "Entreprise")
                naf = ent.get("activite_principale", "Inconnu")
                adresse = ent.get("siege", {}).get("adresse", "Adresse inconnue")
                creation = str(ent.get("date_creation") or "Inconnue")[:4]
                lignes_vivier.append(f"{idx}. Nom: {nom} | Code NAF: {naf} | Créée en: {creation} | Adresse: {adresse}")

            objectif_texte = (
                "TOUS TYPES D'ACTIVITÉS (choisis un mélange varié et pertinent de commerces, artisans et sociétés locales)"
                if tous_types
                else f"THÈME RECHERCHÉ : '{theme_recherche}' (interprète ce thème au sens large pour trouver les meilleures entreprises correspondantes)"
            )

            prompt_prospection = f"""Tu es le directeur commercial d'une entreprise spécialisée dans : {prosp_offre}.

Voici une liste de {len(vivier)} vraies entreprises locales trouvées autour des codes postaux ({codes_postaux}) :
{chr(10).join(lignes_vivier)}

MISSION :
1. Parmi cette liste, sélectionne exactement les {min(limite, len(vivier))} meilleures entreprises qui correspondent le mieux à : {objectif_texte}.
2. Indique leur numéro exact (`numero_entreprise` entre 1 et {len(vivier)}).
3. Explique en 1 phrase simple ce que fait cette entreprise (`interpretation_activite`).
4. Applique strictement ces consignes pour chaque entreprise retenue :
{prosp_consignes}"""

            texte_json, erreur_ia = appeler_gemini_patient(prompt_prospection, schema=ListeAnalyses, temperature=0.9)

            if not texte_json:
                st.error(f"❌ L'IA n'a pas pu analyser les prospects. Détail : {erreur_ia}")
            else:
                try:
                    donnees = ListeAnalyses.model_validate_json(texte_json)
                    tableau = []
                    points_carte = []

                    for item in donnees.resultats:
                        index_reel = item.numero_entreprise - 1
                        if 0 <= index_reel < len(vivier):
                            ent = vivier[index_reel]
                            siege = ent.get("siege", {})
                            nom_ent = ent.get("nom_complet", "Inconnu")
                            adresse_ent = siege.get("adresse", "")
                            creation_ent = str(ent.get("date_creation") or "")[:4]

                            tableau.append({
                                "Entreprise": nom_ent,
                                "Activité détectée": item.interpretation_activite,
                                "Créée en": creation_ent,
                                "Adresse": adresse_ent,
                                "Note /10": item.note_pertinence,
                                "Produit à proposer": item.produit_imprimerie,
                                "Message LinkedIn": item.message_linkedin,
                                "Objet Email": item.objet_email
                            })

                            lat = siege.get("latitude")
                            lon = siege.get("longitude")
                            if lat and lon:
                                try:
                                    points_carte.append({"lat": float(lat), "lon": float(lon)})
                                except ValueError:
                                    pass

                    if tableau:
                        st.success(f"✅ {len(tableau)} prospects sélectionnés et analysés sur mesure par l'IA !")
                        st.dataframe(tableau, use_container_width=True)

                        buffer_csv = io.StringIO()
                        writer = csv.DictWriter(buffer_csv, fieldnames=tableau[0].keys(), delimiter=";")
                        writer.writeheader()
                        writer.writerows(tableau)
                        st.download_button(
                            label="📥 Télécharger ce tableau pour Excel (.csv)",
                            data=buffer_csv.getvalue().encode("utf-8-sig"),
                            file_name="prospection_imprimerie.csv",
                            mime="text/csv"
                        )

                        if points_carte:
                            st.subheader("🗺️ Localisation des prospects retenus")
                            st.map(points_carte, zoom=11)
                    else:
                        st.warning("L'IA a renvoyé des numéros hors liste. Clique à nouveau sur Rechercher.")
                except Exception as e:
                    st.error(f"Erreur de lecture de la réponse IA : {e}")
