import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime
import uuid
import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Configuration de la page
st.set_page_config(
    page_title="SPRING - Système de Vote Collaboratif",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Descriptions réelles des tâches
DESCRIPTIONS_REELLES = {
    "Caractéristique hydraulique de la T8": "AU LABO : caractérisation Delta P vs débit, gap voir production (fréquence, tension), densité gaz. Permet de dérisquer le pilotage en pression de SPRING. Comprendre l'impact du GAP et de la présence plasma, du gaz de plasmalyse (micro déflagration CO2). Monter un PT à la place du TT, faire des calculs de perte de charge sur les conduites 6 mm.",
    "Bouclage bilan matière": "Acquisitions de méthodes nécessaires pour SPRING (bras mort / formules, outils de mesure - débitmètre basse pression). - Trouver et installer un débit mètre volumique - Automatiser le calcul massique avec le MADUR - Mettre des pesons sur le four remontés dans l'automate. - Interpréter les résultats : bouclage Carbone et bouclage Hydrogène. Rendements avec et sans plasmalyse. Accumulation de goudrons qui sont ensuite craqués. Estimation du volume de carbone produit. Efficacité des mécanismes de régénération type BOUDOUARD",
    "Approche empirique des adsorptions H2 dans les réfractaires": "Comprendre le temps nécessaire pour désorber l'hydrogène du four.",
    "Effet Lensing sur la T8": "Comprendre les conditions d'apparition d'un plasma focalisé (défaut de parallélisme des électrodes, modification du gap, apparition de pont de carbone, défaut de concentricité des électrodes, encrassement). Enjeux : - Ablation des électrodes, - Taux de conversion - Mixing - Faux positif sur la détection pont de carbone. Tâche de fond OPS. Besoin de cathodes nickel.",
    "Comprendre l'érosion des électrodes vs l'écoulement": "On est passé d'une cathode concave à une cathode convexe avec la T8. Est-ce lié au refroidissement central de la T8? Intéressant pour SPRING : - Augmenter le débit? - Diminuer la section du gaz? - Percer la cathode? - Électrode en tiges de cuivre pour avoir une érosion plus rapide que le tungsten? - Trouver les paramètres plasma. - Paramètre du gaz de plasmalyse (CO2) - Cathode gros diamètre pour éviter les pbs de concentricité - Cathode trouée - Cathode massique en carbone",
    "Fiabilité PDR et MTBF": "Enregistreur d'évènements. Détecter les points faibles de la T8 pour SPRING. Modif cockpit : suivi des pièces d'usure + le calcul et le dashboarding des heures et paramètres de production. Upgrade du labéliseur d'évènement : labéliseur de maintenance. Ronde intermédiaire (test de la cathode ajustable)",
    "Mesure UI : impact régulation plasma sur le couple T8 GF1R0": "Temps de mise en œuvre. Important avec beaucoup d'interface. APPRENTISSAGE SPRING",
    "Régénération mécanique des ponts de carbones": "Le CO2 ne sera peut-être pas possible sur SPRING (impacte la qualité carbone). Il faudra une solution mécanique. Complexité importante et potentiellement changement de l'AF.",
    "Mobilité carbone vs température de peau vs surface": "Thermoforèse - LABO - utiliser le préchauffeur et le générateur de flux sale pour faire des tests. Tester le teflon.",
    "Régénération pont de carbone H2": "Pour le labo ? Si pas de pont de carbone alors CH5 ...",
    "Relation Process / Qualité carbone / apparition PC / érosion électrode / température": "- Finir le plan de test Température - T240 et T241 à 1200 et 1300°C - Tester d'autres paramètres : pression à 300mbar dans le Réacteur ou le convertisseur (à quel point est ce défavorable?) Fréquence gap tension - Contrôle du temps de séjour dans le four (Mouffle) : Modélisation du four pour le gas mixing, Gaz traceur pour obtenir les temps de séjour observés (distrib de temps de séjour), Possibilité de modification",
    "Que se passe-t-il dans le haut de la torche?": "Peut-on noyer le T8 dans le réfractaire ou faut-il lui laisser de la liberté pour respirer? Qu'est-ce qui se passe à l'horizontal ou en diagonale? - Compo gaz? -> décantation hydrogène vs CH-CHOC - Impact du 'vide' sur la formation des PC (combler avec de la cera blanket, monter une vieille céramique ...) - LABO - test en horizontal.",
    "MONITORING système/zone dans cockpit": "Développer des vues dans le temps par système (filtration / convertisseur / plasmalyse / analyse) qui remontent les informations clés pour MONITORER les équipements (ANALYSER et ANTICIPER les pannes): - Des évènements de type sécurité - Des états (nombre d'heures de fonctionnement par sous ensemble) - Des observations utilisateur (pont de carbone, changement de pièces etc...) But c'est de monter en compétence de pilotage pour SPRING (infos clés à remonter hors de SCADA). Si suivi en temps réel exemple : vue par zone des alarmes. Les consignations",
    "Tester les électrodes en graphite": "Pré requis 11 et surtout 10. Stabilité des GAP, stabilité en régénération CO2 etc... Enjeux : électrodes de spring et carbone conducteur (impureté métalliques)",
    "Optimisation SEO de la T8": "Prépare les méthodes de caractérisation des torches de SPRING + paramétrage des systèmes pendant la chauffe et la production. Trouver une méthode expérimentale pour obtenir la SEO d'une torche T8, l'implémenter dans CH5 et dans cockpit (vue système). Tester des paramètres à notre disposition : - Gap - Débit/ pression - Compo gaz (N2, H2, CH4, ....) - Pousser les générateurs à 100KHz",
    "Tester la bande de température de Victor": "????",
    "Nouveaux systèmes de filtration nanoparticule": "Des cyclones haute vitesse. Filtration électrostatique. Refroidissement ou pas par l'échangeur. Banc de test PAL. pot à carbone. En delta par rapport au BF310 en rendement, en analyse granul, en perte de charge",
    "Battre des records de durée": "Communication. Savoir comment ça se comporte en fonctionnement continu -> truc de fin de campagne (car il faut qu'Eric soit 100% opérationnel + helpers)",
    "Caractériser impuretés dans le gaz a différentes étapes process": "- Savoir prélever du gaz sale, chaud-froid, gérer l'ATEX et la géométrie des points de prélèvements... - Savoir analyser les particules (distribution, HAP etc...) - Savoir trouver de struc inattendu (poussière de réfractaire, oxyde métalliques, soufre etc..) - Gestion des échantillons avec des labos externes etc... Mise au point des méthodes d'échantillonnage et d'analyse pour SPRING.",
    "Miscibilité CH4 – H2": "Selon les écoulements et la température ???",
    "Tester les impuretés du feedstock": "Vapeur d'eau, éthane, mercaptans, CO2, azote, H2 - Impact sur la durabilité des électrodes - Impact sur la détection pont de carbone - Impact sur la régulation de manière générale (UGF etc...) - Structure du carbone de plasmalyse (graphène?)",
    "Étanchéification presse étoupe des résistances du convertisseur": "Aide pour le bilan matière - Capot pressurisé en azote à 20mbar mini et presse étoupe pour les câbles (ATEX zone 1 dans la boîte)",
    "Combustion des gaz de CH5": "Savoir designer, implanter et opérer une torchère. Designer et opérer une torche pour CH5 - Engineering - Impacts sécurité (plan de prévention etc...) - Améliorer les performances environnementales de CH5 - Tester le résidu carbone (pluging brûleur)",
    "Tester des précurseurs dans le feedstock": "- Précurseurs ferreux pour des nanotubes - KOH pour modifier la structure des agrégats. - Savoir injecter dans le feedstock - Monitorer les impacts durabilité / fiabilité etc.... - Cf 23 mais avec des liquides ou des solides plutôt que des gaz.",
    "Breveter la T8": "Cf 21",
    "Mélange nanotubes de carbone et CB du four": "Test pour le carbone conducteur.",
    "Post-traitement du carbone": "- Élimination des HAP - Broyage - Fonctionnalisation en extrudeuse réactive - Granulation - Séchage - Élastomères prêt à l'emploi - Fonctionnalisation carbone in situ : injection haute température d'adjuvant via TT30X",
    "Tests de nouveaux générateurs / pilote carbone": "Faisabilité à regarder en fonction des générateurs concernés - Mesures de sécurité - Modification AF - Disponibilité torche etc... - Pré tests en labo.",
    "Séparation / purification du dihydrogène": "Trouver une membrane basse pression?",
    "Séparer l'acétylène en sortie de plasma": "Semble excessivement difficile (carbone etc...)",
    "Nettoyage du convertisseur vapeur/CO2": "Injection de vapeur en amont du four. Intérêt pour SPRING. Risque de choc thermique aux résistances et réfractaire. Impact sur le carbone etc...",
    "Injection directe de plasma dans le four": "Attention aux chicanes -> utiliser un TT. Mise en place d'une cellule plasma en extérieur (électricité, du gaz)."
}

# Configuration des tokens de vote par utilisateur
TOKENS_CONFIG = {
    "votes_5": 3,  # 3 votes à 5/5
    "votes_4": 5,  # 5 votes à 4/5  
    "votes_3": 10, # 10 votes à 3/5
    "votes_2": 15, # 15 votes à 2/5
    "votes_1": 20  # 20 votes à 1/5
}

@st.cache_resource
def init_firebase():
    """Initialise Firebase avec les credentials du secret Streamlit"""
    try:
        if not firebase_admin._apps:
            # Récupérer les credentials depuis les secrets Streamlit
            firebase_credentials = st.secrets["firebase"]
            
            # Créer un dictionnaire de credentials
            cred_dict = {
                "type": firebase_credentials["type"],
                "project_id": firebase_credentials["project_id"],
                "private_key_id": firebase_credentials["private_key_id"],
                "private_key": firebase_credentials["private_key"].replace('\\n', '\n'),
                "client_email": firebase_credentials["client_email"],
                "client_id": firebase_credentials["client_id"],
                "auth_uri": firebase_credentials["auth_uri"],
                "token_uri": firebase_credentials["token_uri"],
                "auth_provider_x509_cert_url": firebase_credentials["auth_provider_x509_cert_url"],
                "client_x509_cert_url": firebase_credentials["client_x509_cert_url"]
            }
            
            # Initialiser Firebase
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': firebase_credentials["database_url"]
            })
        
        return db.reference()
    except Exception as e:
        st.error(f"Erreur initialisation Firebase: {str(e)}")
        # Fallback vers stockage local en cas d'erreur
        return None

