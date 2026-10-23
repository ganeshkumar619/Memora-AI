"""Tamil / Tanglish / English language understanding for MEMORA AI.

This module is deterministic and fully offline. It normalises a spoken or typed
transcript, works out which command the user meant and extracts the slots that
the chat handler needs. Nothing here touches the database - persistence stays in
:mod:`app.main`.

Supported vocabulary
---------------------
``tamil``    Tamil written in the Unicode Tamil block.
``tanglish`` Tamil words written with Latin letters ("En project deadline Friday").
``english``  Plain English commands.

Normalisation rules
-------------------
* Only *recognised command phrases* are rewritten, so names, dates and numbers
  are never damaged.
* The original transcript is always preserved and returned to the caller.
* A statement is never treated as a save request - saving needs an explicit
  command or a confirmation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Language identifiers
# --------------------------------------------------------------------------- #

LANG_TAMIL = "tamil"
LANG_TANGLISH = "tanglish"
LANG_ENGLISH = "english"

#: Chat "modes" - the value the frontend sends in ``ChatRequest.language``.
MODE_TAMIL = "ta-IN"
MODE_TANGLISH = "tanglish"
MODE_ENGLISH = "en-IN"

_MODE_ALIASES: Dict[str, str] = {
    "ta-in": MODE_TAMIL,
    "ta": MODE_TAMIL,
    "tamil": MODE_TAMIL,
    "தமிழ்": MODE_TAMIL,
    "tanglish": MODE_TANGLISH,
    "tang": MODE_TANGLISH,
    "tamlish": MODE_TANGLISH,
    "en-in": MODE_ENGLISH,
    "en": MODE_ENGLISH,
    "en-us": MODE_ENGLISH,
    "en-gb": MODE_ENGLISH,
    "english": MODE_ENGLISH,
}

#: Unicode block for Tamil (plus the zero-width joiners used in Tamil text).
TAMIL_BLOCK_RE = re.compile(r"[\u0B80-\u0BFF\u200C\u200D]")

#: Latin-script Tamil markers - words that essentially never appear in plain
#: English but are common in Tanglish.
_TANGLISH_MARKERS = frozenset(
    """
    naan nan namma en enna eppo eppoi indru naal ungal ngal unakka ungala
    irukku irukka irukkavalai irundhu illa illai venum vanakkam kelvi
    pannu pannunga pannum pannanum pannava sollu sollra solradhu
    theriyum theriyadhu theriyuma kidaikkum kidadikkum kidaiya
    vechirukka venchirukka veni venunga theerpu thedi thevi
    mattum mele iruppu
    vachiko vechiko vachukko vechuko vechiruka nyabagam ninaivil sonnen sonna sonnadhu
    """.split()
)


def normalize_mode(value: Optional[str]) -> str:
    """Map a frontend supplied language value onto one of the three modes."""
    if not value:
        return MODE_ENGLISH
    key = str(value).strip().lower()
    if key in _MODE_ALIASES:
        return _MODE_ALIASES[key]
    if key in (MODE_TAMIL, MODE_TANGLISH, MODE_ENGLISH):
        return key
    return MODE_ENGLISH


def mode_to_language(mode: str) -> str:
    """Map a chat mode onto the script the reply should be written in."""
    return {
        MODE_TAMIL: LANG_TAMIL,
        MODE_TANGLISH: LANG_TANGLISH,
        MODE_ENGLISH: LANG_ENGLISH,
    }.get(normalize_mode(mode), LANG_ENGLISH)


def detect_language(text: str) -> str:
    """Detect whether *text* is Tamil script, Tanglish or English."""
    if not text:
        return LANG_ENGLISH
    norm = unicodedata.normalize("NFC", text)
    if TAMIL_BLOCK_RE.search(norm):
        return LANG_TAMIL
    tokens = set(re.findall(r"[a-z]+", norm.lower()))
    if tokens & _TANGLISH_MARKERS:
        return LANG_TANGLISH
    return LANG_ENGLISH


# --------------------------------------------------------------------------- #
# Command vocabulary
# --------------------------------------------------------------------------- #

#: Command phrases grouped by intent.
PHRASES: Dict[str, List[str]] = {
    "save": [
        # --- Tamil script -------------------------------------------------
        "சேமித்து வைத்து வை",
        "சேமித்து வை",
        "சேமிக்கவும்",
        "சேமியுங்கள்",
        "சேமியவும்",
        "சேமித்து",
        "சேமி",
        "பதிவு செய்து வை",
        "பதிவு செய்",
        "பதிவு செய்யவும்",
        "பதிவு செய்யுங்கள்",
        "பதிவு",
        "நினைவில் வைத்து வை",
        "நினைவில் வை",
        "நினைவில் கொள்",
        "குறிப்பிடு",
        "குறிப்பிடுங்கள்",
        "குறிப்பு எழுது",
        "ஞாப்பி வை",
        "ஞாபகம் வைத்துக்கொள்",
        "ஞாபகம் வச்சுக்கோ",
        "ஞாபகம் வை",
        "நினைவில் வைத்துக்கொள்",
        "நினைவில் வச்சுக்கோ",
        # --- Tanglish -----------------------------------------------------
        "nu nyabagam vachiko",
        "nu nyabagam vechuko",
        "nu nyabagam vachukko",
        "nu nyabagam vechiko",
        "nu nyabagam vechikonga",
        "nu nyabagam vachikonga",
        "nyabagam vachiko",
        "nyabagam vechuko",
        "nyabagam vachukko",
        "nyabagam vechiko",
        "nyabagam vechikonga",
        "nyabagam vachikonga",
        "ninaivil vechuko",
        "ninaivil vachiko",
        "save pannu pannunga",
        "save pannu",
        "save pannunga",
        "save pannum",
        "save pannanum",
        "save karthu",
        "save it",
        "save this",
        "save that",
        "save",
        "remember pannu",
        "remember pannunga",
        "remember it",
        "remember this",
        "remember that",
        "remember",
        "note down",
        "note it down",
        "take a note of",
        "take a note",
        "make a note of",
        "note pannu",
        "note it",
        "note that",
        "record pannu",
        "record this",
        "store it",
        "store this",
        "store pannu",
    ],
    "list": [
        # --- Tamil script -------------------------------------------------
        "என்ன சேமித்துள்ளது",
        "என்ன விட்டுள்ளது",
        "என்ன தெரியும்",
        "எனக்கு என்ன தெரியும்",
        "என்ன நினைவிருக்கு",
        "என்ன நினைவு",
        "என்ன நினைவுகள்",
        "என்ன நினைவுகளும்",
        "நினைவுகள் என்ன",
        "நினைவு என்ன",
        "எல்லா நினைவும்",
        "என்ன இருக்கு",
        "என்ன இருந்தது",
        "பட்டியல்",
        "காட்டு",
        "காட்டுங்கள்",
        "காண்",
        # --- Tanglish -----------------------------------------------------
        "enna nyabagam vechiruka",
        "enna nyabagam irukku",
        "enna nyabagam irukka",
        "enna nyabagam vechirukke",
        "enna theriyum",
        "enna theriyadhu",
        "en memories enna irukku",
        "en memories enna",
        "en memory enna",
        "enaku theriyadhu",
        "eppo enna irukku",
        "enna irukku",
        "enna solradhu",
        "ena pathu",
        "ammaipadi",
        # --- English ------------------------------------------------------
        "what do you remember",
        "what have you remembered",
        "show my memories",
        "show all my memories",
        "list my memories",
        "list memories",
        "my saved memories",
        "show me everything you remember",
        "what do you know about me",
    ],
    "search": [
        # --- Tamil script -------------------------------------------------
        "தேடித்தர",
        "தேடி வழங்கு",
        "தேடு",
        "தேடுங்கள்",
        "கிடைக்குமா",
        "கிடைக்கும்",
        "எங்கே",
        # --- Tanglish -----------------------------------------------------
        "kidadikkum",
        "kidaikkum",
        "kidaiya",
        "thevi",
        "thedi",
        "vela sollanum",
        "eppo enna sollithe",
        "enna sollithe",
        # --- English ------------------------------------------------------
        "search my memories for",
        "search memories for",
        "look up",
        "where do i find",
        "where is",
        "search",
        "find",
    ],
    "delete": [
        # --- Tamil script -------------------------------------------------
        "நீக்கிடவும்",
        "நீக்கவும்",
        "நீக்குங்கள்",
        "நீக்கு",
        "நீக்கி",
        "அழி",
        "தள்ளி வை",
        # --- Tanglish -----------------------------------------------------
        "delete pannu",
        "delete pannunga",
        "delete pannum",
        "delete pannu pannunga",
        "remove pannu",
        "delete",
        "remove",
        "erase",
        # --- English ------------------------------------------------------
        "delete this",
        "delete that",
        "delete",
        "remove",
        "forget",
    ],
    "edit": [
        # --- Tamil script -------------------------------------------------
        "மாற்றித் தர",
        "மாற்று",
        "திருத்து",
        # --- Tanglish -----------------------------------------------------
        "edit pannu",
        "update pannu",
        "change pannu",
        # --- English ------------------------------------------------------
        "edit",
        "update",
        "change",
    ],
    "reminder_create": [
        # --- Tamil script -------------------------------------------------
        "நினைவூட்டு",
        "நினைவூட்டு வை",
        "எழுத்தி வை",
        "குறிப்பு வை",
        "தினக் குறிப்பு",
        # --- Tanglish / English -------------------------------------------
        "remind pannu",
        "remind pannunga",
        "reminder veni",
        "reminder vechirukka",
        "remind me to",
        "remind me",
        "set a reminder",
        "create a reminder",
        "add a reminder",
    ],
    "reminder_list": [
        # --- Tamil script -------------------------------------------------
        "என்ன குறிப்புகள்",
        "குறிப்புகள் என்ன",
        "குறிப்பு என்ன",
        "குறிப்புகள் என்னன",
        # --- Tanglish / English -------------------------------------------
        "en reminders enna irukku",
        "reminders enna",
        "enna reminders",
        "reminder list",
        "reminders list",
        "show my reminders",
        "show reminders",
        "list my reminders",
        "list reminders",
        "my reminders",
        "what reminders",
    ],
    "help": [
        "help",
        "உதவி",
        "என்ன செய்ய முடியும்",
        "எப்படி பயன்படுத்த",
        "commands",
        "what can you do",
        "how do i use this",
    ],
    "greeting": [
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
        "how r u",
        "what's up",
        "whats up",
        "vanakkam",
        "வணக்கம்",
        "நமஸ்காரம்",
        "enna nyabagam vechirukka",
        "enna new",
        "eppo enna",
        "eppo enna solla",
        "enna solla",
    ],
    "yes": [
        "yes",
        "yeah",
        "yep",
        "ya",
        "ok",
        "okay",
        "sure",
        "sounds good",
        "go ahead",
        "do it",
        "ஆம்",
        "ஆம் தான்",
        "சரி",
    ],
    "no": [
        "no",
        "nope",
        "nah",
        "cancel",
        "don't save",
        "dont save",
        "வேண்டாம்",
        "வேண்டாம",
    ],
}

#: Whole-message confirmations (the message must be exactly one of these).
YES_EXACT = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "ya",
        "ok",
        "okay",
        "sure",
        "sounds good",
        "go ahead",
        "do it",
        "aam",
        "aam thaan",
        "sari",
        "pannu",
        "pannunga",
        "pannum",
        "saami",
        "சரி",
        "ஆம்",
        "ஆம் தான்",
    }
)

#: Whole-message rejections (the message must be exactly one of these).
NO_EXACT = frozenset({"no", "nope", "nah", "cancel", "thevai", "வேண்டாம்", "வேண்டாம"})

#: Words that signal a *reminder* command (used together with list phrases).
REMINDER_WORDS = (
    "reminder",
    "reminders",
    "remind",
    "குறிப்பு",
    "குறிப்புகள்",
    "குறிப்புகளை",
    "நினைவூட்டு",
)

#: Phrases that only make sense as a *reference* to one specific memory.
GENERIC_TARGET_WORDS = (
    "memory",
    "memories",
    "ithu",
    "intha",
    "idha",
    "idhu",
    "that",
    "this",
    "it",
    "one",
    "my",
    "our",
    "all",
    "oruthu",
    "இது",
    "இந்த",
    "அதை",
    "அந்த",
    "நினைவு",
    "நினைவை",
    "நினைவுகள்",
    "நினைவுகளை",
    "குறிப்பு",
    "குறிப்புகள்",
    "எல்லா",
)

#: Leading filler words that carry no meaning for the stored memory.
_LEADING_FILLERS = (
    "naan sonna",
    "naan sollra",
    "naan solradhu",
    "namma solradhu",
    "naan",
    "namma",
    "aval",
    "avvan",
    "unga",
    "anga",
    "en",
    "na",
    "nan",
    "please",
    "pls",
    "kindly",
    "vachi",
)

#: English filler words.  ``my`` is deliberately *not* listed so that the
#: stored memory keeps the wording the user actually used.
_ENGLISH_LEADING_FILLERS = ("i want to", "i want", "i need to", "i need", "i", "me", "that")

#: Words used to point back at something already said.
_REFERENTIAL_WORDS = (
    "naan sonna",
    "sonna",
    "sollra",
    "solradhu",
    "solliya",
    "sollina",
    "மேலே சொன்ன",
    "சொன்ன",
)

#: Words that introduce the subject of a delete/search command.
_TOPIC_LEADERS = ("about", "regarding", "mentioning", "named", "called")

#: Leading articles that are dropped from an extracted topic.
_ARTICLES = ("the", "a", "an", "my", "our")

#: Relative date words - resolved against the server clock when reporting back.
RELATIVE_DATES = (
    "day after tomorrow",
    "tomorrow morning",
    "tomorrow evening",
    "day after",
    "tomorrow",
    "today",
    "tonight",
    "next week",
    "next month",
    "next year",
    "this week",
    "this month",
    "this evening",
    "this morning",
    # --- Tamil script ---------------------------------------------------
    "நாளை மாலை",
    "நாளை மாலையில்",
    "நாளை",
    "நாளைய",
    "இன்று",
    "இந்நாள்",
    "இப்போது",
    "வரும் வாரம்",
    "அடுத்த வாரம்",
    "அடுத்த மாதம்",
)

#: Weekday names (English + Tamil script).
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "திங்கட்கிழமை",
    "செவ்வாய்க்கிழமை",
    "புதன்கிழமை",
    "வியாழக்கிழமை",
    "வெள்ளிக்கிழமை",
    "சனிக்கிழமை",
    "ஞாயிற்றுக்கிழமை",
)

#: Canonical token each intent is rewritten to when normalising.
CANONICAL: Dict[str, str] = {
    "save": "save",
    "list": "show",
    "search": "find",
    "delete": "delete",
    "edit": "edit",
    "reminder_create": "remind",
    "reminder_list": "show reminders",
    "help": "help",
    "greeting": "greeting",
    "yes": "yes",
    "no": "no",
}

#: Matching order.  Earlier entries win.
_PRIORITY: Tuple[str, ...] = (
    "help",
    "reminder_list",
    "reminder_create",
    "delete",
    "edit",
    "list",
    "search",
    "save",
    "greeting",
)

#: Openers that make a sentence a question even without a question mark.
_QUESTION_STARTERS = (
    "what",
    "who",
    "when",
    "where",
    "why",
    "how",
    "which",
    "is ",
    "are ",
    "do ",
    "does ",
    "did ",
    "can ",
    "could",
    "should",
    "would",
    "will ",
    "tell me",
    "enna",
    "enaku",
    "eppo",
    "kaagitha",
    "theriyuma",
    "yennal",
)

#: Tamil question words.  They can sit anywhere in the sentence, so they are
#: matched with word boundaries instead of a plain ``startswith`` check.
#: ``என்ன`` must not match the possessive ``என்னது`` - the trailing word
#: boundary takes care of that.
_TAMIL_QUESTION_WORDS = (
    "என்ன",
    "எது",
    "எப்படி",
    "யார்",
    "எங்கே",
    "எப்போது",
    "ஏன்",
    "தெரியுமா",
    "தெரிய",
    "சொல்லு",
    "சொல்ல",
    "விளக்கு",
    "கூறு",
)

#: Words that carry no topic meaning inside a question.  They are removed
#: before the remaining words are used as a search key.
_QUESTION_NOISE_WORDS = frozenset(
    """
    what whats which who whom whose when where why how
    is are was were am do does did can could should would will shall may might
    you your yours me my mine i we our us tell please again about know remember
    recall say said there here that this the a an of in on for to and or give
    show list ur pls kindly now also any some much many exactly actually but
    so if then than as at by with from up out all both each few more most other
    such only own same too very just
    enna enaku eppo theriyuma theriyum theriyadhu sollu sollunga solla sollirukka
    naan namma unga unna yennal kaagitha mele vachi irukku irukka illai thevai
    nu sonnen sonna sonnadhu vechiruka vechirukken vachiko nyabagam ninaivil eppoi enga yenga yaar yaaru edhu
    என் எனது என்னது என்ன எது எப்படி யார் எங்கே எப்போது ஏன்
    தெரியுமா தெரிய சொல்ல சொல்லு சொல்லுங்கள் பற்றி ஆக இது அது
    நான் நீ உங்கள் எனக்கு எனக்குச் கூறு கூறிய விளக்கு என்னை என்னைப்
    சொன்னேன் சொன்னது ஞாபகம் நினைவு
    பல எல்லா
    """.split()
)



# --------------------------------------------------------------------------- #
# Phrase matching
# --------------------------------------------------------------------------- #


def split_words(text: str) -> List[str]:
    """Split *text* into words, keeping combining marks with their base letter.

    Tamil writes the "pulli" (U+0BCD) as a separate combining character, so a
    plain ``\\w+`` regex breaks ``இந்த`` into three meaningless pieces.  This
    tokenizer keeps every combining mark attached to the letter in front of it.
    """
    words: List[str] = []
    current: List[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("M"):
            if current:
                current.append(char)
            continue
        if char.isalnum() or char == "_":
            current.append(char)
            continue
        if current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _phrase_body(phrase: str) -> str:
    """Build a whitespace tolerant regex body for *phrase*."""
    return r"\s+".join(re.escape(part) for part in phrase.split())


def _compile_group(phrases: Sequence[str]) -> List[re.Pattern]:
    """Compile one regex per phrase so the matched phrase can be identified."""
    return [
        re.compile(r"(?<![\w])" + _phrase_body(phrase) + r"(?![\w])", re.IGNORECASE)
        for phrase in phrases
    ]


_GROUP_PATTERNS: Dict[str, List[re.Pattern]] = {
    intent: _compile_group(phrases) for intent, phrases in PHRASES.items()
}

# Combined pattern used for canonicalisation.  Longer phrases come first so the
# longest possible command phrase wins at any given position.
_ALL_PHRASES: List[Tuple[str, str]] = sorted(
    ((phrase, intent) for intent, phrases in PHRASES.items() for phrase in phrases),
    key=lambda item: len(item[0]),
    reverse=True,
)
_CANONICAL_PATTERN = re.compile(
    "|".join(
        "(?P<g%d>%s)" % (index, r"(?<![\w])" + _phrase_body(phrase) + r"(?![\w])")
        for index, (phrase, _intent) in enumerate(_ALL_PHRASES)
    ),
    re.IGNORECASE,
)
_GROUP_BY_INDEX = {index: intent for index, (_phrase, intent) in enumerate(_ALL_PHRASES)}


def _find_matches(text: str, intent: str) -> List[re.Match]:
    matches: List[re.Match] = []
    for pattern in _GROUP_PATTERNS[intent]:
        matches.extend(pattern.finditer(text))
    matches.sort(key=lambda m: m.start())
    return matches


def _contains(text: str, intent: str) -> bool:
    return bool(_find_matches(text, intent))


def _remove_matches(text: str, intents: Sequence[str]) -> str:
    """Remove every phrase belonging to *intents* from *text*."""
    spans: List[Tuple[int, int]] = []
    for intent in intents:
        spans.extend((m.start(), m.end()) for m in _find_matches(text, intent))
    if not spans:
        return text
    # Longest match wins when several phrases start at the same position.
    spans.sort(key=lambda span: (span[0], -span[1]))
    out: List[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return " ".join(part.strip() for part in out if part.strip())


def canonicalize(text: str) -> str:
    """Rewrite recognised command phrases into canonical English keywords.

    Everything that is *not* a command phrase is preserved byte for byte, so
    names, dates and numbers survive untouched.
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)

    def _replace(match: re.Match) -> str:
        for name, value in match.groupdict().items():
            if value is not None:
                intent = _GROUP_BY_INDEX.get(int(name[1:]))
                return CANONICAL.get(intent or "", value)
        return match.group(0)

    return re.sub(r"\s+", " ", _CANONICAL_PATTERN.sub(_replace, norm)).strip()


