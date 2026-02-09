import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Load environment variables from .env file
load_dotenv()

LANGUAGE_CODES = {
    "german": "de",
    "english": "en",
    "spanish": "es",
    "polish": "pl",
    "french": "fr",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "russian": "ru",
}

# Admin API Keys from environment variables (fallback)
ADMIN_DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
ADMIN_PONS_API_SECRET = os.environ.get("PONS_API_SECRET", "")
ADMIN_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ADMIN_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ADMIN_GOOGLE_TRANSLATE_API_KEY = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")

# Trial period in days
TRIAL_DAYS = 7


def get_api_key(user_id: int, service: str, db: Session) -> Optional[str]:
    """Resolve API key for a user and service.

    1. User's own key in DB -> decrypt, return
    2. User within trial period (7 days since created_at) -> admin key from .env
    3. Otherwise -> None (service disabled)
    """
    from models import User, UserApiKey
    from auth import decrypt_api_key

    # 1. Check for user's own key
    user_key = db.query(UserApiKey).filter(
        UserApiKey.user_id == user_id,
        UserApiKey.service == service
    ).first()

    if user_key:
        try:
            return decrypt_api_key(user_key.api_key)
        except Exception:
            return None

    # 2. Check trial period
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    # Admin user (id=1 or username "admin") always gets admin keys
    if user.id == 1 or user.username == "admin":
        return _get_admin_key(service)

    created_at = user.created_at
    if created_at is None:
        # Legacy user without created_at - give them admin key
        return _get_admin_key(service)

    if datetime.utcnow() - created_at < timedelta(days=TRIAL_DAYS):
        return _get_admin_key(service)

    # 3. Trial expired, no own key
    return None


def get_trial_days_remaining(user) -> int:
    """Return remaining trial days for a user. 0 if expired."""
    if user.id == 1 or user.username == "admin":
        return 999  # Admin always has access
    if user.created_at is None:
        return 0
    elapsed = datetime.utcnow() - user.created_at
    remaining = TRIAL_DAYS - elapsed.days
    return max(0, remaining)


def _get_admin_key(service: str) -> Optional[str]:
    """Get admin key from .env for a service."""
    mapping = {
        "deepl": ADMIN_DEEPL_API_KEY,
        "pons": ADMIN_PONS_API_SECRET,
        "google": ADMIN_GOOGLE_TRANSLATE_API_KEY,
        "groq": ADMIN_GROQ_API_KEY,
        "gemini": ADMIN_GEMINI_API_KEY,
    }
    key = mapping.get(service, "")
    return key if key else None


def translate_google(text: str, source: str, target: str, api_key: str = None) -> str:
    """Google Cloud Translation API (official) with free fallback."""
    try:
        if source == target:
            return text

        if api_key:
            # Official Google Cloud Translation API v2
            url = "https://translation.googleapis.com/language/translate/v2"
            params = {
                "key": api_key,
                "q": text,
                "source": source,
                "target": target,
                "format": "text",
            }
            response = requests.post(url, params=params, timeout=8)
            if response.status_code == 200:
                data = response.json()
                translations = data.get("data", {}).get("translations", [])
                if translations:
                    return translations[0]["translatedText"]
            elif response.status_code == 403:
                return "[No API Key]"
            elif response.status_code == 429:
                return "[Limit]"
            return "[Error]"
        else:
            # Fallback: unofficial free endpoint
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": source,
                "tl": target,
                "dt": "t",
                "q": text
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result and result[0]:
                    return "".join([item[0] for item in result[0] if item[0]])
            elif response.status_code == 429:
                return "[Limit]"
            return "[Error]"
    except Exception:
        return "[Error]"


def translate_mymemory(text: str, source: str, target: str) -> str:
    """MyMemory Translation API (free, no key needed)."""
    try:
        if source == target:
            return text
        url = "https://api.mymemory.translated.net/get"
        params = {
            "q": text,
            "langpair": f"{source}|{target}"
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("responseStatus") == 200:
                trans = data["responseData"]["translatedText"]
                # MyMemory sometimes returns uppercase, normalize
                if trans.isupper() and not text.isupper():
                    trans = trans.capitalize()
                return trans
        return "[Error]"
    except Exception:
        return "[Error]"


def translate_yandex(text: str, source: str, target: str) -> str:
    """Yandex Translate (free tier)."""
    try:
        if source == target:
            return text

        url = "https://translate.yandex.net/api/v1/tr.json/translate"
        params = {
            "lang": f"{source}-{target}",
            "text": text,
            "srv": "android"
        }
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }

        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("text"):
                return data["text"][0]
        return "[Error]"
    except Exception:
        return "[Error]"


