import os
import json
import math
import time
import random
import io
import csv
import requests
import feedparser
import urllib.parse
import folium
import urllib.parse
import streamlit as st
from streamlit_folium import st_folium
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="Tableau de Bord Commercial", page_icon="💹", layout="wide")

# --- 2. VERROU PAR MOT DE PASSE ---
MOT_DE_PASSE_SECRET = "outilcommercial4321"  # <-- Remets ton mot de passe ici

if "connecte" not in st.session_state:
    st.session_state["connecte"] = False

if not st.session_state["connecte"]:
    st.title("🔒 Espace Privé — Plan commercial & Aide Générative")
    mdp_saisi = st.text_input("Entre le mot de passe pour accéder aux outils :", type="password")
    if st.button("Déverrouiller"):
        if mdp_saisi == MOT_DE_PASSE_SECRET:
            st.session_state["connecte"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()

# --- 3. GESTION DES RÉGLAGES SAUVEGARDÉS ---
FICHIER_REGLAGES = "mes_reglages_imprimerie.json"

REGLAGES_PAR_DEFAUT = {
    
    "p_identite": "Imprimerie moderne basée au Centre DIGITALIS Agglomération (ZAE du Bosc – 8 Rue des Vergers, 34130 Mudaison) (cartes de visite, flyers, brochures, menus, affiches, enseignes de façade, vitrophanie, panneaux de chantier)",
    "p_style": "Chaleureux, concret, direct, comme un artisan-conseil local qui parle simplement sans jargon",
    
    # Consigne d'intro avec exigence de structure
    "p_intro": "Commence par un titre accrocheur (<65 car.), puis une ligne de séparation '---'. Rédige ensuite une introduction de 3 lignes max incarnant ton ancrage local à Mudaison, suivie d'un autre séparateur '---'.",
    
    # Consigne de corps avec blocs et émojis obligatoires
    "p_corps": "Propose 3 conseils pratiques. Chaque conseil DOIT commencer par un émoji pertinent (ex: 💡, 📐, 🖨️), être séparé par une ligne '---', et contenir une ligne en gras : '**Ce que ça change pour vous :**'.",
    
    # Consigne de conclusion claire
    "p_conclusion": "Termine par une ligne '---', puis 2 lignes de conclusion positives suivies d'une question ouverte simple pour inciter à réagir.",

    "prosp_offre": "Impression petit et grand format depuis notre atelier du Centre DIGITALIS Agglomération à Mudaison : cartes de visite, flyers, brochures, menus, enseignes, vitrophanie, panneaux de chantier",
    "prosp_consignes": "1. Tiens compte de la localisation précise ({lieu_cible}) et de l'adresse exacte de chaque entreprise.\n2. Sélectionne uniquement les entreprises en rapport avec le thème demandé.\n3. Dans le message LinkedIn (max 230 caractères), positionne-toi clairement comme un **voisin immédiat basé à Mudaison (ZAE du Bosc)** pour créer un ancrage local fort.\n4. Adapte le produit recommandé à l'emplacement et à l'année de création.\n5. Ne sélectionne que des entreprises ouvertes.",
    "codes_postaux": "34130",
    "zone_lat": 43.6440,  # Latitude centrée sur Mudaison
    "zone_lon": 4.0440,   # Longitude centrée sur Mudaison
    "rayon_km": 10
}

def sauvegarder_reglages_sur_disque(nouveaux_reglages: dict):
    st.session_state["reglages"].update(nouveaux_reglages)
    try:
        with open(FICHIER_REGLAGES, "w", encoding="utf-8") as f:
            json.dump(st.session_state["reglages"], f, ensure_ascii=False, indent=2)
    except Exception:
        pass
        
def obtenir_image_internet_dynamique(sujet):
    # Nettoyage et formatage du mot-clé entré par l'utilisateur
    mot_cle_propre = urllib.parse.quote(sujet.strip())
    
    # Cette URL officielle Unsplash interroge leur moteur en direct à chaque appel
    # Le paramètre 'sig' (signature aléatoire) force le serveur à changer d'image à chaque fois
    sig_aleatoire = random.randint(1, 10000)
    
    url_dynamique = f"https://source.unsplash.com/featured/800x600/?{mot_cle_propre}&sig={sig_aleatoire}"
    return url_dynamique
    
if "reglages" not in st.session_state:
    st.session_state["reglages"] = charger_reglages()

if "mode_carte_zone" not in st.session_state:
    st.session_state["mode_carte_zone"] = False

if "check_tous_types" not in st.session_state:
    st.session_state["check_tous_types"] = False

if "dernier_clic_carte" not in st.session_state:
    st.session_state["dernier_clic_carte"] = None

# --- 4. CONNEXION À L'IA GOOGLE ---
st.title("💹 Tableau de Bord — Commerce & Enseignes")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ Clé GEMINI_API_KEY manquante dans les Secrets de Streamlit Cloud.")
    st.stop()

client = genai.Client(api_key=api_key)

def _appel_unique_ia(modele: str, prompt: str, config_args: dict, theme_recherche: str = "", prosp_offre: str = "") -> str:
    # On enrichit le prompt pour que l'IA sache exactement quel visuel générer
    prompt_complet = f"""
    {prompt}
    
    INSTRUCTION SPÉCIALE POUR LE VISUEL (champ 'prompt_image_humour') : 
    Rédige un prompt en anglais très détaillé, propre et professionnel pour Pollinations.ai, représentant une illustration ou une scène en lien direct avec le thème : '{theme_recherche}' et l'offre commerciale : '{prosp_offre}'. Pas de texte parasite sur l'image.
    """
    
    response = client.models.generate_content(
        model=modele,
        contents=prompt_complet,
        config=types.GenerateContentConfig(**config_args)
    )
    return response.text


def appeler_gemini_patient(prompt: str, schema=None, temperature: float = 0.85):
    """Appelle toujours la vraie IA Google avec chronomètre de 90s max par essai."""
    modeles_actifs = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]
    zone_statut = st.empty()
    derniere_erreur = ""

    # On ajoute thinking_config pour forcer le modèle Flash à réfléchir en profondeur
    config_args = {
        "temperature": temperature,
        "max_output_tokens": 16384,
        "thinking_config": {
            "thinking_budget": 4096
        }
    }
    
    if schema is not None:
        config_args["response_mime_type"] = "application/json"
        config_args["response_schema"] = schema

    for cycle in range(1, 4):
        for modele in list(modeles_actifs):
            zone_statut.info(f"⏳ L'IA analyse et rédige sur mesure (essai {cycle}/3 — {modele})... 90 sec max selon la demande.")
            executor = ThreadPoolExecutor(max_workers=1)
            futur = executor.submit(_appel_unique_ia, modele, prompt, config_args)

            try:
                texte = futur.result(timeout=90)
                executor.shutdown(wait=False)
                if texte:
                    zone_statut.empty()
                    return texte, None
            except Exception as e:
                executor.shutdown(wait=False)
                derniere_erreur = str(e) if str(e) else "Délai de 90 secondes dépassé"
                if "API_KEY_INVALID" in derniere_erreur or "API key not valid" in derniere_erreur:
                    zone_statut.empty()
                    return None, "Ta clé GEMINI_API_KEY dans les Secrets de Streamlit est invalide."
                if "404" in derniere_erreur or "not found" in derniere_erreur.lower():
                    modeles_actifs.remove(modele)
                time.sleep(1)

        if not modeles_actifs:
            break

        pause = cycle * 3
        zone_statut.warning(f"🚦 Serveurs Google occupés. Nouvel essai dans {pause}s...")
        time.sleep(pause)

    zone_statut.empty()
    return None, derniere_erreur

