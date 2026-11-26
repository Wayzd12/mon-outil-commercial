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
    "p_identite": "Imprimerie moderne (cartes de visite, flyers, brochures, menus, affiches, enseignes de façade, logos sur bâtiment, vitrophanie, panneaux de chantier)",
    "p_style": "Chaleureux, concret, direct, comme un artisan-conseil local qui parle simplement sans jargon",
    "p_intro": "Commence par un titre accrocheur (moins de 65 caractères), puis une introduction de 3 lignes maximum qui part d'une situation vécue par les commerçants ou artisans locaux.",
    "p_corps": "Donne 3 conseils pratiques et actionnables liés à l'impression ou la signalétique. Pour chaque conseil, ajoute une ligne en gras '**Ce que ça change pour vous :**'.",
    "p_conclusion": "Termine par 2 lignes de conclusion positives et une question ouverte simple pour inciter les lecteurs à commenter.",
    "prosp_offre": "Impression petit et grand format : cartes de visite, flyers, brochures, menus, étiquettes, enseignes de façade, logos en relief, vitrophanie, panneaux de chantier, marquage véhicule",
    "prosp_consignes": "1. Tiens compte de la localisation précise ({lieu_cible}) et de l'adresse exacte de chaque entreprise.\n2. Sélectionne uniquement les entreprises qui ont un vrai rapport avec le thème demandé (en décodant leur code activité NAF et leur nom).\n3. Adapte le produit recommandé à l'emplacement (avenue/zone = grande enseigne ou panneau ; rue commerçante = vitrine, flyers ou menus ; artisan = panneaux de chantier et cartes de visite) et à l'année de création (récente = pack création ; ancienne = modernisation).\n4. Écris un message LinkedIn court (max 230 caractères), poli, ancré localement sur {lieu_cible} et jamais répétitif d'une ligne à l'autre.\n5. Ne sélectionne que des entreprises encore ouvertes ( prend en compte le bâtiment choisi et non pas le siège de l'entreprise ) , tu ne dois pas sélectionner d'entreprises qui ont fermés ( toujours le bâtiment choisi )",
    "codes_postaux": "34670",
    "zone_lat": 43.6667,
    "zone_lon": 4.0303,
    "rayon_km": 10
}

def charger_reglages():
    donnees = REGLAGES_PAR_DEFAUT.copy()
    if os.path.exists(FICHIER_REGLAGES):
        try:
            with open(FICHIER_REGLAGES, "r", encoding="utf-8") as f:
                sauvegarde = json.load(f)
                donnees.update(sauvegarde)
        except Exception:
            pass
    return donnees

def recuperer_image_ia_securisee(prompt):
    """Tente de récupérer l'image IA avec un vrai délai d'attente et 2 essais max."""
    prompt_encoded = urllib.parse.quote(prompt)
    url = f"https://pollinations.ai/p/{prompt_encoded}?width=600&height=600&nologo=true&seed={random.randint(1, 10000)}"
    
    for essai in range(2):
        try:
            # On laisse jusqu'à 30 secondes pour que le serveur de l'IA ait le temps de générer l'image
            rep = requests.get(url, timeout=30)
            
            # On vérifie que la réponse est bien un succès HTTP et que c'est bien une image
            if rep.status_code == 200 and rep.headers.get('content-type', '').startswith('image/'):
                return rep.content  # Succès ! On renvoie l'image
        except Exception:
            pass
            
        time.sleep(2)  # Petite pause de 2 secondes avant de retenter si le premier essai a échoué
        
    return None

def sauvegarder_reglages_sur_disque(nouveaux_reglages: dict):
    st.session_state["reglages"].update(nouveaux_reglages)
    try:
        with open(FICHIER_REGLAGES, "w", encoding="utf-8") as f:
            json.dump(st.session_state["reglages"], f, ensure_ascii=False, indent=2)
    except Exception:
        pass

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

def _appel_unique_ia(modele: str, prompt: str, config_args: dict) -> str:
    response = client.models.generate_content(
        model=modele,
        contents=prompt,
        config=types.GenerateContentConfig(**config_args)
    )
    return response.text