# --------------------------------------------------------------------------- #
# Slot extraction helpers
# --------------------------------------------------------------------------- #


def _strip_punctuation(text: str) -> str:
    return text.strip().strip(" \t\n.,;:!?-–—\"'“”‘’()[]")


def _strip_leading_fillers(text: str, language: str) -> str:
    """Remove leading filler words such as "naan" / "en" / "i"."""
    result = text.strip()
    changed = True
    while changed and result:
        changed = False
        candidates = list(_LEADING_FILLERS)
        if language == LANG_ENGLISH:
            candidates = list(_ENGLISH_LEADING_FILLERS) + candidates
        for filler in candidates:
            pattern = re.compile(r"(?<![\w])" + re.escape(filler) + r"(?![\w])", re.IGNORECASE)
            match = pattern.match(result)
            if match and result[match.end():].strip():
                result = result[match.end():].strip()
                changed = True
                break
        if changed:
            continue
        # Drop a leading "sonna" style reference to something already said.
        for word in _REFERENTIAL_WORDS:
            pattern = re.compile(r"(?<![\w])" + re.escape(word) + r"(?![\w])", re.IGNORECASE)
            match = pattern.match(result)
            if match and result[match.end():].strip():
                result = result[match.end():].strip()
                changed = True
                break
    return result.strip()


