import streamlit as st
import os
import json
import math
import time
import random
import io
import csv
import requests
import feedparser
import folium
from streamlit_folium import st_folium
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

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

# --- 3. GESTION DES RÉGLAGES SAUVEGARDÉS ---
FICHIER_REGLAGES = "mes_reglages_imprimerie.json"

REGLAGES_PAR_DEFAUT = {
    "p_identite": "Imprimerie moderne (cartes de visite, flyers, brochures, menus, affiches, enseignes de façade, logos sur bâtiment, vitrophanie, panneaux de chantier)",
    "p_style": "Chaleureux, concret, direct, comme un artisan-conseil local qui parle simplement sans jargon",
    "p_intro": "Commence par un titre accrocheur (moins de 65 caractères), puis une introduction de 3 lignes maximum qui part d'une situation vécue par les commerçants ou artisans locaux.",
    "p_corps": "Donne 3 conseils pratiques et actionnables liés à l'impression ou la signalétique. Pour chaque conseil, ajoute une ligne en gras '**Ce que ça change pour vous :**'.",
    "p_conclusion": "Termine par 2 lignes de conclusion positives et une question ouverte simple pour inciter les lecteurs à commenter.",
    "prosp_offre": "Impression petit et grand format : cartes de visite, flyers, brochures, menus, étiquettes, enseignes de façade, logos en relief, vitrophanie, panneaux de chantier, marquage véhicule",
    "prosp_consignes": "1. Tiens compte de la localisation précise ({lieu_cible}) et de l'adresse exacte de chaque entreprise.\n2. Sélectionne uniquement les entreprises qui ont un vrai rapport avec le thème demandé (en décodant leur code activité NAF et leur nom).\n3. Adapte le produit recommandé à l'emplacement (avenue/zone = grande enseigne ou panneau ; rue commerçante = vitrine, flyers ou menus ; artisan = panneaux de chantier et cartes de visite) et à l'année de création (récente = pack création ; ancienne = modernisation).\n4. Écris un message LinkedIn court (max 230 caractères), poli, ancré localement sur {lieu_cible} et jamais répétitif d'une ligne à l'autre.",
    "appel_atouts": "Imprimerie locale réactive : déplacement gratuit sur place pour prendre les cotes ou montrer des échantillons de papier/matières, conseil graphique, délais courts et suivi personnalisé.",
    "appel_objections": "Je commande déjà sur Internet (Vistaprint, etc.), J'ai déjà mon imprimeur habituel, Je n'ai pas le temps / envoyez-moi un mail, C'est trop cher pour moi",
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

if "derniers_prospects" not in st.session_state:
    st.session_state["derniers_prospects"] = []

# --- 4. CONNEXION À L'IA GOOGLE ---
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

# --- 7. OUTILS POUR LE SCRIPT D'APPEL & OBJECTIONS ---
class ObjectionReponse(BaseModel):
    objection_client: str
    reponse_conseillee: str

class ScriptAppelComplet(BaseModel):
    accroche_15_secondes: str
    questions_decouverte: list[str]
    argumentaire_produit: str
    proposition_rdv: str
    objections: list[ObjectionReponse]

# --- 8. BARRE DE SAUVEGARDE PERMANENTE DES RÉGLAGES ---
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

# --- 9. INTERFACE DU SITE (3 ONGLETS) ---
tab1, tab2, tab3 = st.tabs([
    "📝 Ma Newsletter LinkedIn",
    "🎯 Prospection & Carte Locale",
    "📞 Script d'Appel & Objections"
])

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

        texte_genere, erreur = appeler_gemini_patient(prompt_complet, schema=None, temperature=0.95)

        if texte_genere:
            st.success("✅ Newsletter rédigée par l'IA !")
            st.info(f"**Sujet traité :** {sujet_final}")
            st.text_area("Copie-colle ce texte sur LinkedIn :", value=texte_genere, height=450)
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
        limite = st.slider("Nombre maximum de prospects à afficher :", 3, 12, 5)

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
                regle_selection = f"""1. RÈGLE STRICTE DE PERTINENCE : L'utilisateur recherche uniquement des entreprises ayant un rapport réel avec le mot-clé / thème : '{theme_recherche}'.
   - Inspecte attentivement le nom et le code NAF de chaque entreprise.
   - Ne retiens QUE celles qui ont un minimum de rapport avec '{theme_recherche}' (jusqu'à {min(limite, len(vivier))} maximum).
   - INTERDICTION ABSOLUE de compléter la liste avec des entreprises hors-sujet ou prises au hasard pour atteindre {limite} résultats : s'il n'y a que 1, 2 ou 3 entreprises pertinentes, ne renvoie QUE celles-là. S'il n'y en a aucune, renvoie une liste vide `[]`."""

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
                        st.session_state["derniers_prospects"] = tableau
                        st.success(f"✅ {len(tableau)} prospect(s) pertinent(s) trouvé(s) sur {lieu_cible} !")

                        if (not tous_types) and len(tableau) < limite:
                            st.info(f"ℹ️ Seulement {len(tableau)} entreprise(s) correspondent réellement à « {theme_recherche} » dans cette zone (les entreprises sans rapport ont été écartées).")

                        st.dataframe(tableau, use_container_width=True)

                        # Export CSV pour Excel
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

                        # Carte des résultats avec les NOMS figés juste au-dessus des points
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

# ==============================================================================
# ONGLET 3 : SCRIPT D'APPEL TÉLÉPHONIQUE & RÉPONSES AUX OBJECTIONS
# ==============================================================================
with tab3:
    st.header("Préparer un appel commercial et répondre aux objections")

    PRODUITS_APPEL = [
        "Cartes de visite (papier épais 350g/400g, pelliculage mat, vernis sélectif)",
        "Enseigne de façade & logo en relief (Dibond, lettres découpées, bandeau lumineux)",
        "Panneaux de chantier & immobiliers (Akilux alvéolaire, Dibond rigide)",
        "Flyers, dépliants 2 ou 3 volets & brochures commerciales",
        "Vitrophanie & habillage de vitrine (adhésif micro-perforé, lettrage)",
        "Marquage de véhicule utilitaire (flocage logo, coordonnées, semi-covering)",
        "Menus, sets de table, affiches & stop-trottoirs pour commerces / restaurants",
        "Kakémonos, roll-ups & stands pour salons et événements"
    ]

    PROFILS_CLIENTS = [
        "Artisan du bâtiment / travaux (maçon, plombier, électricien, paysagiste...)",
        "Commerçant / Boutique avec vitrine",
        "Restaurant / Café / Boulangerie / Traiteur",
        "Nouvelle entreprise qui vient d'ouvrir",
        "PME / Agence immobilière / Cabinet de services",
        "Autre profil (préciser ci-dessous)"
    ]

    col_ap1, col_ap2 = st.columns(2)
    with col_ap1:
        produit_appel = st.selectbox("1. Produit d'imprimerie à vendre :", PRODUITS_APPEL)
        produit_precision = st.text_input(
            "Précision sur l'offre ou promotion (facultatif) :",
            placeholder="Ex: pack 500 cartes + 1000 flyers, devis gratuit sur place..."
        )
    with col_ap2:
        profil_client = st.selectbox("2. Type de client appelé :", PROFILS_CLIENTS)
        objectif_appel = st.selectbox(
            "3. Objectif de l'appel :",
            [
                "Décrocher un rendez-vous rapide sur place (montrer des échantillons / prendre les cotes)",
                "Se faire connaître comme imprimerie locale et envoyer un devis / catalogue",
                "Relancer un besoin saisonnier ou une ouverture récente"
            ]
        )

    # Option pratique : importer un prospect trouvé dans l'onglet 2 ou saisir un nom manuellement
    options_prospects = ["Saisie manuelle (ou appel générique sans nom précis)"]
    for p in st.session_state["derniers_prospects"]:
        options_prospects.append(f"{p['Entreprise']} ({p['Adresse locale']})")

    col_cib1, col_cib2 = st.columns(2)
    with col_cib1:
        choix_prospect_existant = st.selectbox(
            "4. Reprendre un prospect trouvé dans l'onglet 2 (facultatif) :",
            options_prospects
        )
    with col_cib2:
        cible_manuelle = st.text_input(
            "Ou écrire le nom de l'entreprise / ville appelée :",
            placeholder="Ex: Garage du Soleil à Saint-Brès"
        )

    with st.expander("⚙️ Paramètres du script d'appel (Atouts locaux & Objections fréquentes)"):
        st.caption("Personnalise tes points forts et les objections que tu entends le plus souvent :")
        appel_atouts = st.text_area(
            "Tes points forts d'imprimeur local :",
            value=reg["appel_atouts"],
            height=80
        )
        appel_objections = st.text_area(
            "Liste des objections clients à traiter (séparées par une virgule) :",
            value=reg["appel_objections"],
            height=80
        )
        if st.button("💾 Enregistrer ces réglages Appel"):
            sauvegarder_reglages_sur_disque({
                "appel_atouts": appel_atouts,
                "appel_objections": appel_objections
            })
            st.success("✅ Tes réglages d'appel sont enregistrés !")

    if st.button("📞 Générer mon script d'appel et mes réponses aux objections", type="primary"):
        if choix_prospect_existant != options_prospects[0]:
            cible_texte = choix_prospect_existant
        elif cible_manuelle.strip():
            cible_texte = cible_manuelle.strip()
        else:
            cible_texte = f"un professionnel local ({profil_client})"

        offre_finale = f"{produit_appel} ({produit_precision.strip()})" if produit_precision.strip() else produit_appel

        prompt_appel = f"""Tu es un coach commercial spécialisé dans la vente terrain pour une imprimerie et atelier de signalétique.
Prépare une fiche d'appel téléphonique ultra-concrète, naturelle et persuasive (zéro ton robotique de centre d'appel).

PARAMÈTRES DE L'APPEL :
- Produit mis en avant : {offre_finale}
- Profil du prospect : {profil_client}
- Entreprise / lieu ciblé : {cible_texte}
- Objectif de l'appel : {objectif_appel}
- Atouts de notre imprimerie : {appel_atouts}
- Objections habituelles à préparer : {appel_objections}

CONSIGNES DE RÉDACTION :
1. `accroche_15_secondes` : Une phrase d'entrée polie, locale, directe (qui annonce tout de suite qu'on est un imprimeur voisin et pourquoi on appelle).
2. `questions_decouverte` : Exactement 3 questions courtes et ouvertes pour faire parler le client sur ses besoins actuels liés à {produit_appel}.
3. `argumentaire_produit` : Un argumentaire court (4 à 5 lignes max) axé sur les bénéfices concrets pour le client (visibilité, qualité du rendu, gain de clients, proximité).
4. `proposition_rdv` : Une phrase simple pour conclure et obtenir l'accord ({objectif_appel}).
5. `objections` : Traite 5 objections réalistes (en incluant celles de la liste '{appel_objections}' + 1 objection spécifique à '{produit_appel}'). Pour chaque objection, donne une réponse courte, calme, empathique et qui relance la conversation sans être agressif."""

        texte_script_json, erreur_appel = appeler_gemini_patient(
            prompt_appel,
            schema=ScriptAppelComplet,
            temperature=0.85
        )

        if not texte_script_json:
            st.error(f"❌ L'IA n'a pas pu générer le script. Détail : {erreur_appel}")
        else:
            try:
                script = ScriptAppelComplet.model_validate_json(texte_script_json)
                st.success(f"✅ Fiche d'appel prête pour : {offre_finale}")

                col_sc1, col_sc2 = st.columns(2)
                with col_sc1:
                    st.subheader("1️⃣ Accroche (15 premières secondes)")
                    st.info(script.accroche_15_secondes)

                    st.subheader("2️⃣ Questions à poser au client")
                    for idx_q, q in enumerate(script.questions_decouverte, start=1):
                        st.markdown(f"**{idx_q}.** {q}")

                with col_sc2:
                    st.subheader("3️⃣ Argumentaire produit")
                    st.write(script.argumentaire_produit)

                    st.subheader("4️⃣ Conclure et obtenir le rendez-vous")
                    st.success(script.proposition_rdv)

                st.divider()
                st.subheader("🛡️ Réponses prêtes aux objections du client")
                for obj in script.objections:
                    with st.expander(f"❓ « {obj.objection_client} »", expanded=True):
                        st.write(obj.reponse_conseillee)

                # Version texte brut complète pour copier-coller ou imprimer
                lignes_export = [
                    f"FICHE D'APPEL — {offre_finale.upper()}",
                    f"Cible : {cible_texte}",
                    "=" * 50,
                    "\n1. ACCROCHE (15 SECONDES) :",
                    script.accroche_15_secondes,
                    "\n2. QUESTIONS DE DÉCOUVERTE :",
                    *[f"- {q}" for q in script.questions_decouverte],
                    "\n3. ARGUMENTAIRE PRODUIT :",
                    script.argumentaire_produit,
                    "\n4. CONCLUSION / PROPOSITION :",
                    script.proposition_rdv,
                    "\n5. RÉPONSES AUX OBJECTIONS :",
                    *[f"\n* Objection : « {o.objection_client} »\n  Réponse : {o.reponse_conseillee}" for o in script.objections]
                ]
                texte_complet_fiche = "\n".join(lignes_export)
                st.text_area("📋 Fiche complète prête à copier ou imprimer :", value=texte_complet_fiche, height=260)

            except Exception as e:
                st.error(f"Erreur de lecture de la réponse IA : {e}")
