import json
import os
import pickle
import random
from pathlib import Path
from dotenv import load_dotenv
import string
import re
import time
import uuid
from html import unescape
from typing import Dict, Optional, Any, List, Tuple
from threading import RLock
from collections import defaultdict, deque
from datetime import datetime, timedelta
import numpy as np
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from functools import wraps
import hashlib
from functools import lru_cache

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)


# ============================================================================
# ★ CACHE DISABLED: Ensures real-time updates when you edit Q&A pairs in the UI
# ============================================================================
def get_cached_response(cache_key):
    return None


def set_cached_response(cache_key, response):
    pass


# FUZZY MATCHING IMPORTS
try:
    from difflib import SequenceMatcher
    from Levenshtein import distance as levenshtein_distance

    LEVENSHTEIN_AVAILABLE = True
except ImportError:
    LEVENSHTEIN_AVAILABLE = False

# Lazy Imports
SENTENCE_TRANSFORMERS_AVAILABLE = False
try:
    import sentence_transformers

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    pass

SKLEARN_AVAILABLE = False
try:
    import sklearn

    SKLEARN_AVAILABLE = True
except ImportError:
    pass


def _lazy_import_sklearn():
    global cosine_similarity, TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.feature_extraction.text import TfidfVectorizer


try:
    import ollama

    ollama_host = os.getenv('OLLAMA_HOST')
    if ollama_host: os.environ['OLLAMA_HOST'] = ollama_host
    ollama.list()
    OLLAMA_AVAILABLE = True
except Exception as e:
    OLLAMA_AVAILABLE = False

# Configuration from environment
MAX_WORKERS = int(os.getenv('WORKERS', '50'))
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '25'))
OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', '8'))
MAX_CACHE_SIZE = int(os.getenv('MAX_CACHE_SIZE', '5000'))
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))
MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '120'))

ollama_models_str = os.getenv('OLLAMA_MODELS', 'llama2,mistral,neural-chat,orca-mini')
OLLAMA_MODELS = [model.strip() for model in ollama_models_str.split(',')]

if os.getenv('OLLAMA_AVAILABLE', '').lower() == 'false':
    OLLAMA_AVAILABLE = False

CONFIDENCE_THRESHOLDS = {
    'exact_match': 1.0,
    'fuzzy_match': 0.90,
    'semantic_perfect': 0.85,
    'hybrid_confirmed': 0.75,
    'high': 0.60,
    'medium': 0.40,
    'low': 0.25,
    'fallback': 0.0
}

# ============================================================================
# DEFAULT SMALL TALK (Always available even if Bot is empty)
# ============================================================================
DEFAULT_SMALL_TALK = [
    {"intent": "default_greeting",
     "patterns": ["hi", "hello", "hey", "hii", "hi there", "good morning", "good evening", "greetings"],
     "responses": ["Hello! How can I help you today?", "Hi there! What can I do for you?",
                   "Greetings! How may I assist you?"]},
    {"intent": "default_goodbye", "patterns": ["bye", "goodbye", "see you", "catch you later", "exit", "quit"],
     "responses": ["Goodbye! Have a great day.", "See you later!", "Bye! Let me know if you need anything else."]},
    {"intent": "default_thanks", "patterns": ["thanks", "thank you", "appreciate it", "thanks a lot"],
     "responses": ["You're welcome!", "Happy to help!", "Anytime!"]},
    {"intent": "default_how_are_you", "patterns": ["how are you", "how are you doing", "what's up", "how do you do"],
     "responses": ["I'm doing well, thank you for asking! How can I help you today?",
                   "I'm ready to help! What's on your mind?"]},
    {"intent": "default_help", "patterns": ["help", "i need help", "can you help me", "support", "assist me"],
     "responses": ["Of course! What do you need help with?", "I'm here to help. Please ask your question."]}
]


# FUZZY MATCHING UTILITIES
def calculate_levenshtein_distance(str1: str, str2: str) -> int:
    if LEVENSHTEIN_AVAILABLE:
        return levenshtein_distance(str1, str2)
    else:
        if len(str1) < len(str2): return calculate_levenshtein_distance(str2, str1)
        if len(str2) == 0: return len(str1)
        previous_row = range(len(str2) + 1)
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]


def character_ngram_similarity(str1: str, str2: str, n: int = 2) -> float:
    def get_ngrams(text: str, n: int) -> set:
        text = text.lower().strip()
        return set(text[i:i + n] for i in range(len(text) - n + 1))

    ngrams1 = get_ngrams(str1, n)
    ngrams2 = get_ngrams(str2, n)
    if not ngrams1 or not ngrams2: return 0.0
    intersection = ngrams1 & ngrams2
    union = ngrams1 | ngrams2
    return len(intersection) / len(union) if union else 0.0


def _safe_cache_set(user_id: int, key: str, value: tuple, chatbot_id: int, ttl: int = 1800):
    try:
        SMART_CACHE.set(user_id, key, value, session_id=str(chatbot_id), ttl=ttl)
    except Exception as e:
        pass


