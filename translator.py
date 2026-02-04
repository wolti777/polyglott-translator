import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

LANGUAGE_CODES = {
    "spanish": "es",
    "german": "de",
    "polish": "pl",
    "english": "en"
}


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
        "GoogT": translate_google,
        "MyMem": translate_mymemory,
        "Yandex": translate_yandex,
        "Reverso": translate_reverso,
    }

    # Execute translations in parallel
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {}

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

    return result