def load_data_firebase(firebase_ref):
    """Charge les données depuis Firebase"""
    try:
        if firebase_ref is None:
            # Fallback vers fichiers locaux
            return load_data_local()
        
        # Charger depuis Firebase
        data = firebase_ref.get() or {}
        
        votes = data.get('votes', {})
        users = data.get('users', {})
        additional_tasks = data.get('additional_tasks', [])
        
        return votes, users, additional_tasks
    except Exception as e:
        st.error(f"Erreur chargement Firebase: {str(e)}")
        return {}, {}, []

def save_data_firebase(firebase_ref, votes, users, additional_tasks):
    """Sauvegarde les données dans Firebase"""
    try:
        if firebase_ref is None:
            # Fallback vers fichiers locaux
            return save_data_local(votes, users, additional_tasks)
        
        # Sauvegarder dans Firebase
        data = {
            'votes': votes,
            'users': users,
            'additional_tasks': additional_tasks,
            'last_updated': datetime.now().isoformat()
        }
        
        firebase_ref.set(data)
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde Firebase: {str(e)}")
        return False

def load_data_local():
    """Charge les données depuis les fichiers locaux (fallback)"""
    votes = {}
    users = {}
    additional_tasks = []
    
    # Charger les votes
    if os.path.exists("votes_spring_meeting.json"):
        with open("votes_spring_meeting.json", 'r', encoding='utf-8') as f:
            votes = json.load(f)
    
    # Charger les utilisateurs
    if os.path.exists("users_spring_meeting.json"):
        with open("users_spring_meeting.json", 'r', encoding='utf-8') as f:
            users = json.load(f)
    
    # Charger les nouvelles tâches
    if os.path.exists("tasks_spring_meeting.json"):
        with open("tasks_spring_meeting.json", 'r', encoding='utf-8') as f:
            additional_tasks = json.load(f)
    
    return votes, users, additional_tasks