# ML MODEL CACHE
class MLModelCache:
    def __init__(self):
        self.models: Dict[str, Dict] = {}
        self.lock = RLock()

    def get_model(self, user_id: int, chatbot_id: int, model_type: str = 'svm'):
        cache_key = f"{user_id}_{chatbot_id}_{model_type}"
        with self.lock:
            if cache_key in self.models:
                cached = self.models[cache_key]
                if time.time() - cached['loaded_at'] < 3600:
                    return cached['model'], cached['vectorizer'], cached['label_encoder']

            base_folder = os.getenv('BASE_DATA_FOLDER', 'data')
            models_dir = os.path.join(base_folder, 'users', f'user_{user_id}',
                                      'chatbots', f'chatbot_{chatbot_id}', 'models')
            model_path = os.path.join(models_dir, f'{model_type}_model.pkl')
            vectorizer_path = os.path.join(models_dir, f'{model_type}_vectorizer.pkl')

            if not os.path.exists(model_path) or not os.path.exists(vectorizer_path):
                return None, None, None

            try:
                with open(model_path, 'rb') as f:
                    model_data = pickle.load(f)
                with open(vectorizer_path, 'rb') as f:
                    vectorizer = pickle.load(f)

                if isinstance(model_data, dict):
                    model = model_data.get('model')
                    label_encoder = model_data.get('label_encoder')
                    training_info = model_data.get('training_info', {})
                else:
                    model = model_data
                    label_encoder = None
                    training_info = {}

                self.models[cache_key] = {
                    'model': model, 'vectorizer': vectorizer,
                    'label_encoder': label_encoder, 'loaded_at': time.time(),
                    'training_info': training_info
                }
                return model, vectorizer, label_encoder

            except Exception as e:
                return None, None, None

    def clear_cache(self, user_id: int = None, chatbot_id: int = None):
        with self.lock:
            if user_id and chatbot_id:
                to_remove = [k for k in self.models.keys() if k.startswith(f"{user_id}_{chatbot_id}_")]
                for key in to_remove: del self.models[key]
            elif user_id:
                to_remove = [k for k in self.models.keys() if k.startswith(f"{user_id}_")]
                for key in to_remove: del self.models[key]
            else:
                self.models.clear()


ML_MODEL_CACHE = MLModelCache()


# FALLBACK MANAGER
class FallbackMessageManager:
    UNDERSTANDING = ["I'm sorry, I didn't fully understand that. Could you please rephrase?",
                     "I may have missed that. Can you share more detail?"]
    OUT_OF_SCOPE = ["That's a great question, but I don't have that information right now.",
                    "I'm unable to help with that request at the moment."]
    RETRY = ["Try asking in another way.", "Please use simpler or more specific keywords."]
    ERROR = ["Apologies, I couldn't process that request.", "Something went wrong. Let's try again."]
    ESCALATION = ["Would you like to connect with a support representative?",
                  "For further help, please contact our support team."]
    VOICE = ["Sorry, I didn't catch that.", "Can you please repeat?"]
    LOW_CONFIDENCE = ["I'm not entirely confident. Could you clarify?",
                      "I need more information for an accurate answer."]
    NO_MATCH = ["I understand your question, but don't have specific info on that.",
                "That's clear—but it's not in my current knowledge base."]

    def __init__(self):
        self.user_failure_count = defaultdict(int)
        self.lock = RLock()

    def get_fallback(self, situation: str, user_id: int = None, session_id: str = None, confidence: float = 0.0,
                     is_voice: bool = False) -> str:
        failure_key = f"{user_id}_{session_id}" if user_id and session_id else str(user_id or "anon")
        with self.lock:
            self.user_failure_count[failure_key] += 1
            failure_count = self.user_failure_count[failure_key]

        if failure_count >= 3:
            with self.lock: self.user_failure_count[failure_key] = 0
            return random.choice(self.ESCALATION)

        if is_voice: return random.choice(self.VOICE)

        messages = {
            'understanding': self.UNDERSTANDING, 'out_of_scope': self.OUT_OF_SCOPE,
            'retry': self.RETRY, 'error': self.ERROR, 'escalation': self.ESCALATION,
            'voice': self.VOICE, 'low_confidence': self.LOW_CONFIDENCE, 'no_match': self.NO_MATCH
        }.get(situation, self.UNDERSTANDING)
        return random.choice(messages)

    def get_smart_fallback(self, confidence: float, kb_available: bool, ollama_failed: bool, user_id: int = None,
                           session_id: str = None, is_voice: bool = False) -> str:
        failure_key = f"{user_id}_{session_id}" if user_id and session_id else str(user_id or "anon")
        with self.lock:
            failure_count = self.user_failure_count.get(failure_key, 0)
        if failure_count >= 3: return self.get_fallback('escalation', user_id, session_id, confidence, is_voice)
        if is_voice: return self.get_fallback('voice', user_id, session_id, confidence, is_voice)
        if confidence < CONFIDENCE_THRESHOLDS['low']: return self.get_fallback('understanding', user_id, session_id,
                                                                               confidence, is_voice)
        if confidence < CONFIDENCE_THRESHOLDS['medium']: return self.get_fallback('low_confidence', user_id, session_id,
                                                                                  confidence, is_voice)
        if confidence >= CONFIDENCE_THRESHOLDS['medium'] and not kb_available: return self.get_fallback('no_match',
                                                                                                        user_id,
                                                                                                        session_id,
                                                                                                        confidence,
                                                                                                        is_voice)
        if ollama_failed and not kb_available: return self.get_fallback('out_of_scope', user_id, session_id, confidence,
                                                                        is_voice)
        return self.get_fallback('retry', user_id, session_id, confidence, is_voice)

    def reset_failure_count(self, user_id: int, session_id: str = None):
        failure_key = f"{user_id}_{session_id}" if session_id else str(user_id)
        with self.lock: self.user_failure_count[failure_key] = 0