def appeler_gemini_patient(prompt: str, schema=None, temperature: float = 0.85):
    """Appelle toujours la vraie IA Google avec chronomètre de 20s max par essai."""
    modeles_actifs = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]
    zone_statut = st.empty()
    derniere_erreur = ""

    config_args = {"temperature": temperature}
    if schema is not None:
        config_args["response_mime_type"] = "application/json"
        config_args["response_schema"] = schema

    for cycle in range(1, 4):
        for modele in list(modeles_actifs):
            zone_statut.info(f"⏳ L'IA analyse et rédige sur mesure (essai {cycle}/3 — {modele})... 20 sec max.")
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

class ListeAnalyses(BaseModel):
    resultats: list[ProspectSelectionne]

class NewsletterReponse(BaseModel):
    texte_newsletter: str = Field(description="Le texte complet et prêt à publier de la newsletter")
    prompt_image_humour: str = Field(description="Description détaillée en anglais d'une illustration créative, humoristique ou métaphorique en lien avec la situation initiale ou la blague du texte")
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
    """Récupère un vivier ciblé d'entreprises locales en rapport avec le mot-clé."""
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

        if not tous_types and mots_cles_list and code_dept:
            url_search = "https://recherche-entreprises.api.gouv.fr/search"
            requetes_q = [mot_cle.strip()] if len(mots_cles_list) > 1 else []
            requetes_q.extend(mots_cles_list)
            for terme in dict.fromkeys(requetes_q):
                for page_q in ([1, random.randint(2, 4)] if renouveler else [1, 2]):
                    try:
                        rep_q = requests.get(
                            url_search,
                            params={
                                "q": terme,
                                "departement": code_dept,
                                "etat_administratif": "A",
                                "per_page": 25,
                                "page": page_q
                            },
                            timeout=8
                        )
                        if rep_q.status_code == 200:
                            ajouter_depuis_reponse(rep_q.json(), [])
                    except Exception:
                        pass
                    if len(vivier_brut) >= 35:
                        break
                if len(vivier_brut) >= 35:
                    break

        if tous_types or len(vivier_brut) < 15:
            url_geo = "https://recherche-entreprises.api.gouv.fr/near_point"
            pages_geo = [1, 2, random.randint(3, 5)] if renouveler else [1, 2, 3]
            for p in dict.fromkeys(pages_geo):
                try:
                    rep = requests.get(
                        url_geo,
                        params={
                            "lat": round(zone_lat, 5),
                            "long": round(zone_lon, 5),
                            "radius": rayon_km,
                            "per_page": 25,
                            "page": p
                        },
                        timeout=10
                    )
                    if rep.status_code == 200:
                        ajouter_depuis_reponse(rep.json(), [])
                except Exception:
                    pass
                if len(vivier_brut) >= 45:
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
                            if renouveler and total_pages > 1:
                                rep2 = requests.get(
                                    url,
                                    params={
                                        "q": terme,
                                        "code_postal": cp,
                                        "etat_administratif": "A",
                                        "per_page": 25,
                                        "page": random.randint(2, min(total_pages, 5))
                                    },
                                    timeout=8
                                )
                                if rep2.status_code == 200:
                                    ajouter_depuis_reponse(rep2.json(), codes)
                    except Exception:
                        pass

            if tous_types or len(vivier_brut) < 8:
                pages_larges = [1, 2] if not renouveler else [1, random.randint(2, 4)]
                for p_large in dict.fromkeys(pages_larges):
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

    return liste_propre[:40]

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

    reg = st.session_state["reglages"]

    with st.expander("⚙️ Paramètres du prompt (Introduction, Style, Corps, Conclusion)"):
        st.caption("Modifie ces réglages puis clique sur 'Enregistrer mes réglages' pour les garder :")

        p_identite = st.text_input("Ton entreprise & tes produits :", value=reg["p_identite"])
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            p_style = st.text_input("Style et ton d'écriture :", value=reg["p_style"])
            p_intro = st.text_area("Consigne pour l'Introduction :", value=reg["p_intro"], height=100)
        with col_p2:
            p_corps = st.text_area("Consigne pour le Corps (les conseils) :", value=reg["p_corps"], height=100)
            p_conclusion = st.text_area("Consigne pour la Conclusion :", value=reg["p_conclusion"], height=100)

        if st.button("💾 Enregistrer ces réglages Newsletter"):
            sauvegarder_reglages_sur_disque({
                "p_identite": p_identite,
                "p_style": p_style,
                "p_intro": p_intro,
                "p_corps": p_corps,
                "p_conclusion": p_conclusion
            })
            st.success("✅ Tes réglages Newsletter sont enregistrés !")

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

        texte_json, erreur = appeler_gemini_patient(prompt_complet, schema=NewsletterReponse, temperature=0.95)

        if texte_json:
            try:
                donnees_nl = NewsletterReponse.model_validate_json(texte_json)
                st.success("✅ Newsletter rédigée par l'IA !")
                
                # --- DIVISION DE LA PAGE EN 2 COLONNES ---
                col_texte, col_images = st.columns([1.5, 1])
                
                with col_texte:
                    st.subheader("Texte de la newsletter")
                    # Restauration propre des retours à la ligne
                    texte_propre = donnees_nl.texte_newsletter.replace("\\n", "\n")
                    st.text_area("Copie-colle ce texte sur LinkedIn :", value=texte_propre, height=485, label_visibility="collapsed")
                
                with col_images:
                    st.subheader("Visuels")
                    
                    # 1. Tentative de récupération de l'image IA avec le cycle de sécurité (3s d'attente si occupé)
                    with st.spinner("Génération des visuels en cours..."):
                        img_bytes = recuperer_image_ia_securisee(donnees_nl.prompt_image_humour)
                    
                    # 2. Vraie photo professionnelle Unsplash (instantanée)
                    cat = donnees_nl.categorie_produit.lower()
                    if "card" in cat:
                        unsplash_id = "1633533824538-2321522f77dd"
                    elif "store" in cat or "sign" in cat:
                        unsplash_id = "1513519245088-0e12902e5a38"
                    elif "restaurant" in cat:
                        unsplash_id = "1517248135467-4c7edcad34c4"
                    else:
                        unsplash_id = "1562564055-71e051d33c19"
                    url_img_pro = f"https://images.unsplash.com/photo-{unsplash_id}?w=600&h=600&fit=crop"
                    
                    # Conversion de l'image IA en données affichables si elle a réussi
                    src_ia = ""
                    if img_bytes:
                        import base64
                        encoded_img = base64.b64encode(img_bytes).decode('utf-8')
                        src_ia = f"data:image/jpeg;base64,{encoded_img}"
                    
                    # Affichage côte à côte propre via HTML, sans aucune légende
                    if src_ia:
                        html_images = f"""
                        <div style="display: flex; gap: 10px; height: 485px; align-items: stretch; margin-top: 8px;">
                            <div style="flex: 1; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                <img src="{src_ia}" style="width: 100%; height: 100%; object-fit: cover;">
                            </div>
                            <div style="flex: 1; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                <img src="{url_img_pro}" style="width: 100%; height: 100%; object-fit: cover;">
                            </div>
                        </div>
                        """
                        st.markdown(html_images, unsafe_allow_html=True)
                    else:
                        st.warning("⏳ Image en cours de chargement (serveurs IA occupés)... Réessaie dans un instant.")
                        st.image(url_img_pro, use_container_width=True)
                
            except Exception as e:
                st.error(f"Erreur de lecture de la réponse IA : {e}")
        else:
            st.error(f"❌ L'IA n'a pas pu répondre. Détail : {erreur}")