def save_data_local(votes, users, additional_tasks):
    """Sauvegarde locale (fallback)"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        files_data = [
            ("votes_spring_meeting.json", votes),
            ("users_spring_meeting.json", users),
            ("tasks_spring_meeting.json", additional_tasks)
        ]
        
        for filename, data in files_data:
            # Backup du fichier existant
            if os.path.exists(filename):
                backup_name = f"{filename}.backup_{timestamp}"
                os.rename(filename, backup_name)
            
            # Sauvegarder les nouvelles données
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde locale: {str(e)}")
        return False

def get_user_tokens(user_id, users):
    """Récupère les tokens restants pour un utilisateur"""
    if user_id not in users:
        users[user_id] = {
            "name": f"Utilisateur_{user_id[:8]}",
            "tokens": TOKENS_CONFIG.copy(),
            "created_at": datetime.now().isoformat()
        }
    return users[user_id]["tokens"]

def format_text_for_hover(text, line_width=90):
    """Formate le texte pour l'affichage hover avec retours à la ligne intelligents"""
    if not text or len(text) <= line_width:
        return text
    
    # Séparer par phrases d'abord
    sentences = text.replace('. ', '.|').replace('? ', '?|').replace('! ', '!|').split('|')
    formatted_lines = []
    current_line = ""
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # Si la phrase entière tient sur une ligne
        if len(current_line + sentence) <= line_width:
            current_line += sentence
        else:
            # Ajouter la ligne actuelle si elle n'est pas vide
            if current_line.strip():
                formatted_lines.append(current_line.strip())
            
            # Si la phrase est trop longue, la couper par mots
            if len(sentence) > line_width:
                words = sentence.split()
                current_line = ""
                for word in words:
                    if len(current_line + " " + word) <= line_width:
                        current_line += (" " if current_line else "") + word
                    else:
                        if current_line:
                            formatted_lines.append(current_line)
                        current_line = word
            else:
                current_line = sentence
    
    # Ajouter la dernière ligne
    if current_line.strip():
        formatted_lines.append(current_line.strip())
    
    return "<br>".join(formatted_lines)