FALLBACK_MANAGER = FallbackMessageManager()

# THREAD POOL & TRACKERS
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="chatbot_worker")


def with_timeout(timeout: int = 10):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except FutureTimeoutError:
                return None
            except Exception as e:
                return None

        return wrapper

    return decorator


class RequestTracker:
    def __init__(self):
        self.active_requests: Dict[str, Dict] = {}
        self.user_requests: Dict[int, List[str]] = defaultdict(list)
        self.lock = RLock()

    def start_request(self, user_id: int, session_id: str, message: str) -> str:
        request_id = f"req_{user_id}_{session_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        with self.lock:
            self.active_requests[request_id] = {
                'user_id': user_id, 'session_id': session_id, 'message': message[:100],
                'start_time': time.time(), 'status': 'processing'
            }
            self.user_requests[user_id].append(request_id)
        return request_id

    def end_request(self, request_id: str, success: bool = True):
        with self.lock:
            if request_id in self.active_requests:
                req = self.active_requests[request_id]
                req['status'] = 'completed' if success else 'failed'
                req['end_time'] = time.time()
                user_id = req['user_id']
                if request_id in self.user_requests[user_id]: self.user_requests[user_id].remove(request_id)
                if time.time() - req['start_time'] > 60: del self.active_requests[request_id]


REQUEST_TRACKER = RequestTracker()


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        self.lock = RLock()

    def _get_key(self, session_id: str, user_id: int) -> str:
        return f"u{user_id}_s{session_id}"

    def get_session(self, session_id: str, user_id: int) -> Optional[Dict]:
        key = self._get_key(session_id, user_id)
        with self.lock: return self.sessions.get(key)

    def set_session(self, session_id: str, user_id: int, data: Dict):
        key = self._get_key(session_id, user_id)
        with self.lock:
            self.sessions[key] = data
            if len(self.sessions) > MAX_CACHE_SIZE: self._cleanup_old()

    def _cleanup_old(self):
        with self.lock:
            items = list(self.sessions.items())
            items.sort(key=lambda x: x[1].get('created_at', 0))
            to_remove = len(items) // 10
            for key, _ in items[:to_remove]: del self.sessions[key]

    def add_message(self, session_id: str, user_id: int, user_msg: str, bot_msg: str):
        with self.lock:
            session = self.get_session(session_id, user_id)
            if not session: session = {'history': [], 'user_id': user_id, 'session_id': session_id,
                                       'created_at': time.time()}
            session['history'].append({'user': user_msg, 'bot': bot_msg, 'timestamp': time.time()})
            session['history'] = session['history'][-10:]
            self.set_session(session_id, user_id, session)

    def get_context(self, session_id: str, user_id: int, last_n: int = 2) -> str:
        session = self.get_session(session_id, user_id)
        if not session or 'history' not in session: return ""
        history = session['history'][-last_n:]
        context_parts = []
        for entry in history:
            if entry.get('user'): context_parts.append(f"User: {entry['user']}")
            if entry.get('bot'): context_parts.append(f"Assistant: {entry['bot']}")
        return "\n".join(context_parts)

    def clear_user_sessions(self, user_id: int):
        with self.lock:
            to_remove = [k for k in self.sessions.keys() if k.startswith(f"u{user_id}_")]
            for key in to_remove: del self.sessions[key]


SESSION_MANAGER = SessionManager()


class RateLimiter:
    def __init__(self):
        max_rpm = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '120'))
        self.requests: Dict[int, deque] = defaultdict(lambda: deque(maxlen=max_rpm))
        self.lock = RLock()
        self.enabled = os.getenv('RATE_LIMIT_ENABLED', 'True').lower() == 'true'

    def is_allowed(self, user_id: int) -> bool:
        if not self.enabled: return True
        with self.lock:
            now = time.time()
            user_requests = self.requests[user_id]
            while user_requests and now - user_requests[0] > RATE_LIMIT_WINDOW: user_requests.popleft()
            if len(user_requests) >= MAX_REQUESTS_PER_MINUTE: return False
            user_requests.append(now)
            return True


RATE_LIMITER = RateLimiter()