# --- 5. OUTILS POUR LA NEWSLETTER ---
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
    "La cohérence visuelle d'une entreprise : aligner cartes de visite, devis papier et enseigne de façade",
    "tampons personnalisables et gravures sur plaques pour l'office : petite signalétique",
    "clé USB et objets publicitaires : pourquoi afficher sa marque sur des produits du quotidien marque les esprits"
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

# --- 6. OUTILS GÉOGRAPHIQUES & PROSPECTION ---
class ProspectSelectionne(BaseModel):
    numero_entreprise: int
    note_pertinence: int = Field(ge=1, le=10, description="Note stricte sur 10 (1 = aucun rapport avec le mot-clé, 10 = correspondance parfaite)")
    interpretation_activite: str
    produit_imprimerie: str
    message_linkedin: str
    objet_email: str
    projet_chantier: str

class ListeAnalyses(BaseModel):
    resultats: list[ProspectSelectionne]

class NewsletterReponse(BaseModel):
    texte_newsletter: str = Field(description="Le texte complet et professionnel de la publication.")
    prompt_image_humour: str = Field(description="A detailed English visual prompt for Pollinations.ai describing a clean, modern, professional corporate illustration related to the topic.")
    categorie_produit: str = Field(description="Un seul mot-clé en anglais parmi cette liste pour la vraie photo pro : 'businesscard', 'storefront', 'signage', 'restaurant', 'printing'")

def calculer_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rayon_terre = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return rayon_terre * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

@st.cache_data(ttl=3600, show_spinner=False)
def identifier_commune_gps(lat: float, lon: float):
    """Traduit un point GPS cliqué sur la carte en nom de commune, codes postaux et département."""
    try:
        rep = requests.get(
            "https://geo.api.gouv.fr/communes",
            params={"lat": round(lat, 5), "lon": round(lon, 5), "fields": "nom,codesPostaux,codeDepartement"},
            timeout=5
        )
        if rep.status_code == 200 and rep.json():
            commune = rep.json()[0]
            return commune.get("nom", ""), commune.get("codesPostaux", []), commune.get("codeDepartement", "")
    except Exception:
        pass
    return "", [], ""

@st.cache_data(ttl=3600, show_spinner=False)
def identifier_communes_cp(codes_postaux_str: str):
    """Traduit un ou plusieurs codes postaux en noms de villes réels."""
    codes = [c.strip() for c in codes_postaux_str.split(",") if c.strip()]
    villes = []
    for cp in codes[:5]:
        try:
            rep = requests.get(
                "https://geo.api.gouv.fr/communes",
                params={"codePostal": cp, "fields": "nom"},
                timeout=5
            )
            if rep.status_code == 200:
                for c in rep.json():
                    nom_v = c.get("nom")
                    if nom_v and nom_v not in villes:
                        villes.append(nom_v)
        except Exception:
            pass
    return villes

