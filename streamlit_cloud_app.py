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

# Configuration des tokens de vote par utilisateur (réduits)
TOKENS_CONFIG = {
    "votes_5": 3,  # 2 votes à 5/5
    "votes_4": 5,  # 4 votes à 4/5  
    "votes_3": 8, # 8 votes à 3/5
    "votes_2": 10, # 10 votes à 2/5
    "votes_1": 10  # 10 votes à 1/5
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

# (Ancien) chargement/écriture Firebase globaux supprimés au profit d'opérations granulaires

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

# ---- Utilitaires clés Firebase et opérations granulaires ----
def sanitize_key(key: str) -> str:
    """Sanitize a string to be a valid Firebase RTDB key by replacing forbidden characters.
    Forbidden: '.', '#', '$', '[', ']', '/', '\\'"""
    if not isinstance(key, str):
        key = str(key)
    forbidden = ['.', '#', '$', '[', ']', '/', '\\']
    for ch in forbidden:
        key = key.replace(ch, '_')
    return key.strip()

def task_key_from_task(task: dict) -> str:
    """Get a stable Firebase key for a task using its id if present, else its name, sanitized."""
    base = task.get('id') or task.get('name') or 'unknown_task'
    return sanitize_key(base)

def ensure_user_record(firebase_ref, user_id: str, user_name: str):
    """Ensure a user record with tokens exists in Firebase. Do nothing in local mode."""
    try:
        if firebase_ref is None:
            return
        user_ref = firebase_ref.child('users').child(user_id)
        data = user_ref.get()
        if not data:
            user_ref.set({
                'name': user_name,
                'tokens': TOKENS_CONFIG.copy(),
                'created_at': datetime.now().isoformat()
            })
        else:
            # Keep name up to date
            if data.get('name') != user_name:
                user_ref.child('name').set(user_name)
    except Exception as e:
        st.warning(f"Impossible de vérifier/initialiser l'utilisateur dans le cloud: {e}")

def decrement_token(firebase_ref, user_id: str, vote_type: str) -> bool:
    """Decrement a user's token counter in Firebase safely. Returns True if decremented."""
    try:
        if firebase_ref is None:
            return True  # local mode handled elsewhere
        tok_ref = firebase_ref.child('users').child(user_id).child('tokens').child(vote_type)

        # Transaction-like decrement
        def _txn(cur):
            try:
                val = int(cur) if cur is not None else 0
            except Exception:
                val = 0
            if val > 0:
                return val - 1
            return val

        new_val = tok_ref.transaction(_txn)
        # If token was 0, it remains 0 -> not decremented
        try:
            return int(new_val) >= 0 and int(new_val) != int((tok_ref.get() or 0) + 1)
        except Exception:
            return False
    except Exception:
        return False

def increment_token(firebase_ref, user_id: str, vote_type: str) -> bool:
    """Increment a user's token counter in Firebase safely."""
    try:
        if firebase_ref is None:
            return True  # local mode
        tok_ref = firebase_ref.child('users').child(user_id).child('tokens').child(vote_type)

        def _txn(cur):
            try:
                val = int(cur) if cur is not None else 0
            except Exception:
                val = 0
            # Ne pas incrémenter au-delà du maximum défini
            max_val = TOKENS_CONFIG.get(vote_type, 0)
            if val < max_val:
                return val + 1
            return val

        tok_ref.transaction(_txn)
        return True
    except Exception:
        return False

def record_vote(firebase_ref, task_key: str, user_id: str, user_name: str, vote_value: int, previous_vote: dict = None) -> bool:
    """Record a vote, potentially removing a previous one in a robust way."""
    try:
        if firebase_ref is None:
            return False
        
        user_votes_ref = firebase_ref.child('votes').child(task_key).child(user_id)

        # Si un vote précédent existe, le supprimer de manière robuste
        if previous_vote:
            # Récupérer tous les votes de l'utilisateur pour cette tâche pour trouver la clé à supprimer
            existing_votes_snapshot = user_votes_ref.get()
            
            # La snapshot peut être un dictionnaire de votes {push_id: vote_obj}
            if isinstance(existing_votes_snapshot, dict):
                # Prendre la première clé de vote trouvée (il ne devrait y en avoir qu'une)
                vote_id_to_delete = next(iter(existing_votes_snapshot), None)
                
                if vote_id_to_delete:
                    # Préparer la suppression atomique
                    updates = {
                        f'votes/{task_key}/{user_id}/{vote_id_to_delete}': None
                    }
                    firebase_ref.update(updates)

        # Pousser le nouveau vote
        vote_obj = {
            'score': vote_value,
            'timestamp': datetime.now().isoformat(),
            'user_name': user_name
        }
        user_votes_ref.push(vote_obj)
        
        # Mettre à jour le timestamp global
        firebase_ref.child('last_updated').set(datetime.now().isoformat())
        return True
    except Exception as e:
        st.error(f"Erreur d'enregistrement du vote (cloud): {e}")
        return False

def add_additional_task(firebase_ref, task: dict) -> bool:
    """Add a new task in Firebase under additional_tasks/{id} and update last_updated."""
    try:
        if firebase_ref is None:
            return False
        tid = task.get('id') or str(uuid.uuid4())
        firebase_ref.child('additional_tasks').child(sanitize_key(tid)).set(task)
        firebase_ref.child('last_updated').set(datetime.now().isoformat())
        return True
    except Exception as e:
        st.error(f"Erreur d'ajout de tâche (cloud): {e}")
        return False

def _flatten_user_votes(user_votes) -> list:
    """Return a list of vote objects from either a list or a dict of pushIds, including the vote_id."""
    if isinstance(user_votes, list):
        # Pour les données legacy qui n'ont pas de vote_id, on ne peut rien faire
        return user_votes
    if isinstance(user_votes, dict):
        # Ajoute la clé du vote (pushId) comme 'vote_id' dans l'objet
        return [{**v, 'vote_id': k} for k, v in user_votes.items() if isinstance(v, dict)]
    return []

def collect_votes_for_task(votes_store: dict, task: dict) -> list:
    """Collect all vote objects for a given task across possible keys (id-based, sanitized name, raw name)."""
    keys = set()
    try:
        keys.add(task_key_from_task(task))
    except Exception:
        pass
    try:
        if 'name' in task:
            keys.add(sanitize_key(task['name']))
            keys.add(task['name'])
    except Exception:
        pass
    all_votes = []
    for k in keys:
        if k and k in votes_store:
            for uv in votes_store[k].values():
                all_votes.extend(_flatten_user_votes(uv))
    return all_votes

def collect_user_votes_for_task(votes_store: dict, task: dict, user_id: str) -> list:
    """Collect votes for a given task filtered by a specific user_id across possible keys."""
    keys = set()
    try:
        keys.add(task_key_from_task(task))
    except Exception:
        pass
    try:
        if 'name' in task:
            keys.add(sanitize_key(task['name']))
            keys.add(task['name'])
    except Exception:
        pass
    all_votes = []
    for k in keys:
        if k and k in votes_store:
            user_votes = votes_store[k].get(user_id)
            if user_votes:
                all_votes.extend(_flatten_user_votes(user_votes))
    return all_votes

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
        
        votes = data.get('votes', {})  # votes par task_key -> user_id -> pushId -> vote
        users = data.get('users', {})
        # additional_tasks peut être dict (par id) ou liste
        additional_tasks_raw = data.get('additional_tasks', {})
        if isinstance(additional_tasks_raw, dict):
            additional_tasks = list(additional_tasks_raw.values())
        else:
            additional_tasks = additional_tasks_raw or []
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
            # Utiliser la description du CSV si elle existe, sinon fallback
            description = row.get('Description', "Description non fournie dans le CSV.")
            
            all_tasks.append({
                'name': row['Nouveau_Nom'],
                'description': description,
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

    # Verrou anti double-clic (générique)
    LOCK_WINDOW_SEC = 0.5
    if 'click_locks' not in st.session_state:
        st.session_state.click_locks = {}

    def is_locked(lock_key: str) -> bool:
        t = st.session_state.click_locks.get(lock_key)
        return bool(t and (time.time() - t) < LOCK_WINDOW_SEC)

    def lock_now(lock_key: str):
        st.session_state.click_locks[lock_key] = time.time()

    # Nettoyage des verrous expirés
    try:
        expired_keys = [k for k, t0 in st.session_state.click_locks.items() if (time.time() - t0) >= LOCK_WINDOW_SEC]
        for k in expired_keys:
            del st.session_state.click_locks[k]
    except Exception:
        pass
    
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
        live_mode = st.checkbox("Auto-rafraîchissement (beta)", value=False, help="Active le rafraîchissement automatique toutes les 5s (peut perturber les formulaires)")
    
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
        
        # Sauvegarder le nom dans session_state et forcer la mise à jour
        if user_name and user_name != st.session_state.user_name:
            st.session_state.user_name = user_name
            st.rerun()
        
        # Bouton de connexion rapide
        if not st.session_state.user_name and user_name:
            if st.button("🔑 Se connecter", use_container_width=True):
                st.session_state.user_name = user_name
                st.rerun()
        
        # Bouton de déconnexion
        if st.session_state.user_name:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.success(f"✅ Connecté : {st.session_state.user_name}")
            with col2:
                if st.button("🚪 Déco"):
                    st.session_state.user_name = ""
                    st.rerun()
        
        # Section de vote - visible seulement si connecté
        if st.session_state.user_name:
            user_name = st.session_state.user_name  # Utiliser le nom de session_state
            user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, user_name))
            # S'assurer que l'utilisateur existe dans le cloud et le cache
            try:
                ensure_user_record(firebase_ref, user_id, user_name)
            except Exception:
                pass
            user_tokens = get_user_tokens(user_id, users)
            users[user_id]["name"] = user_name
            
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
            existing_votes = collect_user_votes_for_task(votes, current_task, user_id)
            
            if existing_votes:
                st.info(f"Vous avez déjà voté : {[v['score'] for v in existing_votes]}")
            
            # Boutons de vote
            # Boutons de vote
            st.subheader("Voter / Corriger :")
            vote_cols = st.columns(5)
            
            # Trier les types de vote pour un affichage cohérent (1 à 5 étoiles)
            sorted_vote_types = sorted(user_tokens.keys(), key=lambda x: int(x.split('_')[1]))

            for i, vote_type in enumerate(sorted_vote_types):
                remaining = user_tokens[vote_type]
                vote_value = int(vote_type.split('_')[1])
                
                with vote_cols[i]:
                    stars = "⭐" * vote_value
                    task_key = task_key_from_task(current_task)
                    btn_key = f"vote_{vote_value}_{task_key}"
                    btn_lock_key = f"vote:{user_id}:{task_key}:{vote_value}"
                    
                    # On peut voter pour corriger même si le token est à 0, si un vote existe déjà
                    can_vote = remaining > 0 or any(v['score'] != vote_value for v in existing_votes)
                    
                    # Le bouton est désactivé si on ne peut pas voter ou si le verrou anti-clic est actif
                    disabled = not can_vote or is_locked(btn_lock_key)

                    if st.button(f"{stars}\n({remaining})", key=btn_key, use_container_width=True, disabled=disabled):
                        lock_now(btn_lock_key)
                        
                        previous_vote_obj = existing_votes[0] if existing_votes else None
                        
                        # Si le vote est identique, ne rien faire
                        if previous_vote_obj and previous_vote_obj['score'] == vote_value:
                            st.toast("Vous avez déjà voté cette valeur.")
                            st.rerun()

                        # --- Logique de correction de vote ---
                        if firebase_ref is not None:
                            # 1. Rembourser l'ancien token si un vote existait
                            if previous_vote_obj:
                                old_vote_type = f"votes_{previous_vote_obj['score']}"
                                increment_token(firebase_ref, user_id, old_vote_type)
                                users[user_id]["tokens"][old_vote_type] += 1

                            # 2. Décrémenter le nouveau token
                            ok = decrement_token(firebase_ref, user_id, vote_type)
                            if not ok:
                                st.error("Plus de tokens disponibles pour ce type de vote.")
                                # Annuler le remboursement si le nouveau vote échoue
                                if previous_vote_obj:
                                    decrement_token(firebase_ref, user_id, f"votes_{previous_vote_obj['score']}")
                                st.rerun()
                            
                            # 3. Enregistrer le vote
                            if record_vote(firebase_ref, task_key, user_id, user_name, vote_value, previous_vote=previous_vote_obj):
                                # Recharger complètement les données pour garantir la cohérence
                                votes, users, additional_tasks, last_updated = load_live_data(firebase_ref)
                                st.session_state.votes_data = votes
                                st.session_state.users_data = users
                                st.session_state.additional_tasks_data = additional_tasks
                                st.session_state.last_data_timestamp = last_updated
                                st.success(f"Vote mis à jour : {vote_value}/5")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error("Erreur lors de la mise à jour du vote.")
                        
                        else: # Mode local
                            # Logique locale similaire
                            if previous_vote_obj:
                                old_vote_type = f"votes_{previous_vote_obj['score']}"
                                users[user_id]["tokens"][old_vote_type] += 1
                                # Supprimer l'ancien vote localement
                                name_key = sanitize_key(current_task['name'])
                                if name_key in votes and user_id in votes[name_key]:
                                    # Trouver et supprimer le vote
                                    current_user_votes = _flatten_user_votes(votes[name_key][user_id])
                                    # Garder tous les votes sauf celui qui est corrigé
                                    votes[name_key][user_id] = [v for v in current_user_votes if v.get('vote_id') != previous_vote_obj.get('vote_id')]

                            # Décrémenter et ajouter le nouveau
                            if users[user_id]["tokens"][vote_type] > 0:
                                users[user_id]["tokens"][vote_type] -= 1
                                name_key = sanitize_key(current_task['name'])
                                if name_key not in votes: votes[name_key] = {}
                                
                                new_vote = {"score": vote_value, "timestamp": datetime.now().isoformat(), "user_name": user_name}
                                
                                # S'assurer que c'est une liste pour la mise à jour locale
                                if user_id not in votes[name_key] or not isinstance(votes[name_key][user_id], list):
                                    votes[name_key][user_id] = []

                                votes[name_key][user_id].append(new_vote)

                                if save_data_local(votes, users, additional_tasks):
                                    st.session_state.votes_data = votes
                                    st.session_state.users_data = users
                                    st.success(f"Vote mis à jour : {vote_value}/5 (local)")
                                    time.sleep(0.3)
                                    st.rerun()
                                else:
                                    st.error("Erreur lors de la sauvegarde locale du vote.")
                            else:
                                st.warning("Plus de jetons de ce type en mode local.")
                    else:
                        st.button(f"{stars}\n(0)", disabled=True, key=f"vote_disabled_{vote_value}_{task_key}", use_container_width=True)
        
        else:
            # Message d'invitation à se connecter
            st.info("👆 Entrez votre nom ci-dessus pour commencer à voter")
        
        st.markdown("---")
        
        # Section pour ajouter une nouvelle tâche - visible seulement si connecté
        if st.session_state.user_name:
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
                
                form_lock_key = f"new_task_form:{st.session_state.user_name or 'anon'}"
                submitted = st.form_submit_button("🚀 Proposer la tâche", disabled=is_locked(form_lock_key))
                
                if submitted and new_task_name and new_task_desc and st.session_state.user_name:
                    lock_now(form_lock_key)
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
                    
                    # Sauvegarder dans le cloud ou local
                    if firebase_ref is not None:
                        if add_additional_task(firebase_ref, new_task):
                            additional_tasks.append(new_task)
                            st.session_state.additional_tasks_data = additional_tasks
                            st.success(f"Nouvelle tâche proposée : '{new_task_name}'")
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.error("Erreur lors de l'ajout de la tâche (cloud)")
                    else:
                        additional_tasks.append(new_task)
                        if save_data_local(votes, users, additional_tasks):
                            st.session_state.additional_tasks_data = additional_tasks
                            st.success(f"Nouvelle tâche proposée : '{new_task_name}' (local)")
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.error("Erreur lors de l'ajout de la tâche (local)")
        else:
            # Message pour les utilisateurs non connectés
            st.info("👆 Connectez-vous pour proposer de nouvelles tâches")
    
    # Zone principale - Visualisation
    main_col1, main_col2 = st.columns([2, 1])
    
    with main_col1:
        st.subheader("🏆 Classement des Tâches (par total d'étoiles)")

        # Calculer le score total (somme des étoiles) pour chaque tâche
        task_scores = []
        for task in all_tasks:
            task_votes = collect_votes_for_task(votes, task)
            total_stars = sum(v.get("score", 0) for v in task_votes if isinstance(v, dict))
            num_votes = len(task_votes)
            avg_score = total_stars / num_votes if num_votes > 0 else 0
            
            task_scores.append({
                'name': task['name'],
                'total_stars': total_stars,
                'num_votes': num_votes,
                'avg_score': avg_score,
                'source': task['source']
            })

        # Trier par total d'étoiles, puis par nombre de votes
        df_ranked = pd.DataFrame(task_scores)
        df_ranked = df_ranked.sort_values(by=['total_stars', 'num_votes'], ascending=False).reset_index()

        # Afficher le classement
        for index, row in df_ranked.iterrows():
            emoji = "🆕" if row['source'] == 'proposed' else "📋"
            st.markdown(f"### {index + 1}. {emoji} {row['name']}")
            
            cols = st.columns(3)
            cols[0].metric("Total d'étoiles", f"⭐ {row['total_stars']}")
            cols[1].metric("Nombre de votes", f"🗳️ {row['num_votes']}")
            cols[2].metric("Score moyen", f"{row['avg_score']:.1f}/5")
            
            # Barre de progression visuelle
            if df_ranked['total_stars'].max() > 0:
                progress_value = row['total_stars'] / df_ranked['total_stars'].max()
                st.progress(progress_value)
            
            st.markdown("---")

    with main_col2:
        st.subheader("📊 Statistiques de Vote")
        
        # Statistiques générales
        # Total votes across both legacy (lists) and new (dict pushIds) representations
        total_votes = 0
        for task_map in votes.values():
            for uv in task_map.values():
                total_votes += len(_flatten_user_votes(uv))
        st.metric("Total des votes", total_votes)
        st.metric("Participants", len(users))
        st.metric("Nouvelles tâches proposées", len(additional_tasks))
        
        # Affichage de la tâche actuelle dans le vote collectif
        if st.session_state.user_name and 'current_task_index' in st.session_state:
            current_task = all_tasks[st.session_state.current_task_index]
            st.info(f"**Vote collectif :**\nTâche {st.session_state.current_task_index + 1}/{len(all_tasks)}\n*{current_task['name']}*")
        
        # Top des tâches (maintenu pour info rapide)
        if votes:
            st.subheader("🏆 Top 5 (par nb de votes)")
            task_vote_counts = {}
            # Repasser par all_tasks pour avoir un mapping stable nom<->clé
            for task in all_tasks:
                tv = collect_votes_for_task(votes, task)
                count = len(tv)
                if count > 0:
                    avg_score = sum(v.get("score", 0) for v in tv if isinstance(v, dict)) / count
                    task_vote_counts[task['name']] = {"count": count, "avg_score": avg_score}
            
            # Trier par nombre de votes puis par score moyen
            sorted_tasks = sorted(task_vote_counts.items(), 
                                key=lambda x: (x[1]["count"], x[1]["avg_score"]), 
                                reverse=True)
            
            for i, (task_name, stats) in enumerate(sorted_tasks[:5]):
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
        
        # Section Admin
        st.markdown("---")
        st.subheader("👑 Section Admin")
        
        admin_pwd = st.text_input("Mot de passe admin :", type="password")
        
        if admin_pwd == st.secrets.get("ADMIN_PASSWORD", "admin"):
            st.success("Accès admin autorisé")
            
            st.subheader("Réinitialiser les votes d'un participant")
            
            user_list = {uid: u.get('name', f"ID: {uid}") for uid, u in users.items()}
            user_to_reset_id = st.selectbox("Choisir un utilisateur :", options=list(user_list.keys()), format_func=lambda x: user_list[x])
            
            if st.button(f"Réinitialiser TOUS les votes de {user_list.get(user_to_reset_id)}", type="primary"):
                if firebase_ref is not None:
                    # Opération atomique pour supprimer tous les votes et réinitialiser les tokens
                    updates = {}
                    
                    # 1. Préparer la suppression de tous les votes de l'utilisateur
                    all_votes_ref = firebase_ref.child('votes')
                    all_task_votes = all_votes_ref.get()
                    if all_task_votes:
                        for task_key, user_votes in all_task_votes.items():
                            if user_to_reset_id in user_votes:
                                # Ajouter le chemin de suppression à la mise à jour
                                updates[f'votes/{task_key}/{user_to_reset_id}'] = None
                    
                    # 2. Préparer la réinitialisation des tokens
                    updates[f'users/{user_to_reset_id}/tokens'] = TOKENS_CONFIG.copy()
                    
                    try:
                        # 3. Exécuter la mise à jour atomique
                        firebase_ref.update(updates)
                        
                        st.success(f"Votes de {user_list.get(user_to_reset_id)} réinitialisés avec succès.")
                        
                        # 4. Forcer le rechargement complet de l'application
                        st.session_state.clear()
                        time.sleep(1)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Une erreur est survenue lors de la réinitialisation : {e}")

                else:
                    # Mode local
                    for task_key in list(votes.keys()):
                        if user_to_reset_id in votes.get(task_key, {}):
                            del votes[task_key][user_to_reset_id]
                    
                    if user_to_reset_id in users:
                        users[user_to_reset_id]['tokens'] = TOKENS_CONFIG.copy()
                    
                    save_data_local(votes, users, additional_tasks)
                    st.success(f"Votes de {user_list.get(user_to_reset_id)} réinitialisés (local).")
                    st.session_state.clear()
                    time.sleep(1)
                    st.rerun()

        # Indicateur de dernière mise à jour
        st.markdown("---")
        st.caption(f"Dernière actualisation: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