class SmartCache:
    def __init__(self):
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.lock = RLock()

    def _get_key(self, user_id: int, query: str, session_id: str = None) -> str:
        query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()
        session_part = f"_s{session_id}" if session_id else ""
        return f"u{user_id}_{query_hash}{session_part}"

    def get(self, user_id: int, query: str, session_id: str = None) -> Optional[Any]:
        key = self._get_key(user_id, query, session_id)
        with self.lock:
            if key in self.cache:
                value, expire_time = self.cache[key]
                if time.time() < expire_time:
                    return value
                else:
                    del self.cache[key]
        return None

    def set(self, user_id: int, query: str, value: Any, session_id: str = None, ttl: int = None):
        if ttl is None: ttl = int(os.getenv('ML_CACHE_TTL', '1800'))
        key = self._get_key(user_id, query, session_id)
        expire_time = time.time() + ttl
        with self.lock:
            self.cache[key] = (value, expire_time)
            if len(self.cache) > MAX_CACHE_SIZE: self._cleanup_expired()

    def _cleanup_expired(self):
        now = time.time()
        with self.lock:
            expired = [k for k, (_, exp) in self.cache.items() if exp < now]
            for k in expired: del self.cache[k]
            if len(self.cache) > MAX_CACHE_SIZE:
                sorted_items = sorted(self.cache.items(), key=lambda x: x[1][1])
                to_remove = len(self.cache) - (MAX_CACHE_SIZE // 2)
                for k, _ in sorted_items[:to_remove]: del self.cache[k]

    def clear_user(self, user_id: int):
        with self.lock:
            to_remove = [k for k in self.cache.keys() if k.startswith(f"u{user_id}_")]
            for k in to_remove: del self.cache[k]


SMART_CACHE = SmartCache()


def preprocess_text(input_text: str) -> str:
    if not input_text: return ""
    processed = input_text.lower()
    processed = processed.translate(str.maketrans('', '', string.punctuation))
    return ' '.join(processed.split())


def clean_html_tags(text: str) -> str:
    if not text: return ""
    text = unescape(text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


_sentence_transformer = None
_st_lock = RLock()


def get_sentence_transformer():
    global _sentence_transformer
    if not SENTENCE_TRANSFORMERS_AVAILABLE: return None
    with _st_lock:
        if _sentence_transformer is None:
            try:
                from sentence_transformers import SentenceTransformer
                _sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
            except Exception as e:
                return None
        return _sentence_transformer


# ============================================================================
# ★ LIVE DATABASE CONNECTION: Runs synchronously to preserve Flask Context
# ============================================================================
# REMOVED @with_timeout(5) SO IT DOES NOT LOSE FLASK CONTEXT!
def load_knowledge_base(user_id: int, chatbot_id: int = None) -> List[Dict]:
    if not chatbot_id: return []
    cache_key = f"kb_{user_id}_{chatbot_id}"

    # Very short 2-second cache so UI changes show up practically instantly
    cached_kb = SMART_CACHE.get(user_id, cache_key, session_id=str(chatbot_id))
    if cached_kb: return cached_kb

    valid_kb = []

    # 1. ALWAYS TRY THE LIVE DATABASE FIRST
    try:
        from base.com.vo.qa_pair_vo import QAPair
        db_pairs = QAPair.query.filter_by(chatbot_id=chatbot_id).all()
        if db_pairs:
            tag_map = {}
            for p in db_pairs:
                if not p.question or not p.answer: continue
                # Assign a tag if none exists
                tag = p.tag or f"qa_{p.id}"
                if tag not in tag_map:
                    # ✅ FIX: Always add the question to patterns on first creation!
                    tag_map[tag] = {'patterns': [p.question], 'responses': [p.answer]}
                else:
                    tag_map[tag]['patterns'].append(p.question)

            for tag, data in tag_map.items():
                valid_kb.append({
                    'intent': tag,
                    'tag': tag,
                    'patterns': data['patterns'],
                    'responses': data['responses'],
                    'chatbot_id': chatbot_id
                })
    except Exception as e:
        pass

    # 2. IF DB FAILS OR IS EMPTY, FALLBACK TO JSON FILE
    if not valid_kb:
        try:
            base_folder = os.getenv('BASE_DATA_FOLDER', 'data')
            kb_path = os.path.join(base_folder, 'users', f'user_{user_id}', 'chatbots', f'chatbot_{chatbot_id}',
                                   'knowledge_base.json')
            if os.path.exists(kb_path):
                with open(kb_path, 'r', encoding='utf-8') as f:
                    kb_data = json.load(f)
                for item in kb_data:
                    if not isinstance(item, dict): continue
                    intent = item.get('intent') or item.get('tag')
                    if intent and item.get('patterns') and item.get('responses'):
                        valid_kb.append(item)
        except Exception as e:
            pass

    if valid_kb:
        # Cache for just 2 seconds so it refreshes almost instantly!
        SMART_CACHE.set(user_id, cache_key, valid_kb, session_id=str(chatbot_id), ttl=2)

    return valid_kb


def clear_model_cache(user_id: int, chatbot_id: int = None) -> None:
    try:
        SMART_CACHE.clear_user(user_id)
        SESSION_MANAGER.clear_user_sessions(user_id)
        ML_MODEL_CACHE.clear_cache(user_id, chatbot_id)
    except Exception as e:
        pass


@with_timeout(3)
def get_semantic_similarity(query: str, text: str, model=None) -> float:
    if not SENTENCE_TRANSFORMERS_AVAILABLE or model is None: return 0.0
    try:
        if SKLEARN_AVAILABLE: _lazy_import_sklearn()
        query_emb = model.encode(query, convert_to_numpy=True)
        text_emb = model.encode(text, convert_to_numpy=True)
        return float(cosine_similarity([query_emb], [text_emb])[0][0])
    except Exception:
        return 0.0


@lru_cache(maxsize=20000)
def cached_pattern_similarity(user_text: str, pattern: str) -> float:
    user_processed = preprocess_text(user_text)
    pattern_processed = preprocess_text(pattern)
    len_diff = abs(len(user_processed) - len(pattern_processed))
    if len_diff > max(len(user_processed), len(pattern_processed)) * 0.6: return 0.0
    if user_processed == pattern_processed: return 1.0
    user_words = set(user_processed.split())
    pattern_words = set(pattern_processed.split())
    if not user_words or not pattern_words: return 0.0
    intersection = user_words.intersection(pattern_words)
    union = user_words.union(pattern_words)
    jaccard = len(intersection) / len(union) if union else 0.0
    if jaccard < 0.2: return jaccard
    if jaccard > 0.3:
        fuzzy_score = fuzzy_match_score(user_processed, pattern_processed, max_errors=2)
        if fuzzy_score >= 0.85: return fuzzy_score
    if pattern_processed in user_processed:
        jaccard += 0.25
    elif user_processed in pattern_processed:
        jaccard += 0.20
    overlap_ratio = len(intersection) / len(pattern_words) if pattern_words else 0
    if overlap_ratio > 0.8: jaccard += 0.15
    return min(1.0, jaccard)


def calculate_pattern_similarity(user_text: str, pattern: str) -> float:
    return cached_pattern_similarity(user_text, pattern)


def fuzzy_match_score(query: str, pattern: str, max_errors: int = 2) -> float:
    query_clean = query.lower().strip()
    pattern_clean = pattern.lower().strip()
    if query_clean == pattern_clean: return 1.0
    if LEVENSHTEIN_AVAILABLE:
        from Levenshtein import distance
        edit_distance = distance(query_clean, pattern_clean)
    else:
        edit_distance = sum(1 for a, b in zip(query_clean, pattern_clean) if a != b)
        edit_distance += abs(len(query_clean) - len(pattern_clean))
    if edit_distance <= max_errors: return max(0.85, 1.0 - (edit_distance * 0.05))
    max_len = max(len(query_clean), len(pattern_clean))
    if max_len == 0: return 0.0
    return max(0.0, 1.0 - (edit_distance / max_len))


def get_ml_intent_prediction(query: str, user_id: int, chatbot_id: int) -> Tuple[Optional[str], float]:
    if not SKLEARN_AVAILABLE: return None, 0.0
    try:
        model, vectorizer, label_encoder = ML_MODEL_CACHE.get_model(user_id, chatbot_id, 'svm')
        if model and vectorizer and label_encoder:
            query_vector = vectorizer.transform([query])
            if hasattr(model, 'predict_proba'):
                probabilities = model.predict_proba(query_vector)[0]
                predicted_class = np.argmax(probabilities)
                confidence = float(probabilities[predicted_class])
            elif hasattr(model, 'decision_function'):
                decision_scores = model.decision_function(query_vector)[0]
                predicted_class = np.argmax(decision_scores)
                exp_scores = np.exp(decision_scores - np.max(decision_scores))
                probabilities = exp_scores / np.sum(exp_scores)
                confidence = float(probabilities[predicted_class])
            else:
                predicted_class = model.predict(query_vector)[0]
                confidence = 0.75
            intent = label_encoder.inverse_transform([predicted_class])[0]
            return intent, float(confidence)
        return None, 0.0
    except Exception as e:
        return None, 0.0


# ============================================================================
# INTENT DETECTION (WITH FORCED CUSTOM PRIORITY & KEYWORD MATCHING)
# ============================================================================
def get_intent_with_confidence(query: str, user_id: int, chatbot_id: int = None) -> Tuple[Optional[str], float]:
    if not chatbot_id or not query or not isinstance(query, str): return None, 0.0
    query = query.strip()
    if len(query) == 0: return None, 0.0

    cache_key = f"intent:{query}_{chatbot_id}"
    try:
        cached = SMART_CACHE.get(user_id, cache_key, session_id=str(chatbot_id))
        if cached and isinstance(cached, tuple) and len(cached) == 2: return cached
    except Exception:
        pass

    # LOAD LIVE KB FROM DATABASE
    try:
        kb = load_knowledge_base(user_id, chatbot_id=chatbot_id)
        if kb is None: kb = []
    except Exception:
        kb = []

    query_processed = preprocess_text(query)

    # ★ STOP WORDS: We remove these basic words so the bot only focuses on the important keywords!
    STOP_WORDS = {"is", "what", "how", "the", "a", "an", "of", "to", "in", "for", "and", "with", "on", "at", "by",
                  "this", "that", "it", "are", "you", "i", "my", "me", "do", "does", "can", "could", "would", "will",
                  "please", "tell", "about", "us", "we", "am"}

    # Create a set of keywords from the user's message
    query_words = set(w for w in query_processed.split() if w not in STOP_WORDS)

    try:
        st_model = get_sentence_transformer()
    except Exception:
        pass

    best_intent = None
    best_score = 0.0

    # ────────────────────────────────────────────────────────────────
    # ★ PHASE 1: CUSTOM KNOWLEDGE BASE ONLY (Highest Priority) ★
    # ────────────────────────────────────────────────────────────────
    for item in kb:
        intent = item.get('intent') or item.get('tag')
        if not intent: continue
        for pattern in item.get('patterns', []):
            pattern_processed = preprocess_text(pattern)
            pattern_words = set(w for w in pattern_processed.split() if w not in STOP_WORDS)

            # 1. Exact Match
            if query_processed == pattern_processed:
                result = (intent, 1.0)
                _safe_cache_set(user_id, cache_key, result, chatbot_id)
                return result

            # 2. Substring Match (e.g. pattern "pricing" is inside query "tell me about pricing")
            if len(pattern_processed) > 2 and pattern_processed in query_processed:
                score = 0.95
                if score > best_score:
                    best_score = score
                    best_intent = intent

            # 3. Any Word Match (If any non-stop-word matches exactly!)
            if query_words and pattern_words:
                overlap = len(query_words & pattern_words)
                if overlap > 0:
                    score = 0.80 + (overlap / max(len(query_words), len(pattern_words))) * 0.15
                    if score > best_score:
                        best_score = score
                        best_intent = intent

    # If Custom KB had a solid hit, RETURN IMMEDIATELY (Ignores Default Small Talk completely)
    if best_intent and best_score >= 0.80:
        result = (best_intent, best_score)
        _safe_cache_set(user_id, cache_key, result, chatbot_id)
        return result

    # ────────────────────────────────────────────────────────────────
    # ★ PHASE 2: ML MODEL FOR CUSTOM KB ★
    # ────────────────────────────────────────────────────────────────
    try:
        ml_intent, ml_confidence = get_ml_intent_prediction(query, user_id, chatbot_id)
        if ml_intent and ml_confidence >= 0.65:
            result = (ml_intent, ml_confidence)
            _safe_cache_set(user_id, cache_key, result, chatbot_id)
            return result
    except Exception:
        pass

    # ────────────────────────────────────────────────────────────────
    # ★ PHASE 3: DEFAULT SMALL TALK (General Intents) ★
    # ────────────────────────────────────────────────────────────────
    # Only runs if Custom KB had NO matches!
    general_best_intent = None
    general_best_score = 0.0

    for item in DEFAULT_SMALL_TALK:
        intent = item.get('intent') or item.get('tag')
        for pattern in item.get('patterns', []):
            pattern_processed = preprocess_text(pattern)

            # Exact Match
            if query_processed == pattern_processed:
                general_best_score = 0.90
                general_best_intent = intent
                break

            # Word Overlap
            q_words = set(query_processed.split())
            p_words = set(pattern_processed.split())
            if q_words and p_words:
                overlap_ratio = len(q_words & p_words) / max(len(q_words), len(p_words))
                if overlap_ratio >= 0.5:
                    score = 0.70 + overlap_ratio * 0.20
                    if score > general_best_score:
                        general_best_score = score
                        general_best_intent = intent

    if general_best_intent and general_best_score > best_score:
        best_score = general_best_score
        best_intent = general_best_intent

    # ────────────────────────────────────────────────────────────────
    # ★ PHASE 4: FALLBACK PATTERN MATCHING (Fuzzy) ★
    # ────────────────────────────────────────────────────────────────
    if best_score < 0.60:
        combined_kb = kb + DEFAULT_SMALL_TALK
        for item in combined_kb:
            intent = item.get('intent') or item.get('tag')
            if not intent: continue
            for pattern in item.get('patterns', []):
                pattern_score = calculate_pattern_similarity(query, pattern)
                if pattern_score > best_score:
                    best_score = pattern_score
                    best_intent = intent

    MIN_CONFIDENCE = 0.30
    if best_intent and best_score >= MIN_CONFIDENCE:
        result = (best_intent, best_score)
        _safe_cache_set(user_id, cache_key, result, chatbot_id, ttl=1800)
        return result
    else:
        if best_score > 0.0:
            result = (best_intent, best_score)
            _safe_cache_set(user_id, cache_key, result, chatbot_id, ttl=600)
            return result
        return None, 0.0


# REMOVED @with_timeout(5) SO IT DOES NOT LOSE FLASK CONTEXT!
def get_response_from_kb(intent: str, user_id: int, chatbot_id: int = None) -> Optional[str]:
    if not chatbot_id: return None
    try:
        kb = load_knowledge_base(user_id, chatbot_id=chatbot_id)
        if kb is None: kb = []
    except Exception:
        kb = []

    combined_kb = kb + DEFAULT_SMALL_TALK

    try:
        intent_lower = intent.lower().strip()
        for item in combined_kb:
            item_intent = (item.get('intent') or item.get('tag', '')).lower().strip()
            if item_intent == intent_lower:
                responses = item.get('responses', [])
                if not responses: continue

                valid_responses = [r for r in responses if r and r.strip()]
                if valid_responses:
                    return clean_html_tags(random.choice(valid_responses).strip())
        return None
    except Exception:
        return None


def get_available_ollama_model() -> Optional[str]:
    if not OLLAMA_AVAILABLE or ollama is None: return None
    try:
        api_response = ollama.list()
        models_data = api_response.get('models', [])
        if not models_data: return None
        available = []
        for item in models_data:
            name = item.model if hasattr(item, 'model') else (item.get('model') or item.get('name'))
            if name: available.append(name.split(':')[0])
        available = list(set(available))
        if not available: return None
        for pref in OLLAMA_MODELS:
            if pref in available: return pref
        return available[0]
    except Exception:
        return None


def generate_ollama_response(query: str, user_id: int, context: str = None, session_id: str = None) -> Optional[str]:
    if os.getenv('OLLAMA_AVAILABLE', 'False').lower() == 'false': return None
    if not OLLAMA_AVAILABLE or ollama is None: return None
    try:
        model = get_available_ollama_model()
        if not model: return None
        kb_context = f"Context: {context}\n\n" if context else ""
        session_ctx = SESSION_MANAGER.get_context(session_id, user_id) if session_id else ""
        if session_ctx: session_ctx = f"Previous:\n{session_ctx}\n\n"
        system_prompt = "You are a helpful, knowledgeable assistant. Provide clear, accurate, and helpful answers. Keep responses concise (2-4 sentences) but informative. If you don't know something, say so briefly instead of guessing."
        user_prompt = f"{kb_context}{session_ctx}Question: {query}\n\nAnswer:"
        response = ollama.chat(
            model=model,
            messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}],
            options={'temperature': 0.5, 'top_p': 0.9, 'num_predict': 200, 'num_ctx': 2048},
            stream=False
        )
        answer = response.get('message', {}).get('content', '').strip()
        if not answer or len(answer) < 5: return None
        if not validate_ollama_response(answer, query): return None
        return answer
    except Exception as e:
        return None