def extraire_mots_cles_significatifs(mot_cle: str) -> list:
    """Extrait les mots-clés utiles d'une expression (ex: 'commerces avec vitrine' -> ['commerces', 'vitrine'])."""
    mots_vides = {
        "avec", "sans", "pour", "dans", "les", "des", "une", "qui", "font",
        "sur", "par", "aux", "type", "types", "entreprise", "entreprises", "societe", "societes"
    }
    nettoye = mot_cle.lower().replace(",", " ").replace(";", " ").replace("'", " ")
    return [m.strip() for m in nettoye.split() if len(m.strip()) >= 3 and m.strip() not in mots_vides]

def extraire_etablissement_local(ent: dict, mode_zone: bool, codes_cibles: list, zone_lat: float, zone_lon: float, rayon_km: int):
    """Vérifie les établissements locaux pour garder uniquement les entreprises situées sur place."""
    candidats_etab = []
    if ent.get("matching_etablissements"):
        candidats_etab.extend(ent["matching_etablissements"])
    if ent.get("siege"):
        candidats_etab.append(ent["siege"])

    for etab in candidats_etab:
        lat_s = etab.get("latitude")
        lon_s = etab.get("longitude")
        cp_s = str(etab.get("code_postal") or "").strip()

        if mode_zone:
            if lat_s and lon_s:
                try:
                    lat_f, lon_f = float(lat_s), float(lon_s)
                    dist = calculer_distance_km(zone_lat, zone_lon, lat_f, lon_f)
                    if dist <= rayon_km + 1.0:
                        return {
                            "nom": ent.get("nom_complet", "Entreprise"),
                            "naf": ent.get("activite_principale", "Inconnu"),
                            "creation": str(ent.get("date_creation") or "Inconnue")[:4],
                            "adresse": etab.get("adresse", ""),
                            "cp": cp_s,
                            "lat": lat_f,
                            "lon": lon_f,
                            "distance_km": round(dist, 1)
                        }
                except ValueError:
                    pass
        else:
            if cp_s in codes_cibles:
                lat_f, lon_f = None, None
                if lat_s and lon_s:
                    try:
                        lat_f, lon_f = float(lat_s), float(lon_s)
                    except ValueError:
                        pass
                return {
                    "nom": ent.get("nom_complet", "Entreprise"),
                    "naf": ent.get("activite_principale", "Inconnu"),
                    "creation": str(ent.get("date_creation") or "Inconnue")[:4],
                    "adresse": etab.get("adresse", ""),
                    "cp": cp_s,
                    "lat": lat_f,
                    "lon": lon_f,
                    "distance_km": None
                }
    return None

def chercher_entreprises_pool(
    mode_zone: bool,
    codes_postaux_str: str,
    zone_lat: float,
    zone_lon: float,
    rayon_km: int,
    mot_cle: str,
    tous_types: bool,
    renouveler: bool
):
    """Récupère un vivier élargi d'entreprises locales en augmentant le nombre de pages (per_page=25 max exigé par l'API)."""
    vivier_brut = {}
    mots_cles_list = [] if tous_types else extraire_mots_cles_significatifs(mot_cle)
    exclure_sci = True if tous_types else (not any(m in mot_cle.lower() for m in ["immobilier", "sci", "foncier", "location"]))

    def ajouter_depuis_reponse(data_json, codes_cibles):
        for ent in data_json.get("results", []):
            if ent.get("etat_administratif") != "A":
                continue
            naf = str(ent.get("activite_principale") or "")
            if exclure_sci and naf.startswith("68.20"):
                continue
            siren = ent.get("siren") or ent.get("nom_complet")
            if siren in vivier_brut:
                continue
            info_locale = extraire_etablissement_local(ent, mode_zone, codes_cibles, zone_lat, zone_lon, rayon_km)
            if info_locale:
                vivier_brut[siren] = info_locale

    if mode_zone:
        _, cps_gps, code_dept = identifier_commune_gps(zone_lat, zone_lon)

        # 1. Recherche par mots-clés élargie sur le département (pages 1 à 6)
        if not tous_types and mots_cles_list and code_dept:
            url_search = "https://recherche-entreprises.api.gouv.fr/search"
            requetes_q = [mot_cle.strip()] if len(mots_cles_list) > 1 else []
            requetes_q.extend(mots_cles_list)
            for terme in dict.fromkeys(requetes_q):
                pages_q = [1, 2, 3, 4, 5, 6] if not renouveler else [1, 2, 3, 4, 5, 6]
                for page_q in dict.fromkeys(pages_q):
                    try:
                        rep_q = requests.get(
                            url_search,
                            params={
                                "q": terme,
                                "departement": code_dept,
                                "etat_administratif": "A",
                                "per_page": 25,  # MAXIMUM AUTORISÉ PAR L'API
                                "page": page_q
                            },
                            timeout=8
                        )
                        if rep_q.status_code == 200:
                            ajouter_depuis_reponse(rep_q.json(), [])
                    except Exception:
                        pass
                    if len(vivier_brut) >= 120:
                        break
                if len(vivier_brut) >= 120:
                    break

        # 2. Recherche géographique par point élargie (/near_point - pages 1 à 8)
        if tous_types or len(vivier_brut) < 50:
            url_geo = "https://recherche-entreprises.api.gouv.fr/near_point"
            pages_geo = [1, 2, 3, 4, 5, 6, 7, 8] if not renouveler else [1, 2, 3, 4, 5, 6, 7, 8]
            for p in dict.fromkeys(pages_geo):
                try:
                    rep = requests.get(
                        url_geo,
                        params={
                            "lat": round(zone_lat, 5),
                            "long": round(zone_lon, 5),
                            "radius": rayon_km,
                            "per_page": 25,  # MAXIMUM AUTORISÉ PAR L'API
                            "page": p
                        },
                        timeout=10
                    )
                    if rep.status_code == 200:
                        ajouter_depuis_reponse(rep.json(), [])
                except Exception:
                    pass
                if len(vivier_brut) >= 150:
                    break
    else:
        codes = [c.strip() for c in codes_postaux_str.split(",") if c.strip()]
        url = "https://recherche-entreprises.api.gouv.fr/search"

        for cp in codes:
            if not tous_types and mots_cles_list:
                requetes_q = [mot_cle.strip()] if len(mots_cles_list) > 1 else []
                requetes_q.extend(mots_cles_list)
                for terme in dict.fromkeys(requetes_q):
                    try:
                        rep1 = requests.get(
                            url,
                            params={"q": terme, "code_postal": cp, "etat_administratif": "A", "per_page": 25, "page": 1},
                            timeout=8
                        )
                        if rep1.status_code == 200:
                            json1 = rep1.json()
                            ajouter_depuis_reponse(json1, codes)
                            total_pages = int(json1.get("total_pages", 1))
                            if total_pages > 1:
                                for p_idx in range(2, min(total_pages + 1, 8)):
                                    rep_p = requests.get(
                                        url,
                                        params={"q": terme, "code_postal": cp, "etat_administratif": "A", "per_page": 25, "page": p_idx},
                                        timeout=8
                                    )
                                    if rep_p.status_code == 200:
                                        ajouter_depuis_reponse(rep_p.json(), codes)
                    except Exception:
                        pass

            if tous_types or len(vivier_brut) < 30:
                for p_large in range(1, 6):
                    try:
                        rep_large = requests.get(
                            url,
                            params={"code_postal": cp, "etat_administratif": "A", "per_page": 25, "page": p_large},
                            timeout=8
                        )
                        if rep_large.status_code == 200:
                            ajouter_depuis_reponse(rep_large.json(), codes)
                    except Exception:
                        pass

    liste_propre = list(vivier_brut.values())
    if renouveler:
        random.shuffle(liste_propre)
    else:
        liste_propre.sort(key=lambda x: str(x.get("creation") or "0000"), reverse=True)

    return liste_propre[:80]



