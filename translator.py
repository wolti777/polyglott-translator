import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

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

# API Keys from environment variables
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
PONS_API_SECRET = os.environ.get("PONS_API_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def translate_google(text: str, source: str, target: str) -> str:
    """Google Translate via free API."""
    try:
        if source == target:
            return text
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


def translate_deepl(text: str, source: str, target: str) -> str:
    """DeepL Translation API (official, high quality)."""
    try:
        if source == target:
            return text

        if not DEEPL_API_KEY:
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
            "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}",
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


def translate_pons(text: str, source: str, target: str) -> str:
    """PONS Dictionary API (high quality dictionary lookups)."""
    import re
    import html
    try:
        if source == target:
            return text

        if not PONS_API_SECRET:
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
        # Common pairs: deen, dees, depl, enes, enpl, espl, defr, enfr, deit, deru, denl, deptr
        pair = f"{src}{tgt}"

        # Some pairs need to be reversed (PONS convention)
        valid_pairs = ['deen', 'dees', 'depl', 'enes', 'enpl', 'espl', 'defr', 'enfr',
                       'deit', 'enit', 'esit', 'frit', 'deru', 'enru', 'denl', 'ennl',
                       'dept', 'enpt', 'espt', 'frpt']
        reverse_pair = f"{tgt}{src}"

        if pair not in valid_pairs and reverse_pair in valid_pairs:
            pair = reverse_pair

        url = f"https://api.pons.com/v1/dictionary?l={pair}&q={requests.utils.quote(text)}"
        headers = {"X-Secret": PONS_API_SECRET}

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
                                # Get the first translation of each meaning (the main one)
                                target_html = translations[0].get("target", "")
                                # Check if it's an example (skip examples)
                                source_html = translations[0].get("source", "")
                                if 'class="example"' in source_html:
                                    continue
                                # Remove HTML tags
                                clean = re.sub(r'<[^>]+>', '', target_html)
                                # Decode HTML entities
                                clean = html.unescape(clean)
                                # Remove grammar annotations like "m <-(e)s, ...>" or "f <-, -n>"
                                clean = re.sub(r'\s*[mfn]t?\s*<[^>]*>', '', clean)
                                # Remove trailing gender markers
                                clean = re.sub(r'\s+[fmn]t?\s*$', '', clean)
                                # Remove [or ...] alternatives
                                clean = re.sub(r'\s*\[or\s+[^\]]+\]', '', clean)
                                # Remove style markers like "dated", "inf", "form"
                                clean = re.sub(r'\s*(dated|inf|form)\s*', ' ', clean)
                                # Clean up whitespace
                                clean = ' '.join(clean.split())
                                # Skip phrases and grammar constructs
                                if 'sb' in clean or 'sth' in clean:
                                    continue
                                if 'jdn' in clean or 'etw' in clean or 'dat' in clean or 'akk' in clean:
                                    continue
                                if clean.startswith("to ") and len(clean) > 15:
                                    continue
                                if clean.startswith("sich "):
                                    continue
                                # Add if not seen, not empty, and reasonable length
                                if clean and clean.lower() not in seen and len(clean) < 25:
                                    seen.add(clean.lower())
                                    all_translations.append(clean)

                if all_translations:
                    # Return all unique translations separated by comma
                    return ", ".join(all_translations[:8])  # Limit to 8 alternatives
        elif response.status_code == 429:
            return "[Limit]"
        return "[Error]"
    except Exception:
        return "[Error]"


def get_pons_definition(text: str, lang_code: str) -> str:
    """Get word definition from PONS dictionary in the source language."""
    import re
    import html

    if not PONS_API_SECRET:
        return ""

    try:
        # PONS needs a language pair
        if lang_code == 'de':
            pair = 'deen'
        elif lang_code == 'en':
            pair = 'enes' if lang_code == 'en' else 'deen'
            pair = 'deen'  # English words in DE-EN dictionary
        elif lang_code == 'es':
            pair = 'dees'
        elif lang_code == 'pl':
            pair = 'depl'
        else:
            pair = 'deen'

        url = f"https://api.pons.com/v1/dictionary?l={pair}&q={requests.utils.quote(text)}"
        headers = {"X-Secret": PONS_API_SECRET}

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

                        # Clean headword_full - this contains grammatical info
                        if headword_full:
                            clean_hw = re.sub(r'<[^>]+>', '', headword_full)
                            clean_hw = html.unescape(clean_hw).strip()
                            if wordclass and clean_hw:
                                definitions.append(f"[{wordclass}] {clean_hw}")

                        arabs = rom.get("arabs", [])
                        for arab in arabs[:3]:
                            header = arab.get("header", "")
                            if header:
                                # Header contains context/meaning in source language
                                header = re.sub(r'<[^>]+>', '', header)
                                header = html.unescape(header).strip()
                                # Remove numbering like "1. " or "2. "
                                header = re.sub(r'^\d+\.\s*', '', header)
                                if header and len(header) > 2:
                                    definitions.append(header)

                if definitions:
                    # Return unique definitions
                    unique = []
                    for d in definitions:
                        d = d.strip()
                        # Remove trailing colons
                        d = re.sub(r':$', '', d).strip()
                        if d and len(d) > 2 and d not in unique and len(unique) < 4:
                            unique.append(d)
                    return " • ".join(unique)

        return ""
    except Exception:
        return ""


def get_groq_explanation(text: str, lang_code: str) -> str:
    """Get AI explanation using Groq (LLaMA)."""
    if not GROQ_API_KEY:
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
            "Authorization": f"Bearer {GROQ_API_KEY}",
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
    explanation_services: dict = None
) -> dict:
    """Translate to all target languages using multiple sources in parallel.

    Args:
        text: The text to translate
        source_lang: Source language name (e.g., 'german')
        target_languages: List of target language names (e.g., ['english', 'spanish', 'french'])
        enabled_services: Dict of service names to booleans (e.g., {'DeepL': True, 'PONS': False})
        explanation_services: Dict of explanation services (e.g., {'PONS Definition': True, 'Groq AI': True})
    """

    # Default to german if no source language provided
    if not source_lang or source_lang == "auto":
        source_lang = "german"

    source_code = LANGUAGE_CODES.get(source_lang, "de")

    # Default target languages if not specified
    if target_languages is None:
        target_languages = [lang for lang in ["spanish", "german", "polish", "english"] if lang != source_lang]
    else:
        # Filter out source language from targets
        target_languages = [lang for lang in target_languages if lang != source_lang]

    result = {
        "source_language": source_lang,
        "source_text": text,
        "translations": {}
    }

    all_translators = {
        "DeepL": translate_deepl,
        "PONS": translate_pons,
        "Google": translate_google,
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
            pons_future = executor.submit(get_pons_definition, text, source_code)
        if groq_explanation_enabled:
            groq_future = executor.submit(get_groq_explanation, text, source_code)

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