def validate_ollama_response(response: str, query: str) -> bool:
    if not response or len(response) < 10: return False
    generic_responses = ["i'm not sure", "i don't have information", "i cannot help", "i don't know",
                         "unable to answer"]
    response_lower = response.lower()
    for generic in generic_responses:
        if generic in response_lower: return False
    return True


def get_smart_response(user_message: str, user_id: int, chatbot_id: int = None, session_id: str = None,
                       is_voice: bool = False) -> str:
    if not chatbot_id: return "Configuration error: Chatbot ID is required."
    cache_key = f"resp_{user_id}_{chatbot_id}_{hashlib.md5(user_message.lower().encode()).hexdigest()}"
    cached = get_cached_response(cache_key)
    if cached: return cached

    request_id = REQUEST_TRACKER.start_request(user_id, session_id or "unknown", user_message)
    start_time = time.time()

    try:
        ML_MODEL_CACHE.get_model(user_id, chatbot_id, 'svm')
    except:
        pass

    try:
        if not RATE_LIMITER.is_allowed(user_id): return "Rate limit exceeded. Please wait."

        intent, confidence = get_intent_with_confidence(user_message, user_id, chatbot_id=chatbot_id)
        response = None
        kb_response_available = False
        ollama_failed = False

        if intent and confidence >= CONFIDENCE_THRESHOLDS['medium']:
            kb_response = get_response_from_kb(intent, user_id, chatbot_id=chatbot_id)
            if kb_response:
                kb_response_available = True
                response = kb_response
                FALLBACK_MANAGER.reset_failure_count(user_id, session_id)
                if session_id: SESSION_MANAGER.add_message(session_id, user_id, user_message, response)
                REQUEST_TRACKER.end_request(request_id, True)
                set_cached_response(cache_key, response)
                return response

        if not response:
            if OLLAMA_AVAILABLE:
                ollama_response = generate_ollama_response(user_message, user_id, session_id=session_id)
                if ollama_response:
                    response = ollama_response
                    FALLBACK_MANAGER.reset_failure_count(user_id, session_id)
                else:
                    ollama_failed = True

        if OLLAMA_AVAILABLE and not response:
            ollama_response = generate_ollama_response(user_message, user_id, session_id=session_id)
            if ollama_response:
                response = ollama_response
                FALLBACK_MANAGER.reset_failure_count(user_id, session_id)
            else:
                ollama_failed = True

        if not response:
            response = FALLBACK_MANAGER.get_smart_fallback(
                confidence=confidence, kb_available=kb_response_available,
                ollama_failed=ollama_failed, user_id=user_id, session_id=session_id, is_voice=is_voice
            )

        if session_id and response: SESSION_MANAGER.add_message(session_id, user_id, user_message, response)
        REQUEST_TRACKER.end_request(request_id, True)
        if response and confidence >= CONFIDENCE_THRESHOLDS['medium']: set_cached_response(cache_key, response)
        return response

    except Exception as e:
        REQUEST_TRACKER.end_request(request_id, False)
        return FALLBACK_MANAGER.get_fallback('error', user_id, session_id, 0.0, is_voice)


