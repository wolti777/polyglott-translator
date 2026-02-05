import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

LANGUAGE_CODES = {
    "spanish": "es",
    "german": "de",
    "polish": "pl",
    "english": "en"
}

# API Keys from environment variables
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
PONS_API_SECRET = os.environ.get("PONS_API_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


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
            'pl': 'pol'
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

        # DeepL language codes (uppercase, some special cases)
        lang_map = {
            'de': 'DE',
            'en': 'EN',
            'es': 'ES',
            'pl': 'PL'
        }

        src = lang_map.get(source, 'EN')
        tgt = lang_map.get(target, 'EN')

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
            'pl': 'pl'
        }

        src = lang_map.get(source, 'de')
        tgt = lang_map.get(target, 'en')

        # PONS language pair format (source + target, alphabetically sorted in some cases)
        # Common pairs: deen, dees, depl, enes, enpl, espl
        pair = f"{src}{tgt}"

        # Some pairs need to be reversed (PONS convention)
        valid_pairs = ['deen', 'dees', 'depl', 'enes', 'enpl', 'espl', 'defr', 'enfr']
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
        return "[Error]"
    except Exception:
        return "[Error]"


def get_ai_explanation(text: str, lang_code: str) -> str:
    """Get AI explanation of the word/phrase using Google Gemini."""
    if not GEMINI_API_KEY:
        return ""

    try:
        # Map language codes to full names
        lang_names = {
            'de': 'German',
            'en': 'English',
            'es': 'Spanish',
            'pl': 'Polish'
        }
        lang_name = lang_names.get(lang_code, 'German')

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

        prompt = f"""Erkläre das Wort oder den Ausdruck "{text}" kurz und prägnant auf {lang_name if lang_code != 'de' else 'Deutsch'}.
- Maximal 3-4 Zeilen
- Einfache Sprache
- Keine Aufzählungen, nur Fließtext
- Fokus auf Bedeutung und typische Verwendung"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 150
            }
        }

        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("candidates"):
                content = data["candidates"][0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        elif response.status_code == 429:
            return "[LIMIT] API-Limit erreicht. Bitte später erneut versuchen."

        return ""
    except Exception:
        return ""


def translate_to_all_languages(text: str, source_lang: str = None) -> dict:
    """Translate to all target languages using multiple sources in parallel."""

    # Simple language detection
    if not source_lang or source_lang == "auto":
        text_lower = text.lower()
        if any(w in text_lower for w in ['der', 'die', 'das', 'und', 'ist', 'ein', 'eine', 'für', 'mit']):
            source_lang = "german"
        elif any(w in text_lower for w in ['the', 'is', 'are', 'and', 'of', 'to', 'in', 'for']):
            source_lang = "english"
        elif any(w in text_lower for w in ['el', 'la', 'los', 'las', 'es', 'que', 'por', 'para']):
            source_lang = "spanish"
        elif any(w in text_lower for w in ['jest', 'nie', 'tak', 'się', 'czy', 'jak']):
            source_lang = "polish"
        else:
            source_lang = "german"

    source_code = LANGUAGE_CODES.get(source_lang, "en")
    target_languages = [lang for lang in ["spanish", "german", "polish", "english"] if lang != source_lang]

    result = {
        "source_language": source_lang,
        "source_text": text,
        "translations": {}
    }

    translators = {
        "DeepL": translate_deepl,
        "PONS": translate_pons,
        "Google": translate_google,
        "Lingva": translate_lingva,
    }

    # Execute translations and AI explanation in parallel
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {}

        # Submit AI explanation request
        ai_future = executor.submit(get_ai_explanation, text, source_code)

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

        # Get AI explanation
        try:
            result["ai_explanation"] = ai_future.result()
        except Exception:
            result["ai_explanation"] = ""

    return result