# --- 7. BARRE DE SAUVEGARDE PERMANENTE DES RÉGLAGES ---
with st.expander("💾 Sauvegarder ou restaurer mes réglages préférés"):
    st.caption("Tes réglages sont mémorisés dès que tu cliques sur Enregistrer. Télécharge aussi le petit fichier de secours pour pouvoir les recharger en 1 clic si le site se met en veille.")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.download_button(
            label="📥 Télécharger ma sauvegarde (.json)",
            data=json.dumps(st.session_state["reglages"], ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="mes_reglages_imprimerie.json",
            mime="application/json"
        )
    with col_s2:
        fichier_importe = st.file_uploader("📤 Restaurer une sauvegarde (.json)", type=["json"], label_visibility="collapsed")
        if fichier_importe is not None:
            try:
                contenu = json.load(fichier_importe)
                sauvegarder_reglages_sur_disque(contenu)
                st.success("✅ Réglages restaurés avec succès !")
            except Exception:
                st.error("Fichier invalide.")

# --- 8. INTERFACE DU SITE (2 ONGLETS) ---
tab1, tab2 = st.tabs(["📝 Ma Newsletter LinkedIn", "🎯 Prospection & Carte Locale"])

# ==============================================================================
# ONGLET 1 : GÉNÉRATEUR DE NEWSLETTER & VISUELS PROFESSIONNELS
# ==============================================================================
with tab1:
    st.header("📰 Générateur de Newsletter LinkedIn & Illustration")
    
    # 1. Saisie des informations de la newsletter
    sujet_final = st.text_input(
        "Sujet principal de la newsletter :", 
        value="Conseils pour dynamiser la vitrine et l'enseigne de votre commerce local",
        key="input_sujet_newsletter"
    )
    
    actu_du_jour = st.text_input(
        "Inspiration du moment / Actualité (optionnel) :", 
        value="", 
        placeholder="Ex: Arrivée du printemps, fêtes de fin d'année, chantier en cours...",
        key="input_actu_newsletter"
    )

    with st.expander("⚙️ Paramètres du style et de la structure de la newsletter"):
        p_identite = st.text_input("Identité de l'expéditeur :", value="Imprimerie Centre DIGITALIS Agglomération (34130 Mudaison)", key="nl_p_identite")
        p_style = st.text_input("Style d'écriture :", value="Chaleureux, concret, direct, comme un artisan-conseil local", key="nl_p_style")
        p_intro = st.text_area("Consigne Introduction :", value="Commence par un titre accrocheur, puis une ligne '---'. Rédige une intro de 3 lignes max ancrée à Mudaison, puis '---'.", key="nl_p_intro")
        p_corps = st.text_area("Consigne Développement (3 conseils) :", value="Propose 3 conseils commençant par un émoji (ex: 💡), séparés par '---', avec une ligne en gras '**Ce que ça change pour vous :**'.", key="nl_p_corps")
        p_conclusion = st.text_area("Consigne Conclusion :", value="Termine par '---', puis 2 lignes de conclusion positives et une question ouverte.", key="nl_p_conclusion")

    st.markdown("---")
    
    # 2. Sélection de l'image (Automatique, Mot-clé ou Import PC)
st.subheader("🌐 Illustration de la publication (En direct du web)")

mode_image = st.radio(
    "Source de l'image :",
    [
        "🤖 Automatique (selon le sujet de la newsletter)", 
        "🔍 Taper un mot-clé précis pour chercher sur Internet",
        "💻 Importer une photo depuis mon ordinateur"
    ],
    key="radio_mode_internet"
)

image_selectionnee = None

if mode_image == "🤖 Automatique (selon le sujet de la newsletter)":
    mots_cles_auto = " ".join(sujet_final.split()[:3])
    image_selectionnee = obtenir_image_internet_dynamique(mots_cles_auto)

elif mode_image == "🔍 Taper un mot-clé précis pour chercher sur Internet":
    mot_cle_libre = st.text_input(
        "Entrez un mot-clé (ex: printing press, modern shop, construction...)", 
        value="printing press", 
        key="input_mot_cle_libre"
    )
    image_selectionnee = obtenir_image_internet_dynamique(mot_cle_libre)

elif mode_image == "💻 Importer une photo depuis mon ordinateur":
    fichier_upload = st.file_uploader(
        "Téléchargez votre propre image (JPG, PNG)", 
        type=["jpg", "jpeg", "png"], 
        key="uploader_image_locale_nl"
    )
    if fichier_upload is not None:
        image_selectionnee = fichier_upload

# Affichage compact et centré de l'image sélectionnée
if image_selectionnee is not None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(image_selectionnee, width=450, caption="Aperçu de l'image sélectionnée")
   
    st.markdown("---")

    # 3. Bouton de génération de la newsletter par Gemini
    if st.button("✨ Rédiger la Newsletter", type="primary", key="btn_generer_newsletter_pro"):
        
        prompt_complet = f"""Tu es le dirigeant de : {p_identite}.
Rédige une édition INÉDITE et ORIGINALE de newsletter LinkedIn destinée aux dirigeants, commerçants et artisans locaux.

SUJET À TRAITER : {sujet_final}
INSPIRATION DU MOMENT (facultative, à relier naturellement si pertinent) : {actu_du_jour}
STYLE ET TON : {p_style}

STRUCTURE OBLIGATOIRE À SUIVRE :
- Introduction : {p_intro}
- Développement : {p_corps}
- Conclusion : {p_conclusion}

RÈGLES VISUELLES STRICTES DE MISE EN PAGE :
- Aère le texte au maximum avec des paragraphes très courts (3 lignes max).
- Utilise un émoji pertinent en début de chaque bloc ou conseil (ex: 💡, 📐, 🖨️, 📍).
- Sépare CHAQUE grande partie (titre, introduction, chaque conseil, conclusion) par une ligne contenant uniquement : ---

Rédige uniquement la newsletter prête à publier sur LinkedIn, sans phrase d'introduction avant le titre."""

        with st.spinner("✍️ Rédaction de la newsletter par l'IA..."):
            texte_newsletter_genere, erreur_ia = appeler_gemini_patient(prompt_complet, temperature=0.7)

        if erreur_ia:
            st.error(f"Erreur lors de la génération : {erreur_ia}")
        elif texte_newsletter_genere:
            st.success("✅ Newsletter générée avec succès !")
            
            # Stockage en session pour persistance
            st.session_state["derniere_newsletter"] = texte_newsletter_genere
            st.session_state["derniere_image_nl"] = image_selectionnee

    # 4. Affichage persistant du résultat si présent en mémoire
    if "derniere_newsletter" in st.session_state and st.session_state["derniere_newsletter"]:
        st.subheader("📋 Résultat prêt à être publié")
        
        # Affichage de l'image retenue
        if "derniere_image_nl" in st.session_state and st.session_state["derniere_image_nl"]:
            st.image(st.session_state["derniere_image_nl"], caption="Visuel associé à la publication", use_container_width=True)
            
        # Affichage du texte dans un conteneur aéré avec bordure
        with st.container(border=True):
            st.markdown(st.session_state["derniere_newsletter"])
            
        # Bouton de copie / téléchargement rapide
        st.download_button(
            label="📥 Télécharger le texte de la newsletter (.txt)",
            data=st.session_state["derniere_newsletter"].encode("utf-8"),
            file_name="newsletter_imprimerie.txt",
            mime="text/plain",
            key="btn_download_txt_nl"
        )

# ==============================================================================
# ONGLET 2 : PROSPECTION INTELLIGENTE & CARTE INTERACTIVE
# ==============================================================================
with tab2:
    st.header("Trouver des prospects par code postal ou sur la carte")

    carte_active = bool(st.session_state["mode_carte_zone"])
    tous_types_actif = bool(st.session_state["check_tous_types"])

    col_loc, col_btn_carte, col_act_input, col_act_check = st.columns([2, 1.3, 1.8, 1.1])

    with col_loc:
        aide_cp = (
            "Sélection sur carte activée"
            if carte_active
            else "Tu peux mettre un seul code postal ou plusieurs séparés par une virgule."
        )
        codes_postaux = st.text_input(
            "Code(s) postal(aux) :",
            value=REGLAGES_PAR_DEFAUT["codes_postaux"],
            disabled=carte_active,
            help=aide_cp,
            key="input_codes_postaux"
        )

    with col_btn_carte:
        st.write("")
        st.write("")
        label_bouton_carte = (
            "❌ Revenir aux codes"
            if carte_active
            else "🗺️ Choisir carte"
        )
        if st.button(label_bouton_carte, use_container_width=True, key="btn_toggle_carte_mode"):
            st.session_state["mode_carte_zone"] = not carte_active
            st.rerun()

    with col_act_input:
        aide_activite = (
            "Tous types d'activités activé"
            if tous_types_actif
            else "Ex: boulangerie, artisans, agences..."
        )
        theme_recherche = st.text_input(
            "Thème / mot-clé :",
            value="commerces avec vitrine ou restaurants",
            disabled=tous_types_actif,
            help=aide_activite,
            key="input_theme_recherche"
        )

    with col_act_check:
        st.write("")
        st.write("")
        tous_types = st.checkbox(
            "🌐 Tous types",
            key="check_tous_types"
        )

    # --- SÉLECTEUR DE ZONE INTERACTIF ---
    if st.session_state["mode_carte_zone"]:
        lat_centre = float(st.session_state["reglages"]["zone_lat"])
        lon_centre = float(st.session_state["reglages"]["zone_lon"])
        nom_commune_clic, cps_clic, _ = identifier_commune_gps(lat_centre, lon_centre)

        col_z1, col_z2 = st.columns([3, 1])
        with col_z1:
            rayon_km = st.slider(
                "📏 Taille de la zone de recherche (rayon en km) :",
                min_value=1,
                max_value=50,
                value=int(reg["rayon_km"]),
                key="slider_rayon_km"
            )
        with col_z2:
            st.write("")
            if st.button("📍 Recentrer le point", key="btn_recentrer_gps_point"):
                sauvegarder_reglages_sur_disque({"zone_lat": 43.6667, "zone_lon": 4.0303})
                st.rerun()

        if nom_commune_clic:
            st.info(f"📍 **Variable de zone active pour l'IA :** {nom_commune_clic} ({', '.join(cps_clic)}) — rayon de **{rayon_km} km**. Clique sur la carte pour déplacer ce point.")
        else:
            st.info(f"📍 **Variable de zone active pour l'IA :** Coordonnées ({lat_centre}, {lon_centre}) — rayon de **{rayon_km} km**. Clique sur la carte pour déplacer ce point.")

        carte_zone = folium.Map(location=[43.65, 3.35], zoom_start=8)

        folium.Circle(
            location=[lat_centre, lon_centre],
            radius=rayon_km * 1000,
            color="#1f77b4",
            weight=2,
            fill=True,
            fill_color="#1f77b4",
            fill_opacity=0.2,
            tooltip=f"Zone active : {rayon_km} km"
        ).add_to(carte_zone)

        folium.Marker(
            location=[lat_centre, lon_centre],
            tooltip=f"{nom_commune_clic or 'Centre'} (rayon {rayon_km} km)",
            icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")
        ).add_to(carte_zone)

        retour_carte = st_folium(
            carte_zone,
            height=400,
            use_container_width=True,
            returned_objects=["last_clicked"],
            key="selecteur_zone_carte_interactif"
        )

        if retour_carte and retour_carte.get("last_clicked"):
            clic = retour_carte["last_clicked"]
            nouveau_coord = (round(clic["lat"], 5), round(clic["lng"], 5))
            if nouveau_coord != st.session_state["dernier_clic_carte"]:
                st.session_state["dernier_clic_carte"] = nouveau_coord
                sauvegarder_reglages_sur_disque({
                    "zone_lat": nouveau_coord[0],
                    "zone_lon": nouveau_coord[1],
                    "rayon_km": rayon_km
                })
                st.rerun()
    else:
        rayon_km = int(REGLAGES_PAR_DEFAUT["rayon_km"])
        villes_cp = identifier_communes_cp(codes_postaux)
        if villes_cp:
            st.caption(f"📍 **Variable de lieu détectée pour l'IA :** {', '.join(villes_cp[:6])} ({codes_postaux})")

    col_opt2, col_opt3 = st.columns([1.5, 2])
    with col_opt2:
        renouveler = st.checkbox(
            "🎲 Varier les entreprises à chaque recherche",
            value=True,
            key="check_renouveler_prosp_v2"
        )
    with col_opt3:
        limite = st.slider("Nombre maximum de prospects à afficher :", 1, 50, 10, key="slider_limite_prosp_v2")

    with st.expander("⚙️ Paramètres du prompt de prospection"):
        st.caption("Variables automatiques disponibles dans tes consignes : `{lieu_cible}` (ville/zone choisie) et `{rayon_km}` (taille du cercle).")
        prosp_offre = st.text_input("Tes services d'imprimerie à mettre en avant :", value=REGLAGES_PAR_DEFAUT["prosp_offre"], key="input_prosp_offre_v2")
        prosp_consignes = st.text_area("Consignes d'interprétation pour l'IA :", value=REGLAGES_PAR_DEFAUT["prosp_consignes"], height=130, key="area_prosp_consignes_v2")

        if st.button("💾 Enregistrer ces réglages Prospection", key="btn_save_prosp_settings_v2"):
            sauvegarder_reglages_sur_disque({
                "prosp_offre": prosp_offre,
                "prosp_consignes": prosp_consignes,
                "codes_postaux": codes_postaux,
                "rayon_km": rayon_km
            })
            st.success("✅ Tes réglages Prospection sont enregistrés !")

    # --- GESTION DE LA MÉMOIRE DES RÉSULTATS DANS SESSION_STATE ---
    if "tableau_prospects" not in st.session_state:
        st.session_state["tableau_prospects"] = None
    if "marqueurs_carte" not in st.session_state:
        st.session_state["marqueurs_carte"] = []

    # Bouton de recherche principale avec clé unique
    if st.button("🔍 Rechercher, analyser et afficher sur la carte", type="primary", key="btn_rechercher_prospects_unique"):
        lat_actuelle = float(st.session_state["reglages"]["zone_lat"])
        lon_actuelle = float(st.session_state["reglages"]["zone_lon"])

        if st.session_state["mode_carte_zone"]:
            nom_commune_actuelle, cps_actuels, _ = identifier_commune_gps(lat_actuelle, lon_actuelle)
            if nom_commune_actuelle:
                lieu_cible = f"un rayon de {rayon_km} km autour de {nom_commune_actuelle} ({', '.join(cps_actuels)})"
            else:
                lieu_cible = f"un rayon de {rayon_km} km autour du point GPS ({lat_actuelle}, {lon_actuelle})"
        else:
            villes_actuelles = identifier_communes_cp(codes_postaux)
            if villes_actuelles:
                lieu_cible = f"le secteur de {', '.join(villes_actuelles[:5])} (code postal : {codes_postaux})"
            else:
                lieu_cible = f"le code postal {codes_postaux}"

        # Spinner global pour bloquer l'UI et empêcher les clics multiples pendant le batching
        with st.spinner("🚀 Récupération du vivier et analyse par l'IA en cours... Patientez..."):
            vivier = chercher_entreprises_pool(
                mode_zone=st.session_state["mode_carte_zone"],
                codes_postaux_str=codes_postaux,
                zone_lat=lat_actuelle,
                zone_lon=lon_actuelle,
                rayon_km=rayon_km,
                mot_cle=theme_recherche,
                tous_types=tous_types,
                renouveler=renouveler
            )

        st.info(f"📊 Nombre d'entreprises trouvées dans le vivier : {len(vivier)}")

        if not vivier:
            st.error(f"Aucune entreprise trouvée sur {lieu_cible}. Essaie d'agrandir le rayon ou de vérifier le code postal.")
            st.session_state["tableau_prospects"] = None
            st.session_state["marqueurs_carte"] = []
        else:
            nb_cibles = min(limite, len(vivier))
            taille_lot = 10
            tous_resultats_bruts = []
            
            progress_bar = st.progress(0, text="🚀 Analyse des lots par l'IA...")

            for i in range(0, nb_cibles, taille_lot):
                lot_vivier = vivier[i:i + taille_lot]
                lot_num_debut = i + 1
                
                lignes_vivier = []
                for idx_relatif, ent in enumerate(lot_vivier, start=lot_num_debut):
                    dist_txt = f" | Distance: {ent['distance_km']} km" if ent.get("distance_km") is not None else ""
                    lignes_vivier.append(
                        f"{idx_relatif}. Nom: {ent['nom']} | Code NAF: {ent['naf']} | Créée en: {ent['creation']} | Adresse locale: {ent['adresse']}{dist_txt}"
                    )

                if tous_types:
                    regle_selection = f"""1. L'utilisateur a coché "TOUS TYPES D'ACTIVITÉS" : sélectionne toutes les entreprises valides de ce lot (jusqu'à {len(lot_vivier)}), de manière totalement diversifiée dans la liste fournie."""
                else:
                    regle_selection = f"""1. RÈGLE DE SÉLECTION DES PROSPECTS : Analyse ce lot d'entreprises (numéros {lot_num_debut} à {lot_num_debut + len(lot_vivier) - 1}).
- Inspecte attentivement le nom et le code NAF de chaque entreprise.
- Sélectionne en priorité les entreprises ayant un rapport réel avec le thème : '{theme_recherche}'."""

                consignes_interpretees = (
                    prosp_consignes
                    .replace("{lieu_cible}", lieu_cible)
                    .replace("{rayon_km}", str(rayon_km))
                )

                prompt_prospection = f"""Tu es le directeur commercial d'une entreprise spécialisée dans : {prosp_offre}.

CONTEXTE GÉOGRAPHIQUE DE LA RECHERCHE :
L'utilisateur cible précisément : {lieu_cible}.
Voici un sous-ensemble de {len(lot_vivier)} entreprises locales (Lot {(i // taille_lot) + 1}) :
{chr(10).join(lignes_vivier)}

MISSION :
{regle_selection}
2. Pour chaque entreprise retenue de ce lot, indique son numéro exact (`numero_entreprise` entre {lot_num_debut} et {lot_num_debut + len(lot_vivier) - 1}).
3. Explique en 1 phrase simple ce que fait cette entreprise (`interpretation_activite`).
4. **Détecte si l'entreprise a un projet, un chantier en cours, des travaux ou une ouverture récente/future** (`projet_chantier`). Si rien n'indique un projet particulier, écris "Pas de chantier/projet visible".
5. Donne une note stricte sur 10 et applique ces consignes :
{consignes_interpretees}"""

                texte_json, erreur_ia = appeler_gemini_patient(prompt_prospection, schema=ListeAnalyses, temperature=0.75)

                if texte_json:
                    try:
                        donnees_lot = ListeAnalyses.model_validate_json(texte_json)
                        tous_resultats_bruts.extend(donnees_lot.resultats)
                    except Exception as e:
                        pass

                progres = min(1.0, (i + taille_lot) / nb_cibles)
                progress_bar.progress(progres, text=f"Analyse en cours... Lot {(i // taille_lot) + 1} traité.")

            progress_bar.empty()

            tableau = []
            marqueurs_carte = []

            for item in tous_resultats_bruts:
                index_reel = item.numero_entreprise - 1
                if 0 <= index_reel < len(vivier):
                    note_propre = round(item.note_pertinence / 10) if item.note_pertinence > 10 else item.note_pertinence
                    note_propre = max(1, min(10, note_propre))

                    if (not tous_types) and note_propre < 5:
                        continue

                    ent = vivier[index_reel]
                    ligne_tab = {
                        "Entreprise": ent["nom"],
                        "Activité détectée": item.interpretation_activite,
                        "Projet / Chantier": item.projet_chantier,
                        "Créée en": ent["creation"],
                        "Adresse locale": ent["adresse"],
                        "Note /10": note_propre,
                        "Produit à proposer": item.produit_imprimerie,
                        "Message LinkedIn": item.message_linkedin,
                        "Objet Email": item.objet_email
                    }
                    if ent.get("distance_km") is not None:
                        ligne_tab["Distance"] = f"{ent['distance_km']} km"
                    tableau.append(ligne_tab)

                    if ent.get("lat") and ent.get("lon"):
                        marqueurs_carte.append({
                            "lat": ent["lat"],
                            "lon": ent["lon"],
                            "nom": ent["nom"],
                            "adresse": ent["adresse"],
                            "produit": item.produit_imprimerie,
                            "note": note_propre
                        })

            if tableau:
                tableau.sort(key=lambda x: x["Note /10"], reverse=True)
                st.session_state["tableau_prospects"] = tableau
                st.session_state["marqueurs_carte"] = marqueurs_carte
                st.rerun()
            else:
                st.warning("Aucune entreprise pertinente retenue sur cette tentative.")

    # --- AFFICHAGE PERSISTANT DES RÉSULTATS ---
    if st.session_state["tableau_prospects"] is not None:
        tableau = st.session_state["tableau_prospects"]
        marqueurs_carte = st.session_state["marqueurs_carte"]
        
        st.success(f"✅ {len(tableau)} prospect(s) en mémoire.")

        if st.button("🗑️ Supprimer les données obtenues", key="btn_supprimer_donnees_memoire"):
            st.session_state["tableau_prospects"] = None
            st.session_state["marqueurs_carte"] = []
            st.rerun()

        tableau_affichage = []
        for row in tableau:
            r_copie = row.copy()
            r_copie["Map"] = "📍"
            tableau_affichage.append(r_copie)

        evenement_selection = st.dataframe(
            tableau_affichage,
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            key="table_prospects_select_unique"
        )

        buffer_csv = io.StringIO()
        writer = csv.DictWriter(buffer_csv, fieldnames=tableau[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(tableau)
        st.download_button(
            label="📥 Télécharger ce tableau pour Excel (.csv)",
            data=buffer_csv.getvalue().encode("utf-8-sig"),
            file_name="prospection_imprimerie.csv",
            mime="text/csv",
            key="btn_download_csv_prosp_unique"
        )

        if marqueurs_carte:
            st.subheader("🗺️ Localisation et noms des prospects trouvés")
            
            centre_lat = sum(m["lat"] for m in marqueurs_carte) / len(marqueurs_carte)
            centre_lon = sum(m["lon"] for m in marqueurs_carte) / len(marqueurs_carte)
            zoom_carte = 12

            try:
                lignes_selectionnees = evenement_selection.selection.rows
                if lignes_selectionnees:
                    idx_selectionne = lignes_selectionnees[0]
                    nom_entreprise_selectionnee = tableau[idx_selectionne]["Entreprise"]
                    prospect_cible = next((m for m in marqueurs_carte if m["nom"] == nom_entreprise_selectionnee), None)
                    if prospect_cible:
                        centre_lat, centre_lon = prospect_cible["lat"], prospect_cible["lon"]
                        zoom_carte = 16
            except Exception:
                pass

            carte_resultats = folium.Map(location=[centre_lat, centre_lon], zoom_start=zoom_carte)

            if st.session_state["mode_carte_zone"]:
                folium.Circle(
                    location=[float(st.session_state["reglages"]["zone_lat"]), float(st.session_state["reglages"]["zone_lon"])],
                    radius=rayon_km * 1000,
                    color="#1f77b4",
                    weight=1,
                    fill=True,
                    fill_opacity=0.08
                ).add_to(carte_resultats)

            for m in marqueurs_carte:
                fiche_html = (
                    f"<b>{m['nom']}</b> (Note : {m['note']}/10)<br>"
                    f"<i>{m['adresse']}</i><br><br>"
                    f"<b>Idée :</b> {m['produit']}"
                )
                folium.Marker(
                    location=[m["lat"], m["lon"]],
                    popup=folium.Popup(fiche_html, max_width=280),
                    tooltip=folium.Tooltip(f"<b>{m['nom']}</b>", permanent=False),
                    icon=folium.Icon(color="green", icon="briefcase", prefix="fa")
                ).add_to(carte_resultats)

            st_folium(
                carte_resultats,
                height=460,
                use_container_width=True,
                returned_objects=[],
                key="carte_resultats_prospects_unique"
            )