def predict_class(message: str, user_id: int, chatbot_id: int = None) -> str:
    intent, _ = get_intent_with_confidence(message, user_id, chatbot_id)
    return intent or 'unknown'


def get_confidence_score(message: str, user_id: int, chatbot_id: int = None) -> float:
    _, confidence = get_intent_with_confidence(message, user_id, chatbot_id)
    return confidence


def get_response_from_intent(intent: str, user_id: int, chatbot_id: int = None) -> Optional[str]:
    return get_response_from_kb(intent, user_id, chatbot_id)


def load_user_model(user_id: int, chatbot_id: int = None) -> bool:
    try:
        if not chatbot_id: return False
        base_folder = os.getenv('BASE_DATA_FOLDER', 'data')
        models_dir = os.path.join(base_folder, 'users', f'user_{user_id}', 'chatbots', f'chatbot_{chatbot_id}',
                                  'models')
        if not os.path.exists(models_dir): return False
        model_types = ['svm', 'neural_network', 'naive_bayes']
        loaded = False
        for model_type in model_types:
            model_path = os.path.join(models_dir, f'{model_type}_model.pkl')
            vectorizer_path = os.path.join(models_dir, f'{model_type}_vectorizer.pkl')
            if os.path.exists(model_path) and os.path.exists(vectorizer_path):
                model, vec, le = ML_MODEL_CACHE.get_model(user_id, chatbot_id, model_type)
                if model and vec:
                    loaded = True
                    try:
                        dummy_vector = vec.transform(["test"])
                        if hasattr(model, 'predict_proba'):
                            _ = model.predict_proba(dummy_vector)
                        else:
                            _ = model.predict(dummy_vector)
                    except Exception:
                        pass
                    break
        return loaded
    except Exception as e:
        return False