def translate_reverso(text: str, source: str, target: str) -> str:
    """Reverso Translation API."""
    try:
        if source == target:
            return text

        # Reverso language codes
        lang_map = {
            'de': 'ger',
            'en': 'eng',
            'es': 'spa',
            'pl': 'pol',
            'fr': 'fra',
            'it': 'ita',
            'pt': 'por',
            'nl': 'dut',
            'ru': 'rus',
        }

        src = lang_map.get(source, 'eng')
        tgt = lang_map.get(target, 'eng')

        url = "https://api.reverso.net/translate/v1/translation"
        payload = {
            "input": text,
            "from": src,
            "to": tgt,
            "format": "text",
            "options": {
                "sentenceSplitter": False,
                "contextResults": False,
                "languageDetection": False
            }
        }
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        }

        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("translation"):
                return data["translation"][0]
        return "[Error]"
    except Exception:
        return "[Error]"


def translate_deepl(text: str, source: str, target: str, api_key: str = None) -> str:
    """DeepL Translation API (official, high quality)."""
    try:
        if source == target:
            return text

        if not api_key:
            return "[No API Key]"

        # DeepL source language codes
        source_map = {
            'de': 'DE',
            'en': 'EN',
            'es': 'ES',
            'pl': 'PL',
            'fr': 'FR',
            'it': 'IT',
            'pt': 'PT',
            'nl': 'NL',
            'ru': 'RU',
        }

        # DeepL target language codes (English/Portuguese require region)
        target_map = {
            'de': 'DE',
            'en': 'EN-US',
            'es': 'ES',
            'pl': 'PL',
            'fr': 'FR',
            'it': 'IT',
            'pt': 'PT-PT',
            'nl': 'NL',
            'ru': 'RU',
        }

        src = source_map.get(source, 'EN')
        tgt = target_map.get(target, 'EN-US')

        # DeepL Free API uses api-free.deepl.com
        url = "https://api-free.deepl.com/v2/translate"

        headers = {
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "text": [text],
            "source_lang": src,
            "target_lang": tgt
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("translations"):
                return data["translations"][0]["text"]
        elif response.status_code in [429, 456]:
            return "[Limit]"
        return "[Error]"
    except Exception:
        return "[Error]"


def translate_lingva(text: str, source: str, target: str) -> str:
    """Lingva Translate (free Google Translate frontend)."""
    try:
        if source == target:
            return text

        # Try multiple public Lingva instances
        instances = [
            "https://lingva.ml/api/v1",
            "https://translate.plausibility.cloud/api/v1",
            "https://lingva.garuber.dev/api/v1",
        ]

        for base_url in instances:
            try:
                url = f"{base_url}/{source}/{target}/{requests.utils.quote(text)}"
                response = requests.get(url, timeout=8)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("translation"):
                        return data["translation"]
                elif response.status_code == 429:
                    return "[Limit]"
            except Exception:
                continue

        return "[Error]"
    except Exception:
        return "[Error]"


def translate_pons(text: str, source: str, target: str, api_key: str = None) -> str:
    """PONS Dictionary API (high quality dictionary lookups)."""
    import re
    import html
    try:
        if source == target:
            return text

        if not api_key:
            return "[No API Key]"

        # PONS uses language pair codes like "deen", "dees", "depl"
        lang_map = {
            'de': 'de',
            'en': 'en',
            'es': 'es',
            'pl': 'pl',
            'fr': 'fr',
            'it': 'it',
            'pt': 'pt',
            'nl': 'nl',
            'ru': 'ru',
        }

        src = lang_map.get(source, 'de')
        tgt = lang_map.get(target, 'en')

        # PONS language pair format (source + target, alphabetically sorted in some cases)
        pair = f"{src}{tgt}"

        # Some pairs need to be reversed (PONS convention)
        valid_pairs = ['deen', 'dees', 'depl', 'enes', 'enpl', 'espl', 'defr', 'enfr',
                       'deit', 'enit', 'esit', 'frit', 'deru', 'enru', 'denl', 'ennl',
                       'dept', 'enpt', 'espt', 'frpt']
        reverse_pair = f"{tgt}{src}"

        if pair not in valid_pairs and reverse_pair in valid_pairs:
            pair = reverse_pair

        url = f"https://api.pons.com/v1/dictionary?l={pair}&q={requests.utils.quote(text)}"
        headers = {"X-Secret": api_key}

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                hits = data[0].get("hits", [])
                all_translations = []
                seen = set()

                for hit in hits:
                    roms = hit.get("roms", [])
                    for rom in roms:
                        arabs = rom.get("arabs", [])
                        for arab in arabs:
                            translations = arab.get("translations", [])
                            if translations:
                                target_html = translations[0].get("target", "")
                                source_html = translations[0].get("source", "")
                                if 'class="example"' in source_html:
                                    continue
                                clean = re.sub(r'<[^>]+>', '', target_html)
                                clean = html.unescape(clean)
                                clean = re.sub(r'\s*[mfn]t?\s*<[^>]*>', '', clean)
                                clean = re.sub(r'\s+[fmn]t?\s*$', '', clean)
                                clean = re.sub(r'\s*\[or\s+[^\]]+\]', '', clean)
                                clean = re.sub(r'\s*(dated|inf|form)\s*', ' ', clean)
                                clean = ' '.join(clean.split())
                                if 'sb' in clean or 'sth' in clean:
                                    continue
                                if 'jdn' in clean or 'etw' in clean or 'dat' in clean or 'akk' in clean:
                                    continue
                                if clean.startswith("to ") and len(clean) > 15:
                                    continue
                                if clean.startswith("sich "):
                                    continue
                                if clean and clean.lower() not in seen and len(clean) < 25:
                                    seen.add(clean.lower())
                                    all_translations.append(clean)

                if all_translations:
                    return ", ".join(all_translations[:8])
        elif response.status_code == 429:
            return "[Limit]"
        return "[Error]"
    except Exception:
        return "[Error]"


def get_pons_definition(text: str, lang_code: str, api_key: str = None) -> str:
    """Get word definition from PONS dictionary in the source language."""
    import re
    import html

    if not api_key:
        return ""

    try:
        if lang_code == 'de':
            pair = 'deen'
        elif lang_code == 'en':
            pair = 'deen'
        elif lang_code == 'es':
            pair = 'dees'
        elif lang_code == 'pl':
            pair = 'depl'
        else:
            pair = 'deen'

        url = f"https://api.pons.com/v1/dictionary?l={pair}&q={requests.utils.quote(text)}"
        headers = {"X-Secret": api_key}

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                hits = data[0].get("hits", [])
                definitions = []

                for hit in hits[:2]:
                    roms = hit.get("roms", [])
                    for rom in roms[:2]:
                        wordclass = rom.get("wordclass", "")
                        headword_full = rom.get("headword_full", "")

                        if headword_full:
                            clean_hw = re.sub(r'<[^>]+>', '', headword_full)
                            clean_hw = html.unescape(clean_hw).strip()
                            if wordclass and clean_hw:
                                definitions.append(f"[{wordclass}] {clean_hw}")

                        arabs = rom.get("arabs", [])
                        for arab in arabs[:3]:
                            header = arab.get("header", "")
                            if header:
                                header = re.sub(r'<[^>]+>', '', header)
                                header = html.unescape(header).strip()
                                header = re.sub(r'^\d+\.\s*', '', header)
                                if header and len(header) > 2:
                                    definitions.append(header)

                if definitions:
                    unique = []
                    for d in definitions:
                        d = d.strip()
                        d = re.sub(r':$', '', d).strip()
                        if d and len(d) > 2 and d not in unique and len(unique) < 4:
                            unique.append(d)
                    return " • ".join(unique)

        return ""
    except Exception:
        return ""


def get_groq_explanation(text: str, lang_code: str, api_key: str = None) -> str:
    """Get AI explanation using Groq (LLaMA)."""
    if not api_key:
        return ""

    try:
        lang_names = {
            'de': 'Deutsch',
            'en': 'English',
            'es': 'Español',
            'pl': 'Polski',
            'fr': 'Français',
            'it': 'Italiano',
            'pt': 'Português',
            'nl': 'Nederlands',
            'ru': 'Русский',
        }
        lang_name = lang_names.get(lang_code, 'Deutsch')

        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        prompt = f"""Explain "{text}" briefly in {lang_name}. Maximum 2 sentences. No bullet points."""

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 100
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("choices"):
                return data["choices"][0]["message"]["content"].strip()
        elif response.status_code == 429:
            return "[Limit] API-Limit erreicht"

        return ""
    except Exception:
        return ""


def translate_to_all_languages(
    text: str,
    source_lang: str = None,
    target_languages: list = None,
    enabled_services: dict = None,
    explanation_services: dict = None,
    user_id: int = None,
    db: Session = None
) -> dict:
    """Translate to all target languages using multiple sources in parallel.

    Args:
        text: The text to translate
        source_lang: Source language name (e.g., 'german')
        target_languages: List of target language names
        enabled_services: Dict of service names to booleans
        explanation_services: Dict of explanation services
        user_id: Current user's ID for key resolution
        db: Database session for key resolution
    """

    # Default to german if no source language provided
    if not source_lang or source_lang == "auto":
        source_lang = "german"

    source_code = LANGUAGE_CODES.get(source_lang, "de")

    # Default target languages if not specified
    if target_languages is None:
        target_languages = [lang for lang in ["spanish", "german", "polish", "english"] if lang != source_lang]
    else:
        target_languages = [lang for lang in target_languages if lang != source_lang]

    # Resolve per-user API keys
    deepl_key = None
    pons_key = None
    google_key = None
    groq_key = None

    if user_id and db:
        deepl_key = get_api_key(user_id, "deepl", db)
        pons_key = get_api_key(user_id, "pons", db)
        google_key = get_api_key(user_id, "google", db)
        groq_key = get_api_key(user_id, "groq", db)
    else:
        # Fallback to admin keys (backward compatibility)
        deepl_key = ADMIN_DEEPL_API_KEY or None
        pons_key = ADMIN_PONS_API_SECRET or None
        google_key = ADMIN_GOOGLE_TRANSLATE_API_KEY or None
        groq_key = ADMIN_GROQ_API_KEY or None

    result = {
        "source_language": source_lang,
        "source_text": text,
        "translations": {}
    }

    # Build translator map with resolved keys
    all_translators = {
        "DeepL": lambda t, s, tgt: translate_deepl(t, s, tgt, deepl_key),
        "PONS": lambda t, s, tgt: translate_pons(t, s, tgt, pons_key),
        "Google": lambda t, s, tgt: translate_google(t, s, tgt, google_key),
        "Lingva": translate_lingva,
    }

    # Filter translators based on enabled_services
    if enabled_services:
        translators = {name: func for name, func in all_translators.items()
                       if enabled_services.get(name, True)}
    else:
        translators = all_translators

    # Determine if explanation services are enabled
    pons_explanation_enabled = True
    groq_explanation_enabled = True
    if explanation_services:
        pons_explanation_enabled = explanation_services.get("PONS Definition", True)
        groq_explanation_enabled = explanation_services.get("Groq AI", True)

    # Execute translations and explanations in parallel
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {}

        # Submit PONS definition and Groq explanation requests if enabled
        pons_future = None
        groq_future = None
        if pons_explanation_enabled:
            pons_future = executor.submit(get_pons_definition, text, source_code, pons_key)
        if groq_explanation_enabled:
            groq_future = executor.submit(get_groq_explanation, text, source_code, groq_key)

        for target_lang in target_languages:
            target_code = LANGUAGE_CODES.get(target_lang, "en")
            result["translations"][target_lang] = {}

            for name, func in translators.items():
                future = executor.submit(func, text, source_code, target_code)
                futures[future] = (target_lang, name)

        for future in as_completed(futures):
            target_lang, name = futures[future]
            try:
                translation = future.result()
                result["translations"][target_lang][name] = translation
            except Exception:
                result["translations"][target_lang][name] = "[Error]"

        # Get PONS definition
        if pons_future:
            try:
                result["ai_explanation"] = pons_future.result()
            except Exception:
                result["ai_explanation"] = ""
        else:
            result["ai_explanation"] = ""

        # Get Groq explanation
        if groq_future:
            try:
                result["groq_explanation"] = groq_future.result()
            except Exception:
                result["groq_explanation"] = ""
        else:
            result["groq_explanation"] = ""

    return result