def get_real_description(task_name):
    """Récupère la vraie description d'une tâche par correspondance exacte"""
    if task_name in DESCRIPTIONS_REELLES:
        return DESCRIPTIONS_REELLES[task_name]
    return "Description à compléter selon les critères SPRING"

@st.cache_data(ttl=300)  # Cache le CSV pendant 5 minutes (il ne change pas souvent)
def load_csv_data():
    """Charge les données du CSV"""
    try:
        df = pd.read_csv('Evaluation_Taches_SPRING - Copie.csv', 
                        sep=';', 
                        encoding='iso-8859-1')
        
        # Nettoyer les données numériques
        numeric_cols = ['Cout', 'Score_Prix', 'Score_Complexité', 'Score_Intérêt', 'Score_Total']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.').astype(float)
        
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement du CSV : {e}")
        return None

def load_live_data(firebase_ref):
    """Charge les données en temps réel sans cache"""
    try:
        if firebase_ref is None:
            return load_data_local()
        
        # Charger directement depuis Firebase sans cache
        data = firebase_ref.get() or {}
        
        votes = data.get('votes', {})
        users = data.get('users', {})
        additional_tasks = data.get('additional_tasks', [])
        last_updated = data.get('last_updated', '')
        
        return votes, users, additional_tasks, last_updated
    except Exception as e:
        st.error(f"Erreur chargement live: {str(e)}")
        return {}, {}, [], ""

def check_for_updates(firebase_ref):
    """Vérifie s'il y a des mises à jour sans recharger la page"""
    if 'last_data_timestamp' not in st.session_state:
        st.session_state.last_data_timestamp = ""
    
    try:
        if firebase_ref is not None:
            # Vérifier seulement le timestamp de dernière mise à jour
            last_updated = firebase_ref.child('last_updated').get()
            
            if last_updated and last_updated != st.session_state.last_data_timestamp:
                st.session_state.last_data_timestamp = last_updated
                return True
        
        return False
    except Exception:
        return False

def get_all_tasks(df, additional_tasks):
    """Combine les tâches du CSV et les nouvelles tâches proposées"""
    all_tasks = []
    
    # Tâches du CSV
    if df is not None:
        for _, row in df.iterrows():
            all_tasks.append({
                'name': row['Nouveau_Nom'],
                'description': get_real_description(row['Nouveau_Nom']),
                'cost_score': row['Score_Prix'],
                'complexity_score': row['Score_Complexité'],
                'interest_score': row['Score_Intérêt'],
                'total_score': row['Score_Total'],
                'source': 'csv',
                'id': f"csv_{row['Nouveau_Nom']}"
            })
    
    # Nouvelles tâches proposées
    for task in additional_tasks:
        all_tasks.append({
            'name': task['name'],
            'description': task['description'],
            'cost_score': float(task['cost']),
            'complexity_score': float(task['complexity']),
            'interest_score': float(task['interest']),
            'total_score': (float(task['cost']) + float(task['complexity']) + float(task['interest'])) / 3,
            'source': 'proposed',
            'proposed_by': task['proposed_by'],
            'id': task['id']
        })
    
    # Trier par nom pour avoir un ordre fixe
    all_tasks.sort(key=lambda x: x['name'].lower())
    
    return all_tasks