def get_model_info(user_id: int, chatbot_id: int = None) -> Dict[str, Any]:
    try:
        if chatbot_id:
            base_folder = os.getenv('BASE_DATA_FOLDER', 'data')
            metadata_path = os.path.join(base_folder, 'users', f'user_{user_id}', 'chatbots', f'chatbot_{chatbot_id}',
                                         'model_metadata.json')
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f: return json.load(f)
            kb = load_knowledge_base(user_id, chatbot_id=chatbot_id)
            return {'user_id': user_id, 'chatbot_id': chatbot_id, 'is_trained': len(kb) > 0, 'kb_size': len(kb),
                    'intents': len(kb)}
        return {'user_id': user_id, 'is_trained': False}
    except Exception as e:
        return {'user_id': user_id, 'is_trained': False}


def get_knowledge_base_info(user_id: int, chatbot_id: int = None) -> Dict[str, Any]:
    try:
        kb = load_knowledge_base(user_id, chatbot_id)
        return {'available': len(kb) > 0, 'total': len(kb), 'user_id': user_id, 'chatbot_id': chatbot_id}
    except Exception:
        return {'available': False, 'total': 0, 'user_id': user_id}


def get_intent_from_text(text: str, user_id: int, chatbot_id: int = None, threshold: float = 0.0) -> Dict[str, Any]:
    intent, confidence = get_intent_with_confidence(text, user_id, chatbot_id)
    return {'intent': intent or 'unknown', 'confidence': confidence, 'method': 'hybrid', 'threshold': threshold,
            'chatbot_id': chatbot_id}


