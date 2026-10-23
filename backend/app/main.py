from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import ai
from app import language as lang

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("MEMORA_DB_PATH", os.getenv("MEMORA_DB", str(BASE_DIR / "memora.db"))))


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    """Open a connection, commit on success and always close it."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_text TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session TEXT NOT NULL DEFAULT 'default',
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MEMORA AI API", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

init_db()


def format_memory(row: Any) -> Dict[str, Any]:
    """Ensure both 'content'/'category' and legacy 'text'/'tag' exist."""
    d = dict(row)
    c = d.get("content") or d.get("text") or ""
    cat = d.get("category") or d.get("tag") or "general"
    d["content"] = c
    d["text"] = c
    d["category"] = cat
    d["tag"] = cat
    return d


def rows(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with db() as conn:
        return [format_memory(row) for row in conn.execute(sql, params).fetchall()]


def save_chat_turn(user_msg: str, assistant_reply: str, session: str = "default") -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO chat(session, role, text, created_at) VALUES(?,?,?,?)",
                (session, "user", user_msg, now),
            )
            conn.execute(
                "INSERT INTO chat(session, role, text, created_at) VALUES(?,?,?,?)",
                (session, "assistant", assistant_reply, now),
            )
            conn.commit()
    except Exception:
        pass


def get_chat_history(session: str = "default", limit: int = 10) -> List[Dict[str, Any]]:
    try:
        with db() as conn:
            cur = conn.execute(
                "SELECT role, text, created_at FROM chat WHERE session=? ORDER BY id DESC LIMIT ?",
                (session, limit),
            )
            data = [dict(r) for r in cur.fetchall()]
            return data[::-1]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Request & Response Models
# --------------------------------------------------------------------------- #

class MemoryCreate(BaseModel):
    content: Optional[str] = None
    text: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None

class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    text: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: str = Field(default=lang.MODE_ENGLISH, max_length=20)
    pending_memory: Optional[str] = Field(default=None, max_length=2000)

class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_text: str = Field(default="", max_length=200)

class AskPayload(BaseModel):
    message: str
    session: str = "default"


# --------------------------------------------------------------------------- #
# Status & System Endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    status = ai.provider_status()
    return {
        "status": "ok",
        "app": "MEMORA AI",
        "version": "1.2.0",
        "languages": [lang.MODE_TAMIL, lang.MODE_TANGLISH, lang.MODE_ENGLISH],
        "ai_provider": status["ai_provider"],
        "ai_model": status.get("ai_model", ""),
        "mode": status["mode"],
        "message": status.get("message", ""),
    }


@app.get("/api/languages")
def languages():
    return {
        "languages": [
            {
                "id": lang.MODE_TAMIL,
                "label": "தமிழ்",
                "name": "Tamil (தமிழ்)",
                "recognition": "ta-IN",
                "speech": "ta-IN",
            },
            {
                "id": lang.MODE_TANGLISH,
                "label": "Tanglish",
                "name": "Tanglish (Tamil spoken with English words)",
                "recognition": "ta-IN",
                "speech": "en-IN",
            },
            {
                "id": lang.MODE_ENGLISH,
                "label": "English",
                "name": "English (India)",
                "recognition": "en-IN",
                "speech": "en-IN",
            },
        ],
        "note": (
            "MEMORA AI understands Tamil, Tanglish, and English naturally. "
            "Google Gemini AI Brain generates natural conversational replies in matching language."
        ),
    }


# --------------------------------------------------------------------------- #
# Memory CRUD Endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/memories")
def list_memories(q: Optional[str] = None):
    if q and q.strip():
        term = f"%{q.strip()}%"
        return rows(
            "SELECT * FROM memories WHERE content LIKE ? OR category LIKE ? ORDER BY id DESC",
            (term, term),
        )
    return rows("SELECT * FROM memories ORDER BY id DESC")


@app.post("/api/memories", status_code=201)
def create_memory(payload: MemoryCreate):
    raw_content = (payload.content if payload.content is not None else payload.text) or ""
    content = raw_content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Memory cannot be empty.")
    cat = (payload.category if payload.category is not None else payload.tag) or "general"
    category = cat.strip() or "general"
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO memories(content, category, created_at, updated_at) VALUES(?,?,?,?)",
            (content, category, now, now),
        )
        conn.commit()
        memory_id = cur.lastrowid
    return rows("SELECT * FROM memories WHERE id = ?", (memory_id,))[0]


@app.patch("/api/memories/{memory_id}")
def update_memory(memory_id: int, payload: MemoryUpdate):
    raw_content = (payload.content if payload.content is not None else payload.text) or ""
    content = raw_content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory text cannot be empty.")
    cat = (payload.category if payload.category is not None else payload.tag) or "general"
    category = cat.strip() or "general"
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        cur = conn.execute(
            "UPDATE memories SET content=?, category=?, updated_at=? WHERE id=?",
            (content, category, now, memory_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Memory not found.")
    return rows("SELECT * FROM memories WHERE id = ?", (memory_id,))[0]


@app.put("/api/memories/{memory_id}")
def put_memory(memory_id: int, payload: MemoryUpdate):
    return update_memory(memory_id, payload)


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int):
    with db() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Memory not found.")
    return {"deleted": True, "id": memory_id}


# --------------------------------------------------------------------------- #
# Reminders CRUD Endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/reminders")
def list_reminders():
    return rows("SELECT * FROM reminders ORDER BY id DESC")


@app.post("/api/reminders", status_code=201)
def create_reminder(payload: ReminderCreate):
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO reminders(title, due_text, created_at) VALUES(?,?,?)",
            (payload.title.strip(), payload.due_text.strip(), now),
        )
        conn.commit()
        reminder_id = cur.lastrowid
    return rows("SELECT * FROM reminders WHERE id = ?", (reminder_id,))[0]


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: int):
    with db() as conn:
        cur = conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"deleted": True, "id": reminder_id}


# --------------------------------------------------------------------------- #
# History & Backwards Compatibility
# --------------------------------------------------------------------------- #

@app.get("/api/history")
def history(session: str = "default"):
    return get_chat_history(session=session, limit=40)


@app.post("/api/assistant")
def assistant_compat(payload: AskPayload):
    """Simulated assistant endpoint for legacy scripts/tests."""
    msg = payload.message.strip()
    clean_msg = re.sub(r"^(?:hey |ok )?(?:alexa|memora)\+?[,!]?\s*", "", msg, flags=re.I)
    chat_res = handle_chat(ChatRequest(message=clean_msg, language="en-IN"))
    cards = find_memories(clean_msg)[:5]
    intent = chat_res.get("intent", "chat")
    if chat_res.get("saved"):
        intent = "remember"
    elif "delete" in intent:
        intent = "forget"
    return {
        "reply": chat_res.get("reply", ""),
        "intent": intent,
        "cards": cards,
    }


# --------------------------------------------------------------------------- #
# Reply Catalogue for Local Fallback Mode
# --------------------------------------------------------------------------- #

REPLIES: Dict[str, Dict[str, str]] = {
    "saved": {
        "en-IN": "I saved this to your local memory: “{content}”",
        "ta-IN": "இதை உங்கள் உள்ள நினைவில் சேமித்துவிட்டேன்: “{content}”",
        "tanglish": "Idhai ungal ninaivil save pannitten: “{content}”",
    },
    "confirm_saved": {
        "en-IN": "Saved to your memory: “{content}”",
        "ta-IN": "உங்கள் நினைவில் சேமிக்கப்பட்டது: “{content}”",
        "tanglish": "Ungal ninaivil save pannappattathu: “{content}”",
    },
    "relative_note": {
        "en-IN": "I read “{phrase}” as {resolved}.",
        "ta-IN": "“{phrase}” என்பதை நான் {resolved} எனப் படித்துள்ளேன்.",
        "tanglish": "“{phrase}” nu sonnadha {resolved} nu note pannitten.",
    },
    "empty_content": {
        "en-IN": "What would you like me to remember? Tell me the fact to save.",
        "ta-IN": "நான் என்ன நினைவில் வைக்க வேண்டும்? சேமிக்க வேண்டியதைச் சொல்லுங்கள்.",
        "tanglish": "Naan enna ninaivil vaikka venum? Save panna vendiya vishayatha sollunga.",
    },
    "ask_save": {
        "en-IN": "I heard: “{content}”. Would you like me to save this to your memory? Reply “yes” to save it, or tell me what to do.",
        "ta-IN": "நான் கேட்டது: “{content}”. இதை உங்கள் நினைவில் சேமிக்கவா? சேமிக்க “ஆம்” என்று சொல்லுங்கள்.",
        "tanglish": "Naan kettu: “{content}”. Idhai ungalai ninaivil saamikka va? Saamikka “aam” ennu sollunga.",
    },
    "ambiguous_date": {
        "en-IN": "The date in “{content}” could be read more than one way. Please tell me the exact day and month - I have not saved it yet.",
        "ta-IN": "“{content}” என்று கூறிய தேதியைப் பலவாறு படிக்க முடியும். சரியான நாள் மற்றும் மாதத்தைத் தெரிவிக்கவும் - இன்னும் சேமிக்கவில்லை.",
        "tanglish": "“{content}” date puriyala. Day matrum month theliva sollunga - innum save pannala.",
    },
    "empty_query": {
        "en-IN": "What should I look for? Tell me a word or phrase to search your saved memories.",
        "ta-IN": "நான் எதைத் தேட வேண்டும்? சேமித்த நினைவுகளில் தேட வேண்டிய சொல்லைச் சொல்லுங்கள்.",
        "tanglish": "Naan ethai theda venum? Search panna vendiyatha sollunga.",
    },
    "list_header": {
        "en-IN": "Here is what I remember:",
        "ta-IN": "உங்கள் நினைவில் இருப்பவை:",
        "tanglish": "Ungal ninaivil iruppavai:",
    },
    "empty_memory": {
        "en-IN": "Your memory is empty. Try: “Remember that my project deadline is Friday.”",
        "ta-IN": "உங்கள் நினைவு காலியாக உள்ளது. முயற்சி செய்: “என் ப்ராஜெக்ட் டெட்லைன் வெள்ளி” என்று சேமி.",
        "tanglish": "Ungal memory kaaliyaaga irukku. Try: “En project deadline Friday nu nyabagam vachiko”.",
    },
    "search_found": {
        "en-IN": "I found:",
        "ta-IN": "நான் கண்டுபிடித்தது:",
        "tanglish": "Naan kandupidithathu:",
    },
    "recall_found": {
        "en-IN": "You asked about “{topic}”. Here is what I have saved:",
        "ta-IN": "“{topic}” பற்றி கேட்டீர்கள். சேமித்துள்ளவை இவை:",
        "tanglish": "“{topic}” pathi kettenga. Save panniyulla ninaivu:",
    },
    "recall_none": {
        "en-IN": "I could not find a saved memory about “{topic}”. I only answer from what is really stored, so I won't invent an answer.",
        "ta-IN": "“{topic}” பற்றி சேமிக்கப்பட்ட நினைவை நான் கண்டுபிடிக்க முடியவில்லை. உண்மையாக சேமித்தவற்றையே சொல்வேன், பொய்யான பதிலைச் சொல்ல மாட்டேன்.",
        "tanglish": "“{topic}” pathi endha ninaivum illa. Save pannathai mattumae solluven, poi sollamaatten.",
    },
    "search_none": {
        "en-IN": "I couldn't find a matching saved memory.",
        "ta-IN": "பொருந்திய சேமிக்கப்பட்ட நினைவை நான் கண்டுபிடிக்க முடியவில்லை.",
        "tanglish": "Porundhiya ninaivai kandupidikka mudiyala.",
    },
    "delete_ambiguous": {
        "en-IN": "Which memory should I delete? Reply with the number shown below, or tell me what it contains.",
        "ta-IN": "எந்த நினைவை நீக்க வேண்டும்? கீழே காட்டப்பட்ட எண்ணைச் சொல்லுங்கள்.",
        "tanglish": "Endha ninaiva delete pannanum? Keezhe ulla number sollunga.",
    },
    "delete_none": {
        "en-IN": "I couldn't find a saved memory matching that.",
        "ta-IN": "அதைப் பொருந்திய சேமிக்கப்பட்ட நினைவை நான் கண்டுபிடிக்க முடியவில்லை.",
        "tanglish": "Porundhiya memory edhuvum illa.",
    },
    "delete_done": {
        "en-IN": "Deleted that memory: “{content}”",
        "ta-IN": "அந்த நினைவை நீக்கிவிட்டேன்: “{content}”",
        "tanglish": "Andha memory delete pannitten: “{content}”",
    },
    "reminder_created": {
        "en-IN": "Reminder saved: “{title}”{due}.",
        "ta-IN": "குறிப்பு சேமிக்கப்பட்டது: “{title}”{due}.",
        "tanglish": "Reminder save pannappattathu: “{title}”{due}.",
    },
    "reminder_list_header": {
        "en-IN": "Your reminders:",
        "ta-IN": "உங்கள் குறிப்புகள்:",
        "tanglish": "Ungal reminders:",
    },
    "reminder_none": {
        "en-IN": "You have no reminders yet.",
        "ta-IN": "இன்னும் உங்களிடம் குறிப்புகள் இல்லை.",
        "tanglish": "Innum ungalidam reminders illa.",
    },
    "cancel_saved": {
        "en-IN": "Okay, I did not save anything.",
        "ta-IN": "சரி, நான் ஒன்றும் சேமிக்கவில்லை.",
        "tanglish": "Sari, naan onrum save pannala.",
    },
    "nothing_pending": {
        "en-IN": "There is nothing waiting for confirmation. Tell me what to remember, for example: “Remember that my project deadline is Friday.”",
        "ta-IN": "உறுதிப்படுத்தக்கூடிய ஏதும் இல்லை. நினைவில் வைக்க வேண்டியதைச் சொல்லுங்கள்.",
        "tanglish": "Urudhipadutha edhum illa. Enna save pannanum nu sollunga.",
    },
    "greeting": {
        "en-IN": "Hi! I’m Memora. I can save facts you ask me to remember, find them again and manage your reminders. What would you like to do?",
        "ta-IN": "வணக்கம்! நான் மெமோரா. நீங்கள் சொல்லும் செய்திகளை நினைவில் வைத்து, மீண்டும் தேட உதவுகிறேன். உங்களுக்கு என்ன தேவை?",
        "tanglish": "Vanakkam! Naan Memora. Ungal memories save panna, meendum theda udhavuren. Enna pannanum sollunga?",
    },
    "help": {
        "en-IN": "I can save and search memories, manage reminders, and speak responses. Try: “Remember that my deadline is Friday”.",
        "ta-IN": "நினைவுகளைச் சேமிக்கவும் தேடவும், குறிப்புகளை நிர்வகிக்கவும் முடியும். முயற்சி செய்: “என் டெட்லைன் வெள்ளி” என்று சேமி.",
        "tanglish": "Memories save panna, theda mudiyum. Try: “En project deadline Friday nu nyabagam vachiko”.",
    },
    "fallback_local": {
        "en-IN": "I can help with saved memories and reminders. For example, say “Remember that my project deadline is Friday” or ask “What do you remember?”. Advanced generative AI is not configured in this starter build, so I won't invent an answer.",
        "ta-IN": "சேமிக்கப்பட்ட நினைவுகள் மற்றும் குறிப்புகளில் நான் உதவ முடியும். இந்தப் பதிப்பில் மேம்பட்ட AI இல்லை, ஆகவே நான் பொய்யான பதிலைச் சொல்ல மாட்டேன்.",
        "tanglish": "Save pannappa ninaivugalum kurippugalum naan udavi mudiyum. Intha pothippil AI illai, athukku naan pol padayadhai soll mattai.",
    },
    "fallback_ai_failed": {
        "en-IN": "I could not reach the configured AI provider just now, so I will not guess. I can still save and search your memories.",
        "ta-IN": "அமைக்கப்பட்ட AI வழங்கலை தற்போது அணுக முடியவில்லை, எனவே நான் ஊகிக்க மாட்டேன்.",
        "tanglish": "AI connect aagala, aana ungal local memories save panna matrum theda mudiyum.",
    },
}

LANGUAGE_NAMES = {
    lang.MODE_TAMIL: "Tamil (தமிழ்)",
    lang.MODE_TANGLISH: "Tanglish (Tamil written with English words)",
    lang.MODE_ENGLISH: "English",
}


def reply_text(key: str, mode: str, **kwargs) -> str:
    bundle = REPLIES.get(key)
    if not bundle:
        return key
    template = bundle.get(mode) or bundle.get(lang.MODE_ENGLISH, "")
    if mode == lang.MODE_TANGLISH and template[:1].isalpha() and template[:1].islower():
        template = template[0].upper() + template[1:]
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def resolve_relative_date(phrase: str) -> str:
    today = datetime.now()
    mapping = {
        "day after tomorrow": timedelta(days=2),
        "tomorrow": timedelta(days=1),
        "next week": timedelta(days=7),
        "next month": timedelta(days=30),
        "next year": timedelta(days=365),
        "this week": timedelta(days=0),
        "this month": timedelta(days=0),
        "today": timedelta(days=0),
        "tonight": timedelta(days=0),
        "this morning": timedelta(days=0),
        "this evening": timedelta(days=0),
        "tomorrow morning": timedelta(days=1),
        "tomorrow evening": timedelta(days=1),
        "நாளை": timedelta(days=1),
        "நாளைய": timedelta(days=1),
        "நாளை மாலை": timedelta(days=1),
        "நாளை மாலையில்": timedelta(days=1),
        "இன்று": timedelta(days=0),
        "இந்நாள்": timedelta(days=0),
        "இப்போது": timedelta(days=0),
        "வரும் வாரம்": timedelta(days=7),
        "அடுத்த வாரம்": timedelta(days=7),
        "அடுத்த மாதம்": timedelta(days=30),
    }
    offset = mapping.get(phrase, timedelta(days=0))
    return (today + offset).strftime("%d %b %Y")


def find_memories(term: str) -> List[dict]:
    term = (term or "").strip()
    if not term:
        return []
    items = list_memories(term)
    if items:
        return items
    tokens = [token for token in lang.split_words(term.lower()) if len(token) > 2]
    if not tokens:
        return []
    # Strict AND clause
    clause = " AND ".join(["content LIKE ?"] * len(tokens))
    params = tuple(f"%{token}%" for token in tokens)
    strict = rows(f"SELECT * FROM memories WHERE {clause} ORDER BY id DESC LIMIT 20", params)
    if strict:
        return strict
    # OR ranking clause
    if len(tokens) > 1:
        all_memories = list_memories()
        scored = []
        for mem in all_memories:
            c_low = (mem["content"] + " " + mem["category"]).lower()
            score = sum(1 for tok in tokens if tok in c_low)
            if score > 0:
                scored.append((score, mem))
        scored.sort(key=lambda x: -x[0])
        return [m for s, m in scored[:10]]
    return []


def looks_like_personal_fact(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"(?<![\w])(en|naan|namma|my|our)(?![\w])", lowered):
        return True
    for word in ("என்", "எனது", "என்னது"):
        if re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", lowered):
            return True
    for day in lang.WEEKDAYS:
        if day in lowered:
            return True
    if re.search(r"\d{1,2}[/-]\d{1,2}", text):
        return True
    return False


def chat_response(
    reply: str,
    mode: str,
    intent: str,
    analysis: Optional[lang.Analysis] = None,
    saved: bool = False,
    pending: Optional[dict] = None,
    ai_used: bool = False,
) -> dict:
    return {
        "reply": reply,
        "mode": "ai-assisted" if ai_used else "local-fallback",
        "intent": intent,
        "language": mode,
        "detected_language": analysis.language if analysis else lang.LANG_ENGLISH,
        "saved": saved,
        "pending": pending,
        "normalized": analysis.normalized if analysis else "",
    }


def ai_answer(message: str, mode: str, memories: List[dict]) -> Optional[str]:
    provider = ai.get_provider()
    if provider is None or not provider.available():
        return None
    context = "\n".join(f"- {item['content']}" for item in memories[:40]) or "(no saved memories)"
    system = (
        "You are Memora, a personal memory assistant. Answer the user using ONLY the saved "
        "memories listed below. If the answer is not present in them, say plainly that you do "
        f"not know. Never invent names, dates or records. Reply in {LANGUAGE_NAMES.get(mode, 'English')} "
        "and keep it under 120 words."
    )
    user = f"Saved memories:\n{context}\n\nUser question: {message}"
    try:
        return provider.complete(system, user)
    except Exception:
        return None


def handle_save(analysis: lang.Analysis, mode: str):
    if analysis.needs_clarification and analysis.clarification == "empty_content":
        return chat_response(reply_text("empty_content", mode), mode, "save_memory", analysis)
    if analysis.needs_clarification and analysis.clarification == "ambiguous_date":
        return chat_response(
            reply_text("ambiguous_date", mode, content=analysis.content),
            mode,
            "save_memory",
            analysis,
            pending={"action": "save_memory", "content": analysis.content, "ambiguous": True},
        )
    item = create_memory(MemoryCreate(content=analysis.content, category="personal"))
    reply = reply_text("saved", mode, content=item["content"])
    for note in analysis.notes:
        if note.startswith("relative_date:"):
            phrase = note.split(":", 1)[1]
            reply += " " + reply_text(
                "relative_note", mode, phrase=phrase, resolved=resolve_relative_date(phrase)
            )
    return chat_response(reply, mode, "save_memory", analysis, saved=True)


def handle_delete(analysis: lang.Analysis, mode: str):
    explicit_id = lang.extract_memory_id(analysis.original)
    if explicit_id is not None:
        found = rows("SELECT * FROM memories WHERE id = ?", (explicit_id,))
        if not found:
            return chat_response(reply_text("delete_none", mode), mode, "delete_memory", analysis)
        delete_memory(explicit_id)
        return chat_response(
            reply_text("delete_done", mode, content=found[0]["content"]),
            mode,
            "delete_memory",
            analysis,
        )

    if analysis.needs_clarification:
        items = list_memories()[:10]
        if not items:
            return chat_response(reply_text("empty_memory", mode), mode, "delete_memory", analysis)
        listing = "\n" + "\n".join(f"• #{item['id']} — {item['content']}" for item in items)
        return chat_response(
            reply_text("delete_ambiguous", mode) + listing,
            mode,
            "delete_memory",
            analysis,
            pending={
                "action": "delete_memory",
                "candidates": [{"id": item["id"], "content": item["content"]} for item in items],
            },
        )

    matches = find_memories(analysis.target)
    if not matches:
        return chat_response(reply_text("delete_none", mode), mode, "delete_memory", analysis)
    if len(matches) == 1:
        delete_memory(matches[0]["id"])
        return chat_response(
            reply_text("delete_done", mode, content=matches[0]["content"]),
            mode,
            "delete_memory",
            analysis,
        )
    listing = "\n" + "\n".join(f"• #{item['id']} — {item['content']}" for item in matches[:10])
    return chat_response(
        reply_text("delete_ambiguous", mode) + listing,
        mode,
        "delete_memory",
        analysis,
        pending={
            "action": "delete_memory",
            "candidates": [{"id": item["id"], "content": item["content"]} for item in matches[:10]],
        },
    )


def handle_reminder_create(analysis: lang.Analysis, mode: str):
    title = analysis.title or analysis.content
    if not title:
        return chat_response(reply_text("empty_content", mode), mode, "reminder_create", analysis)
    due = analysis.due or ""
    create_reminder(ReminderCreate(title=title, due_text=due))
    due_suffix = f" ({due})" if due else ""
    return chat_response(
        reply_text("reminder_created", mode, title=title, due=due_suffix),
        mode,
        "reminder_create",
        analysis,
    )


def handle_reminder_list(mode: str, analysis: Optional[lang.Analysis] = None):
    items = list_reminders()
    if not items:
        return chat_response(reply_text("reminder_none", mode), mode, "reminder_list", analysis)
    listing = "\n" + "\n".join(
        f"• {item['title']}" + (f" ({item['due_text']})" if item["due_text"] else "")
        for item in items
    )
    return chat_response(
        reply_text("reminder_list_header", mode) + listing, mode, "reminder_list", analysis
    )


def handle_statement(analysis: lang.Analysis, mode: str, message: str):
    """Handle statement or question under local fallback rules."""
    # Special query: "Naan enna sonnen?" / "What did I say?"
    if re.search(r"\b(?:naan\s+enna\s+sonnen|what\s+did\s+i\s+say|நான்\s+என்ன\s+சொன்னேன்)\b", message, re.I):
        hist = [h for h in get_chat_history(limit=5) if h["role"] == "user"]
        prev_user_msg = hist[-2]["text"] if len(hist) >= 2 else (hist[-1]["text"] if hist else "")
        if prev_user_msg:
            if mode == lang.MODE_TANGLISH:
                reply = f"Kadaisiya neenga sonnadhu: “{prev_user_msg}”"
            elif mode == lang.MODE_TAMIL:
                reply = f"கடைசியாக நீங்கள் கூறியது: “{prev_user_msg}”"
            else:
                reply = f"Earlier you said: “{prev_user_msg}”"
            return chat_response(reply, mode, "recall", analysis)
        mems = list_memories()
        if mems:
            if mode == lang.MODE_TANGLISH:
                reply = f"Ungal memories la irunthu: “{mems[0]['content']}”"
            elif mode == lang.MODE_TAMIL:
                reply = f"உங்கள் நினைவிலிருந்து: “{mems[0]['content']}”"
            else:
                reply = f"From your memories: “{mems[0]['content']}”"
            return chat_response(reply, mode, "recall", analysis)

    # Special query: "Enna nyabagam vechiruka?" / "What have you remembered?"
    if re.search(r"\b(?:enna\s+nyabagam\s+(?:vechiruka|vechirukke|irukku|irukka)|what\s+do\s+you\s+remember)\b", message, re.I):
        items = list_memories()
        if not items:
            return chat_response(reply_text("empty_memory", mode), mode, "list_memories", analysis)
        listing = "\n" + "\n".join(f"• {item['content']}" for item in items[:20])
        return chat_response(
            reply_text("list_header", mode) + listing, mode, "list_memories", analysis
        )

    if not analysis.is_question and looks_like_personal_fact(message):
        content = lang.extract_save_content(message, analysis.language)
        if content:
            return chat_response(
                reply_text("ask_save", mode, content=content),
                mode,
                "statement",
                analysis,
                pending={"action": "save_memory", "content": content},
            )

    if analysis.is_question:
        topic = lang.extract_question_topic(message, analysis.language)
        if topic:
            items = find_memories(topic)
            if items:
                listing = "\n" + "\n".join(f"• {item['content']}" for item in items[:20])
                return chat_response(
                    reply_text("recall_found", mode, topic=topic) + listing,
                    mode,
                    "recall",
                    analysis,
                )
            return chat_response(
                reply_text("recall_none", mode, topic=topic), mode, "recall", analysis
            )
        answered = ai_answer(message, mode, list_memories())
        if answered:
            return chat_response(answered, mode, "question", analysis, ai_used=True)

    provider = ai.get_provider()
    if provider is not None and provider.available():
        return chat_response(
            reply_text("fallback_ai_failed", mode), mode, "statement", analysis
        )
    return chat_response(reply_text("fallback_local", mode), mode, "statement", analysis)


def handle_chat(payload: ChatRequest) -> dict:
    """Understand a message in Tamil, Tanglish or English using Gemini or local rules."""
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    mode = lang.normalize_mode(payload.language)
    analysis = lang.analyze(message, mode)
    pending = (payload.pending_memory or "").strip() or None

    # --- 1. Pending confirmation check ---------------------------------------
    if pending:
        if analysis.intent == "yes" or (analysis.intent == "save" and not analysis.content):
            item = create_memory(MemoryCreate(content=pending, category="personal"))
            res = chat_response(
                reply_text("confirm_saved", mode, content=item["content"]),
                mode,
                "save_memory",
                analysis,
                saved=True,
            )
            save_chat_turn(message, res["reply"])
            return res
        if analysis.intent == "no":
            res = chat_response(reply_text("cancel_saved", mode), mode, "cancel", analysis)
            save_chat_turn(message, res["reply"])
            return res

    # --- 2. Try Google Gemini AI Brain if configured -------------------------
    provider = ai.get_provider()
    if provider is not None and provider.available():
        memories = list_memories()
        history_items = get_chat_history(limit=6)
        ai_result = provider.analyze_and_respond(message, mode, memories, history_items)
        if ai_result and isinstance(ai_result, dict) and ai_result.get("reply"):
            intent = ai_result.get("intent", "chat")
            reply = ai_result["reply"]
            saved = False
            action = (ai_result.get("action") or "none").lower()

            if action == "save" and ai_result.get("memory_content"):
                mem_content = str(ai_result["memory_content"]).strip()
                mem_cat = str(ai_result.get("category") or "personal").strip()
                if mem_content:
                    create_memory(MemoryCreate(content=mem_content, category=mem_cat))
                    saved = True
            elif action == "delete" and ai_result.get("target_id"):
                try:
                    delete_memory(int(ai_result["target_id"]))
                except Exception:
                    pass

            save_chat_turn(message, reply)
            return {
                "reply": reply,
                "mode": "ai-assisted",
                "intent": intent,
                "language": mode,
                "detected_language": ai_result.get("detected_language") or analysis.language,
                "saved": saved,
                "pending": None,
                "normalized": analysis.normalized,
            }

    # --- 3. Deterministic Local Fallback Dispatch ----------------------------
    res: dict
    if analysis.intent == "greeting":
        res = chat_response(reply_text("greeting", mode), mode, "greeting", analysis)
    elif analysis.intent == "help":
        res = chat_response(reply_text("help", mode), mode, "help", analysis)
    elif analysis.intent == "save":
        res = handle_save(analysis, mode)
    elif analysis.intent == "list":
        items = list_memories()
        if not items:
            res = chat_response(reply_text("empty_memory", mode), mode, "list_memories", analysis)
        else:
            listing = "\n" + "\n".join(f"• {item['content']}" for item in items[:20])
            res = chat_response(
                reply_text("list_header", mode) + listing, mode, "list_memories", analysis
            )
    elif analysis.intent == "search":
        if analysis.needs_clarification:
            res = chat_response(reply_text("empty_query", mode), mode, "search_memory", analysis)
        else:
            items = find_memories(analysis.query)
            if not items:
                res = chat_response(reply_text("search_none", mode), mode, "search_memory", analysis)
            else:
                listing = "\n" + "\n".join(f"• {item['content']}" for item in items)
                res = chat_response(
                    reply_text("search_found", mode) + listing, mode, "search_memory", analysis
                )
    elif analysis.intent == "delete":
        res = handle_delete(analysis, mode)
    elif analysis.intent == "reminder_create":
        res = handle_reminder_create(analysis, mode)
    elif analysis.intent == "reminder_list":
        res = handle_reminder_list(mode, analysis)
    elif analysis.intent in ("yes", "no"):
        res = chat_response(reply_text("nothing_pending", mode), mode, analysis.intent, analysis)
    else:
        res = handle_statement(analysis, mode, message)

    save_chat_turn(message, res["reply"])
    return res


def simple_answer(message: str) -> str:
    return handle_chat(ChatRequest(message=message)).get("reply", "")


@app.post("/api/chat")
def chat(payload: ChatRequest):
    return handle_chat(payload)


@app.get("/")
def root():
    return {
        "message": "MEMORA AI API is running. See /docs for interactive API documentation.",
        "version": "1.2.0",
        "health": "/api/health",
        "chat": "/api/chat",
        "memories": "/api/memories",
        "reminders": "/api/reminders",
    }