def main():
    st.title("🗳️ SPRING - Système de Vote Collaboratif")
    st.markdown("---")
    
    # Initialiser toutes les variables de session_state en premier
    if 'user_name' not in st.session_state:
        st.session_state.user_name = ""
    if 'current_task_index' not in st.session_state:
        st.session_state.current_task_index = 0
    if 'last_data_timestamp' not in st.session_state:
        st.session_state.last_data_timestamp = ""
    
    # Initialiser Firebase
    firebase_ref = init_firebase()
    
    # Indicateur de connexion
    if firebase_ref is not None:
        st.success("🌐 Connecté au cloud - Synchronisation temps réel active")
    else:
        st.warning("⚠️ Mode local - Les données ne seront pas synchronisées")
    
    # Initialiser les données dans session_state
    if 'votes_data' not in st.session_state:
        votes, users, additional_tasks, last_updated = load_live_data(firebase_ref)
        st.session_state.votes_data = votes
        st.session_state.users_data = users
        st.session_state.additional_tasks_data = additional_tasks
        st.session_state.last_data_timestamp = last_updated
    
    # Vérification initiale des mises à jour en arrière-plan (une seule fois par chargement)
    if firebase_ref is not None and 'initial_load_done' not in st.session_state:
        votes, users, additional_tasks, last_updated = load_live_data(firebase_ref)
        st.session_state.votes_data = votes
        st.session_state.users_data = users
        st.session_state.additional_tasks_data = additional_tasks
        st.session_state.initial_load_done = True
    
    # Utiliser les données du session_state
    votes = st.session_state.votes_data
    users = st.session_state.users_data
    additional_tasks = st.session_state.additional_tasks_data
    
    # Boutons de contrôle
    col1, col2, col3, col4 = st.columns([1, 1, 2, 2])
    with col1:
        if st.button("🔄 Actualiser"):
            # Force le rechargement des données
            votes, users, additional_tasks, last_updated = load_live_data(firebase_ref)
            st.session_state.votes_data = votes
            st.session_state.users_data = users
            st.session_state.additional_tasks_data = additional_tasks
            st.session_state.last_data_timestamp = last_updated
            st.rerun()
    
    with col2:
        live_mode = st.checkbox("🔴 Live", value=True, help="Synchronisation temps réel")
    
    # Mécanisme de polling intelligent
    if live_mode and firebase_ref is not None:
        # Utiliser un placeholder pour déclencher le polling
        placeholder = st.empty()
        
        # Vérifier s'il est temps de faire un poll
        current_time = time.time()
        if 'last_poll' not in st.session_state:
            st.session_state.last_poll = current_time
        
        if current_time - st.session_state.last_poll > 5:  # 5 secondes
            st.session_state.last_poll = current_time
            
            if check_for_updates(firebase_ref):
                # Mettre à jour les données silencieusement
                votes, users, additional_tasks, last_updated = load_live_data(firebase_ref)
                st.session_state.votes_data = votes
                st.session_state.users_data = users
                st.session_state.additional_tasks_data = additional_tasks
                
                # Notification discrète de mise à jour
                with placeholder:
                    st.success("🔄 Nouvelles données détectées", icon="🔄")
                    time.sleep(1)
                    placeholder.empty()
            
            # Programmer le prochain poll
            time.sleep(0.1)
            st.rerun()
    
    with col3:
        if st.session_state.last_data_timestamp:
            try:
                last_update_time = datetime.fromisoformat(st.session_state.last_data_timestamp.replace('Z', '+00:00'))
                st.caption(f"Dernière MAJ: {last_update_time.strftime('%H:%M:%S')}")
            except:
                st.caption("Dernière MAJ: --:--:--")
    
    with col4:
        if st.session_state.user_name:
            st.success(f"👤 {st.session_state.user_name}")
        else:
            st.info("👤 Non connecté")
    
    # Charger les données CSV (cachées plus longtemps car statiques)
    df = load_csv_data()
    
    if df is None and not additional_tasks:
        st.error("Aucune donnée disponible. Vérifiez la configuration.")
        return
    
    # Obtenir toutes les tâches (CSV + nouvelles)
    all_tasks = get_all_tasks(df, additional_tasks)
    
    # Sidebar pour le système de vote
    with st.sidebar:
        st.header("🎯 Système de Vote")
        
        # Identification utilisateur avec persistance
        user_name = st.text_input(
            "Votre nom :", 
            value=st.session_state.user_name,
            placeholder="Entrez votre nom",
            key="user_input"
        )
        
        # Sauvegarder le nom dans session_state
        if user_name:
            st.session_state.user_name = user_name
        
        # Bouton de déconnexion
        if st.session_state.user_name:
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("🚪 Déco"):
                    st.session_state.user_name = ""
                    st.rerun()
        
        if user_name:
            user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_name))
            user_tokens = get_user_tokens(user_id, users)
            users[user_id]["name"] = user_name
            
            st.success(f"Connecté : {user_name}")
            
            # Affichage des tokens restants
            st.subheader("🪙 Vos tokens restants :")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**{user_tokens['votes_5']}** votes ⭐⭐⭐⭐⭐")
                st.write(f"**{user_tokens['votes_4']}** votes ⭐⭐⭐⭐")
                st.write(f"**{user_tokens['votes_3']}** votes ⭐⭐⭐")
            with col2:
                st.write(f"**{user_tokens['votes_2']}** votes ⭐⭐")
                st.write(f"**{user_tokens['votes_1']}** votes ⭐")
            
            st.markdown("---")
            
            # Interface de vote avec ordre fixe
            st.subheader("📊 Vote Collectif - Ordre Fixe")
            
            # S'assurer que l'index est dans les limites
            if st.session_state.current_task_index >= len(all_tasks):
                st.session_state.current_task_index = 0
            
            current_task = all_tasks[st.session_state.current_task_index]
            
            # Navigation
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if st.button("⬅️ Précédent", disabled=st.session_state.current_task_index == 0):
                    st.session_state.current_task_index -= 1
                    st.rerun()
            
            with col2:
                st.write(f"**Tâche {st.session_state.current_task_index + 1}/{len(all_tasks)}**")
            
            with col3:
                if st.button("➡️ Suivant", disabled=st.session_state.current_task_index == len(all_tasks) - 1):
                    st.session_state.current_task_index += 1
                    st.rerun()
            
            # Aller directement à une tâche
            task_names = [task['name'] for task in all_tasks]
            selected_index = st.selectbox(
                "Aller à :", 
                range(len(task_names)),
                format_func=lambda x: f"{x+1}. {task_names[x]}",
                index=st.session_state.current_task_index,
                key="task_selector"
            )
            
            if selected_index != st.session_state.current_task_index:
                st.session_state.current_task_index = selected_index
                st.rerun()
            
            # Affichage de la tâche actuelle
            st.markdown("---")
            st.subheader(f"🎯 {current_task['name']}")
            
            # Badge pour les nouvelles tâches
            if current_task['source'] == 'proposed':
                st.markdown(f"🆕 **Nouvelle tâche** proposée par *{current_task['proposed_by']}*")
            
            # Description
            st.text_area("Description :", current_task['description'], height=120, disabled=True)
            
            # Scores actuels
            st.write("**Scores actuels :**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Coût", f"{current_task['cost_score']:.1f}/5")
            with col2:
                st.metric("Complexité", f"{current_task['complexity_score']:.1f}/5")
            with col3:
                st.metric("Intérêt", f"{current_task['interest_score']:.1f}/5")
            
            # Vérifier les votes existants pour cette tâche
            existing_votes = []
            if current_task['name'] in votes and user_id in votes[current_task['name']]:
                existing_votes = votes[current_task['name']][user_id]
            
            if existing_votes:
                st.info(f"Vous avez déjà voté : {[v['score'] for v in existing_votes]}")
            
            # Boutons de vote
            st.subheader("Voter :")
            vote_cols = st.columns(5)
            
            for i, (vote_type, remaining) in enumerate(user_tokens.items()):
                vote_value = int(vote_type.split('_')[1])
                
                with vote_cols[i]:
                    stars = "⭐" * vote_value
                    
                    if remaining > 0:
                        if st.button(f"{stars}\n({remaining})", key=f"vote_{vote_value}_{current_task['name']}", use_container_width=True):
                            # Enregistrer le vote
                            if current_task['name'] not in votes:
                                votes[current_task['name']] = {}
                            if user_id not in votes[current_task['name']]:
                                votes[current_task['name']][user_id] = []
                            
                            votes[current_task['name']][user_id].append({
                                "score": vote_value,
                                "timestamp": datetime.now().isoformat(),
                                "user_name": user_name
                            })
                            
                            # Décrémenter le token
                            users[user_id]["tokens"][vote_type] -= 1
                            
                            # Sauvegarder dans le cloud
                            if save_data_firebase(firebase_ref, votes, users, additional_tasks):
                                st.success(f"Vote enregistré : {vote_value}/5")
                                # Mettre à jour les données locales immédiatement
                                st.session_state.votes_data = votes
                                st.session_state.users_data = users
                                time.sleep(0.5)  # Petit délai pour laisser Firebase se synchroniser
                                st.rerun()
                            else:
                                st.error("Erreur lors de l'enregistrement du vote")
                    else:
                        st.button(f"{stars}\n(0)", disabled=True, key=f"vote_disabled_{vote_value}_{current_task['name']}", use_container_width=True)
        
        st.markdown("---")
        
        # Section pour ajouter une nouvelle tâche
        st.subheader("➕ Proposer une nouvelle tâche")
        
        with st.form("new_task_form"):
            new_task_name = st.text_input("Nom de la tâche :")
            new_task_desc = st.text_area("Description détaillée :")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                new_cost = st.slider("Coût", 1, 5, 3)
            with col2:
                new_complexity = st.slider("Complexité", 1, 5, 3)
            with col3:
                new_interest = st.slider("Intérêt", 1, 5, 3)
            
            submitted = st.form_submit_button("🚀 Proposer la tâche")
            
            if submitted and new_task_name and new_task_desc and st.session_state.user_name:
                new_task = {
                    "id": str(uuid.uuid4()),
                    "name": new_task_name,
                    "description": new_task_desc,
                    "cost": new_cost,
                    "complexity": new_complexity,
                    "interest": new_interest,
                    "proposed_by": st.session_state.user_name,
                    "timestamp": datetime.now().isoformat()
                }
                
                additional_tasks.append(new_task)
                
                # Sauvegarder dans le cloud
                if save_data_firebase(firebase_ref, votes, users, additional_tasks):
                    st.success(f"Nouvelle tâche proposée : '{new_task_name}'")
                    # Mettre à jour les données locales immédiatement
                    st.session_state.additional_tasks_data = additional_tasks
                    time.sleep(0.5)  # Petit délai pour laisser Firebase se synchroniser
                    st.rerun()
                else:
                    st.error("Erreur lors de l'ajout de la tâche")
    
    # Zone principale - Visualisation
    main_col1, main_col2 = st.columns([2, 1])
    
    with main_col1:
        st.subheader("📈 Visualisation 3D des Tâches SPRING")
        
        # Créer un DataFrame combiné pour la visualisation
        combined_data = []
        
        for task in all_tasks:
            # Calculer le score d'intérêt avec les votes
            interest_score = task['interest_score']
            if task['name'] in votes:
                all_votes = []
                for user_votes in votes[task['name']].values():
                    all_votes.extend([v["score"] for v in user_votes])
                
                if all_votes:
                    interest_score = sum(all_votes) / len(all_votes)
            
            combined_data.append({
                'Nouveau_Nom': task['name'],
                'Score_Prix': task['cost_score'],
                'Score_Complexité': task['complexity_score'],
                'Score_Intérêt': interest_score,
                'Score_Total': (task['cost_score'] + task['complexity_score'] + interest_score) / 3,
                'Source': task['source'],
                'Description': task['description'],
                'Task_ID': task.get('id', task['name'])
            })
        
        df_display = pd.DataFrame(combined_data)
        
        # Créer le graphique 3D avec distinction visuelle pour les nouvelles tâches
        fig = px.scatter_3d(
            df_display,
            x='Score_Prix',
            y='Score_Complexité', 
            z='Score_Intérêt',
            size='Score_Total',
            color='Source',
            color_discrete_map={'csv': 'blue', 'proposed': 'red'},
            hover_name='Nouveau_Nom',
            size_max=20,
            title="Évaluation 3D des Tâches SPRING (🔵 Originales | 🔴 Nouvelles)"
        )
        
        # Enrichir les informations de hover
        hover_text = []
        for index, row in df_display.iterrows():
            task_name = row['Nouveau_Nom']
            
            # Rechercher la tâche dans all_tasks par nom exact
            original_task = None
            for task in all_tasks:
                if task['name'] == task_name:
                    original_task = task
                    break
            
            # Utiliser les vraies données de la tâche
            if original_task:
                description = original_task['description']
                display_name = original_task['name']
            else:
                description = "Description non trouvée"
                display_name = task_name
            
            formatted_desc = format_text_for_hover(description)
            
            # Compter les votes
            vote_count = 0
            if task_name in votes:
                for user_votes in votes[task_name].values():
                    vote_count += len(user_votes)
            
            # Badge pour les nouvelles tâches
            source_badge = "🆕 NOUVELLE" if row['Source'] == 'proposed' else "📋 ORIGINALE"
            
            hover_info = f"""
<b>{display_name}</b><br>
<b>{source_badge}</b><br>
<br>
<b>Scores :</b><br>
• Coût : {row['Score_Prix']:.1f}/5<br>
• Complexité : {row['Score_Complexité']:.1f}/5<br>
• Intérêt : {row['Score_Intérêt']:.1f}/5<br>
• <b>Total : {row['Score_Total']:.1f}/5</b><br>
<br>
<b>Votes reçus : {vote_count}</b><br>
<br>
<b>Description :</b><br>
{formatted_desc}
<extra></extra>"""
            hover_text.append(hover_info)
        
        fig.update_traces(hovertemplate=hover_text)
        
        # Améliorer l'apparence
        fig.update_layout(
            height=600,
            scene=dict(
                xaxis_title="Coût (Prix)",
                yaxis_title="Complexité", 
                zaxis_title="Intérêt",
                bgcolor="rgba(0,0,0,0)"
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with main_col2:
        st.subheader("📊 Statistiques de Vote")
        
        # Statistiques générales
        total_votes = sum(len(task_votes) for task_votes in votes.values() for task_votes in task_votes.values())
        st.metric("Total des votes", total_votes)
        st.metric("Participants", len(users))
        st.metric("Nouvelles tâches proposées", len(additional_tasks))
        
        # Affichage de la tâche actuelle dans le vote collectif
        if st.session_state.user_name and 'current_task_index' in st.session_state:
            current_task = all_tasks[st.session_state.current_task_index]
            st.info(f"**Vote collectif :**\nTâche {st.session_state.current_task_index + 1}/{len(all_tasks)}\n*{current_task['name']}*")
        
        # Top des tâches votées
        if votes:
            st.subheader("🏆 Top des tâches")
            task_vote_counts = {}
            for task_name, task_votes in votes.items():
                count = sum(len(user_votes) for user_votes in task_votes.values())
                if count > 0:
                    avg_score = sum(vote["score"] for user_votes in task_votes.values() for vote in user_votes) / count
                    task_vote_counts[task_name] = {"count": count, "avg_score": avg_score}
            
            # Trier par nombre de votes puis par score moyen
            sorted_tasks = sorted(task_vote_counts.items(), 
                                key=lambda x: (x[1]["count"], x[1]["avg_score"]), 
                                reverse=True)
            
            for i, (task_name, stats) in enumerate(sorted_tasks[:10]):
                # Emoji pour distinguer les nouvelles tâches
                is_new = any(task['name'] == task_name and task['source'] == 'proposed' for task in all_tasks)
                emoji = "🆕" if is_new else "📋"
                
                st.write(f"**{i+1}.** {emoji} {task_name}")
                st.write(f"   📊 {stats['count']} votes - ⭐ {stats['avg_score']:.1f}/5")
        
        # Nouvelles tâches proposées
        if additional_tasks:
            st.subheader("💡 Nouvelles tâches proposées")
            for task in additional_tasks[-5:]:  # 5 dernières
                st.write(f"**{task['name']}**")
                st.write(f"   Par: {task['proposed_by']}")
                st.write(f"   💰{task['cost']} 🔧{task['complexity']} ⭐{task['interest']}")
        
        # Indicateur de dernière mise à jour
        st.markdown("---")
        st.caption(f"Dernière actualisation: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