def _strip_articles(text: str) -> str:
    result = text.strip()
    changed = True
    while changed and result:
        changed = False
        for article in _ARTICLES:
            pattern = re.compile(r"(?<![\w])" + re.escape(article) + r"(?![\w])", re.IGNORECASE)
            match = pattern.match(result)
            if match and result[match.end():].strip():
                result = result[match.end():].strip()
                changed = True
                break
    return result.strip()


def _drop_topic_leaders(text: str) -> str:
    for leader in _TOPIC_LEADERS:
        text = re.sub(
            r"(?<![\w])" + re.escape(leader) + r"(?![\w])", " ", text, flags=re.IGNORECASE
        )
    return re.sub(r"\s+", " ", text).strip()


def extract_save_content(text: str, language: str = LANG_ENGLISH) -> str:
    """Extract the fact that should be stored for a save command."""
    body = _remove_matches(text, ("save",))
    body = _strip_leading_fillers(body, language)
    body = _strip_punctuation(body)
    # Strip trailing colloquial markers such as "nu", "endru", "ena"
    body = re.sub(r"(?:\s+|^)nu\s*$", "", body, flags=re.IGNORECASE)
    body = re.sub(r"(?:\s+|^)(?:என்று|என)\s*$", "", body)
    return _strip_punctuation(body)