# ==============================================================================
# ONGLET 2 : PROSPECTION INTELLIGENTE & CARTE INTERACTIVE
# ==============================================================================
with tab2:
    st.header("Trouver des prospects par code postal ou sur la carte")

    carte_active = bool(st.session_state["mode_carte_zone"])
    tous_types_actif = bool(st.session_state["check_tous_types"])

    col_loc, col_btn_carte, col_act = st.columns([2, 1.3, 2.2])

    with col_loc:
        aide_cp = (
            "Sélection sur carte activée"
            if carte_active
            else "Tu peux mettre un seul code postal (ex: 34670) ou plusieurs séparés par une virgule."
        )
        codes_postaux = st.text_input(
            "Code(s) postal(aux) :",
            value=reg["codes_postaux"],
            disabled=carte_active,
            help=aide_cp
        )

    with col_btn_carte:
        st.write("")
        st.write("")
        label_bouton_carte = (
            "❌ Revenir aux codes postaux"
            if carte_active
            else "🗺️ Choisir sur la carte"
        )
        if st.button(label_bouton_carte, use_container_width=True):
            st.session_state["mode_carte_zone"] = not carte_active
            st.rerun()

    with col_act:
        aide_activite = (
            "Tous types d'activités activé"
            if tous_types_actif
            else "Ex: boulangerie, artisans de chantier, jeunes entreprises, agences..."
        )
        theme_recherche = st.text_input(
            "Thème ou mot-clé à interpréter par l'IA :",
            value="commerces avec vitrine ou restaurants",
            disabled=tous_types_actif,
            help=aide_activite
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
                value=int(reg["rayon_km"])
            )
        with col_z2:
            st.write("")
            if st.button("📍 Recentrer le point"):
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
            key="selecteur_zone_carte"
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
        rayon_km = int(reg["rayon_km"])
        villes_cp = identifier_communes_cp(codes_postaux)
        if villes_cp:
            st.caption(f"📍 **Variable de lieu détectée pour l'IA :** {', '.join(villes_cp[:6])} ({codes_postaux})")

    col_opt1, col_opt2, col_opt3 = st.columns([2, 2, 2])
    with col_opt1:
        tous_types = st.checkbox(
            "🌐 Tous types d'activités",
            key="check_tous_types"
        )
    with col_opt2:
        renouveler = st.checkbox(
            "🎲 Varier les entreprises à chaque recherche",
            value=True
        )
    with col_opt3:
        limite = st.slider("Nombre maximum de prospects à afficher :", 1, 50, 10)

    with st.expander("⚙️ Paramètres du prompt de prospection"):
        st.caption("Variables automatiques disponibles dans tes consignes : `{lieu_cible}` (ville/zone choisie) et `{rayon_km}` (taille du cercle).")
        prosp_offre = st.text_input("Tes services d'imprimerie à mettre en avant :", value=reg["prosp_offre"])
        prosp_consignes = st.text_area("Consignes d'interprétation pour l'IA :", value=reg["prosp_consignes"], height=130)

        if st.button("💾 Enregistrer ces réglages Prospection"):
            sauvegarder_reglages_sur_disque({
                "prosp_offre": prosp_offre,
                "prosp_consignes": prosp_consignes,
                "codes_postaux": codes_postaux,
                "rayon_km": rayon_km
            })
            st.success("✅ Tes réglages Prospection sont enregistrés !")

    if st.button("🔍 Rechercher, analyser et afficher sur la carte", type="primary"):
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

        if not vivier:
            st.error(f"Aucune entreprise trouvée sur {lieu_cible}. Essaie d'agrandir le rayon ou de vérifier le code postal.")
        else:
            lignes_vivier = []
            for idx, ent in enumerate(vivier, start=1):
                dist_txt = f" | Distance: {ent['distance_km']} km" if ent.get("distance_km") is not None else ""
                lignes_vivier.append(
                    f"{idx}. Nom: {ent['nom']} | Code NAF: {ent['naf']} | Créée en: {ent['creation']} | Adresse locale: {ent['adresse']}{dist_txt}"
                )

            if tous_types:
                regle_selection = f"""1. L'utilisateur a coché "TOUS TYPES D'ACTIVITÉS" : sélectionne jusqu'à {min(limite, len(vivier))} entreprises variées et pertinentes (commerces, artisans, sociétés locales) dans cette liste."""
            else:
                regle_selection = f"""1. RÈGLE DE SÉLECTION DES PROSPECTS : L'objectif est d'atteindre {nb_prospects} prospects détaillés.
- Inspecte attentivement le nom et le code NAF de chaque entreprise.
- Priorise en premier les entreprises ayant un rapport réel avec le thème : '{theme_recherche}'.
- Si le vivier de prospects pertinents est épuisé avant d'arriver à {nb_prospects}, tu peux compléter la liste avec d'autres entreprises du vivier (même si elles ont moins de rapport avec le thème), mais tu dois le préciser clairement dans leur description.
- Prends tout ton temps pour structurer ta réponse, aucune précipitation n'est requise. Sois exhaustif."""

            consignes_interpretees = (
                prosp_consignes
                .replace("{lieu_cible}", lieu_cible)
                .replace("{rayon_km}", str(rayon_km))
            )

            prompt_prospection = f"""Tu es le directeur commercial d'une entreprise spécialisée dans : {prosp_offre}.

CONTEXTE GÉOGRAPHIQUE DE LA RECHERCHE :
L'utilisateur cible précisément : {lieu_cible}.
Voici une liste de {len(vivier)} vraies entreprises locales ayant un établissement actif sur place :
{chr(10).join(lignes_vivier)}

MISSION :
{regle_selection}
2. Pour chaque entreprise retenue, indique son numéro exact (`numero_entreprise` entre 1 et {len(vivier)}).
3. Explique en 1 phrase simple ce que fait cette entreprise (`interpretation_activite`).
4. Donne une note stricte sur 10 (entre 1 et 10, jamais sur 100 — mets moins de 5 si le rapport avec '{theme_recherche}' est trop faible) et applique ces consignes :
{consignes_interpretees}"""

            texte_json, erreur_ia = appeler_gemini_patient(prompt_prospection, schema=ListeAnalyses, temperature=0.7)

            if not texte_json:
                st.error(f"❌ L'IA n'a pas pu analyser les prospects. Détail : {erreur_ia}")
            else:
                try:
                    donnees = ListeAnalyses.model_validate_json(texte_json)
                    tableau = []
                    marqueurs_carte = []

                    for item in donnees.resultats:
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
                        st.success(f"✅ {len(tableau)} prospect(s) pertinent(s) trouvé(s) sur {lieu_cible} !")

                        if (not tous_types) and len(tableau) < limite:
                            st.info(f"ℹ️ Seulement {len(tableau)} entreprise(s) correspondent réellement à « {theme_recherche} » dans cette zone (les entreprises sans rapport ont été écartées).")

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

                        if marqueurs_carte:
                            st.subheader("🗺️ Localisation et noms des prospects trouvés")
                            centre_lat = sum(m["lat"] for m in marqueurs_carte) / len(marqueurs_carte)
                            centre_lon = sum(m["lon"] for m in marqueurs_carte) / len(marqueurs_carte)

                            carte_resultats = folium.Map(location=[centre_lat, centre_lon], zoom_start=12)

                            if st.session_state["mode_carte_zone"]:
                                folium.Circle(
                                    location=[lat_actuelle, lon_actuelle],
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
                                    tooltip=folium.Tooltip(
                                        f"<b>{m['nom']}</b>",
                                        permanent=True,
                                        direction="top",
                                        sticky=False,
                                        offset=(0, -36)
                                    ),
                                    icon=folium.Icon(color="green", icon="briefcase", prefix="fa")
                                ).add_to(carte_resultats)

                            st_folium(
                                carte_resultats,
                                height=460,
                                use_container_width=True,
                                returned_objects=[],
                                key="carte_resultats_prospects"
                            )
                    else:
                        if tous_types:
                            st.warning("L'IA n'a retenu aucune entreprise sur cette tentative. Clique à nouveau sur Rechercher.")
                        else:
                            st.warning(f"Aucune entreprise en rapport avec « {theme_recherche} » n'a été trouvée sur {lieu_cible}. Essaie d'agrandir le rayon ou d'utiliser un mot-clé plus général.")
                except Exception as e:
                    st.error(f"Erreur de lecture de la réponse IA : {e}")