def get_system_stats() -> Dict[str, Any]:
    return {
        'active_requests': 0, 'cache_stats': {},
        'session_count': len(SESSION_MANAGER.sessions) if hasattr(SESSION_MANAGER, 'sessions') else 0,
        'ollama_available': OLLAMA_AVAILABLE, 'transformers_available': SENTENCE_TRANSFORMERS_AVAILABLE
    }


def periodic_cleanup():
    try:
        SMART_CACHE._cleanup_expired()
    except Exception:
        pass


def get_fallback_message(situation: str, user_id: int = None, session_id: str = None, is_voice: bool = False) -> str:
    return FALLBACK_MANAGER.get_fallback(situation, user_id, session_id, 0.0, is_voice)


def reset_user_fallback_count(user_id: int, session_id: str = None):
    FALLBACK_MANAGER.reset_failure_count(user_id, session_id)


__all__ = [
    'get_smart_response', 'get_intent_with_confidence', 'get_response_from_kb',
    'generate_ollama_response', 'get_fallback_message', 'reset_user_fallback_count',
    'FALLBACK_MANAGER', 'predict_class', 'get_confidence_score', 'get_response_from_intent',
    'clear_model_cache', 'load_user_model', 'get_model_info', 'get_knowledge_base_info',
    'get_intent_from_text', 'get_system_stats', 'periodic_cleanup', 'OLLAMA_AVAILABLE',
    'CONFIDENCE_THRESHOLDS', 'REQUEST_TRACKER', 'RATE_LIMITER', 'SESSION_MANAGER',
    'SMART_CACHE', 'ML_MODEL_CACHE'
]