def extract_search_query(text: str, language: str = LANG_ENGLISH) -> str:
    """Extract the search term from a find/search command."""
    body = _remove_matches(text, ("search",))
    body = _remove_matches(body, ("list",))
    body = _strip_leading_fillers(body, language)
    body = body.replace("?", " ").replace("!", " ")
    body = re.sub(r"\s+", " ", body).strip()
    return _strip_punctuation(body)


def extract_delete_target(text: str, language: str = LANG_ENGLISH) -> str:
    """Extract which memory the user wants removed."""
    body = _remove_matches(text, ("delete",))
    body = _remove_matches(body, ("edit",))
    body = _drop_topic_leaders(body)
    body = _strip_leading_fillers(body, language)
    body = _strip_articles(body)
    body = body.replace("?", " ").replace("!", " ")
    body = re.sub(r"\s+", " ", body).strip()
    return _strip_punctuation(body)


def is_generic_target(target: str) -> bool:
    """True when the target does not identify one specific memory."""
    cleaned = _strip_punctuation(target).lower()
    if not cleaned:
        return True
    words = [word.lower() for word in split_words(cleaned)]
    if not words:
        return True
    return all(word in GENERIC_TARGET_WORDS for word in words)


def extract_memory_id(text: str) -> Optional[int]:
    """Look for an explicit memory id such as ``#3`` or ``memory 3``."""
    match = re.search(r"#\s*(\d+)", text)
    if not match:
        match = re.search(r"\b(?:memory|memories|id)\s*(\d+)\b", text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def detect_relative_date(text: str) -> Optional[str]:
    """Return the relative date phrase contained in *text* (if any)."""
    lowered = text.lower()
    for phrase in sorted(RELATIVE_DATES, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", lowered):
            return phrase
    return None


def detect_date_phrase(text: str) -> Optional[str]:
    """Return a weekday / relative date mentioned in *text* (if any)."""
    lowered = text.lower()
    relative = detect_relative_date(lowered)
    if relative:
        return relative
    for day in sorted(WEEKDAYS, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(day) + r"(?![\w])", lowered):
            return day
    match = re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", text)
    if match:
        return match.group(0)
    return None


def has_ambiguous_numeric_date(text: str) -> bool:
    """True for dates such as ``05/11`` where day and month can be swapped."""
    return bool(re.search(r"(?<![\w])\d{1,2}/\d{1,2}(?![\w/])", text))


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #


@dataclass
class Analysis:
    """Result of understanding one user utterance."""

    intent: str = "unknown"
    language: str = LANG_ENGLISH
    mode: str = MODE_ENGLISH
    original: str = ""
    normalized: str = ""
    content: str = ""
    query: str = ""
    target: str = ""
    title: str = ""
    due: str = ""
    is_question: bool = False
    needs_clarification: bool = False
    clarification: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.intent == "empty"


def _looks_like_reminder_command(text: str) -> bool:
    lowered = text.lower()
    for word in REMINDER_WORDS:
        if re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", lowered):
            return True
    return False


def _is_question(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered.endswith("?"):
        return True
    if lowered.startswith(_QUESTION_STARTERS):
        return True
    # Tamil question words may appear anywhere in the sentence, for example
    # "என் பெயர் என்ன" (what is my name).
    for word in _TAMIL_QUESTION_WORDS:
        if re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", lowered):
            return True
    return False


def extract_question_topic(text: str, language: str = LANG_ENGLISH) -> str:
    """Return the topic of a question with the question words removed.

    ``"What is my project deadline?"`` becomes ``"project deadline"`` and
    ``"என் பெயர் என்ன?"`` becomes ``"பெயர்"``.  The result is used as a search
    key against the real database rows - it is never invented content.
    """
    body = _strip_punctuation(text)
    body = body.replace("?", " ").replace("!", " ")
    kept: List[str] = []
    for token in re.split(r"\s+", body):
        clean = _strip_punctuation(token)
        if not clean:
            continue
        if clean.lower() in _QUESTION_NOISE_WORDS:
            continue
        kept.append(clean)
    return " ".join(kept).strip()



def analyze(text: str, mode: str = MODE_ENGLISH) -> Analysis:
    """Understand *text* and return the detected intent plus extracted slots."""
    original = (text or "").strip()
    mode = normalize_mode(mode)
    if not original:
        return Analysis(intent="empty", mode=mode, original="", normalized="")

    norm = unicodedata.normalize("NFC", original)
    norm = re.sub(r"[ \t]+", " ", norm)
    language = detect_language(norm)
    is_question = _is_question(norm)

    analysis = Analysis(
        intent="statement",
        language=language,
        mode=mode,
        original=original,
        normalized=canonicalize(norm),
        is_question=is_question,
    )

    # --- pick the intent ---------------------------------------------------
    stripped = _strip_punctuation(norm.lower())
    intent: Optional[str] = None
    if stripped in YES_EXACT:
        intent = "yes"
    elif stripped in NO_EXACT:
        intent = "no"
    else:
        for candidate in _PRIORITY:
            if candidate == "reminder_list":
                if _looks_like_reminder_command(norm) and (
                    _contains(norm, "reminder_list") or _contains(norm, "list")
                ):
                    intent = candidate
                    break
                continue
            if _contains(norm, candidate):
                intent = candidate
                break

    if intent is None:
        intent = "statement"

    analysis.intent = intent

    # --- extract the slots -------------------------------------------------
    if intent == "save":
        analysis.content = extract_save_content(norm, language)
        if not analysis.content:
            analysis.needs_clarification = True
            analysis.clarification = "empty_content"
        elif has_ambiguous_numeric_date(analysis.content):
            analysis.needs_clarification = True
            analysis.clarification = "ambiguous_date"
        else:
            relative = detect_relative_date(analysis.content)
            if relative:
                analysis.notes.append("relative_date:%s" % relative)
    elif intent == "search":
        analysis.query = extract_search_query(norm, language)
        if not analysis.query:
            analysis.needs_clarification = True
            analysis.clarification = "empty_query"
    elif intent == "delete":
        analysis.target = extract_delete_target(norm, language)
        if not analysis.target or is_generic_target(analysis.target):
            analysis.needs_clarification = True
            analysis.clarification = "ambiguous_target"
    elif intent == "reminder_create":
        body = _remove_matches(norm, ("reminder_create",))
        body = _strip_leading_fillers(body, language)
        body = re.sub(r"(?<![\w])to(?![\w])", " ", body, flags=re.IGNORECASE)
        body = re.sub(r"(?<![\w])ku(?![\w])", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
        due = detect_date_phrase(body)
        title = body
        if due:
            title = re.sub(
                r"(?<![\w])" + re.escape(due) + r"(?![\w])", " ", body, flags=re.IGNORECASE
            )
            title = re.sub(r"\s+", " ", title).strip()
        analysis.title = _strip_punctuation(title) or _strip_punctuation(body)
        analysis.due = due or ""

    return analysis


def is_confirmation(text: str) -> bool:
    """True when *text* clearly confirms a pending action."""
    return analyze(text).intent == "yes"


def is_negation(text: str) -> bool:
    """True when *text* clearly rejects a pending action."""
    return analyze(text).intent == "no"
