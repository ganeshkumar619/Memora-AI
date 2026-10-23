"""AI provider abstraction for MEMORA AI.

Integrates real language models—primarily Google Gemini (using the official google-genai SDK),
with automatic graceful model fallback (gemini-3.5-flash, gemini-3.5-flash-lite, gemini-3.8-flash, etc.)
and optional OpenAI-compatible endpoints.
API keys are loaded securely from .env and never exposed to the frontend, logs, or responses.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("memora.ai")

# Load .env securely from backend directory and workspace root
try:
    from dotenv import load_dotenv
    _backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(_backend_dir / ".env", override=True)
    load_dotenv(_backend_dir.parent / ".env", override=True)
except Exception:
    pass

DEFAULT_GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
REQUEST_TIMEOUT_SECONDS = 12.0

# Supported candidate models in fallback order
RECOMMENDED_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.1-flash-lite",
]


def sanitize_log(msg: Any) -> str:
    """Never expose API keys in log strings or error messages."""
    s = str(msg)
    s = re.sub(r"(?:key|api_key|token)=[A-Za-z0-9_\-]+", "key=[REDACTED]", s, flags=re.IGNORECASE)
    s = re.sub(r"AIzaSy[A-Za-z0-9_\-]{20,}", "[REDACTED_API_KEY]", s)
    return s


class AIProvider:
    """Base class for chat completion and reasoning providers."""

    name: str = "none"
    model: str = ""
    active_model: str = ""
    last_error: Optional[str] = None

    def available(self) -> bool:
        """True when the provider has valid credentials and is configured."""
        return False

    def verify_connection(self) -> Tuple[bool, Optional[str]]:
        """Verify whether the provider endpoint is currently reachable and responding."""
        return False, "Provider not configured"

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> Optional[str]:
        """Return raw model completion text, or None on failure."""
        return None

    def analyze_and_respond(
        self,
        message: str,
        mode: str,
        memories: List[Dict[str, Any]],
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Understand the user's intent in Tamil, Tanglish, or English."""
        return None

    def get_last_error_message(self) -> Optional[str]:
        if not self.last_error:
            return None
        return sanitize_log(self.last_error)


class GeminiProvider(AIProvider):
    """Google Gemini AI integration using official google-genai SDK with multi-model fallback."""

    name = "gemini"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key.strip()
        self.model = (model or DEFAULT_GEMINI_MODEL).strip() or "gemini-2.5-flash"
        self.active_model = self.model
        self.last_error = None
        self._last_verify_time = 0.0
        self._last_verify_result: Tuple[bool, Optional[str]] = (False, None)
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        if not self.api_key:
            return
        try:
            from google import genai
            from google.genai import types
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except Exception as e:
            self.last_error = sanitize_log(str(e))
            self._client = None

    def available(self) -> bool:
        return bool(self.api_key)

    def _get_candidate_models(self) -> List[str]:
        candidates = [self.model]
        for m in RECOMMENDED_FALLBACK_MODELS:
            if m not in candidates:
                candidates.append(m)
        return candidates

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> Optional[str]:
        if not self.available():
            self.last_error = "GEMINI_API_KEY is not configured."
            return None

        from google.genai import types

        config_args: Dict[str, Any] = {
            "temperature": 0.2,
            "max_output_tokens": 1024,
        }
        if system:
            config_args["system_instruction"] = system
        if json_mode:
            config_args["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_args)
        candidate_models = self._get_candidate_models()
        # If active_model is already known to work, prioritize it
        if self.active_model and self.active_model in candidate_models:
            candidate_models.remove(self.active_model)
            candidate_models.insert(0, self.active_model)

        last_err: Optional[Exception] = None
        for model_name in candidate_models:
            try:
                if self._client is None:
                    self._init_client()
                if self._client is None:
                    raise RuntimeError("Failed to initialize Google Gemini client.")

                response = self._client.models.generate_content(
                    model=model_name,
                    contents=user,
                    config=config,
                )
                text = (response.text or "").strip()
                if text:
                    self.active_model = model_name
                    self.last_error = None
                    self._last_verify_result = (True, None)
                    self._last_verify_time = time.time()
                    return text
            except Exception as e:
                last_err = e
                err_str = sanitize_log(str(e))
                logger.warning("Gemini model %s failed: %s", model_name, err_str)
                # If authentication failed (400/401/403 with invalid key), trying other models won't help
                if any(k in err_str.lower() for k in ("api key not valid", "api_key_invalid", "permission denied", "unauthenticated")):
                    self.last_error = f"Authentication error: {err_str}"
                    return None
                # If network connection failed or timed out during connect/handshake, fail fast
                if any(k in err_str.lower() for k in ("connecttimeout", "handshake operation timed out", "connection refused", "failed to establish a new connection")):
                    self.last_error = f"Network connection error: {err_str}"
                    return None

        if last_err is not None:
            self.last_error = sanitize_log(str(last_err))
            self._last_verify_result = (False, self.last_error)
            self._last_verify_time = time.time()
        return None

    def verify_connection(self, force: bool = False) -> Tuple[bool, Optional[str]]:
        if not self.available():
            return False, "GEMINI_API_KEY is not configured."

        now = time.time()
        # Cache connection test result for 60 seconds unless forced
        if not force and (now - self._last_verify_time < 60.0) and self._last_verify_result[0]:
            return self._last_verify_result

        try:
            res = self.complete("", "Ping", json_mode=False)
            if res:
                self._last_verify_result = (True, None)
                self._last_verify_time = now
                return True, None
            msg = self.last_error or "No response from Gemini API."
            self._last_verify_result = (False, msg)
            self._last_verify_time = now
            return False, msg
        except Exception as e:
            msg = sanitize_log(str(e))
            self._last_verify_result = (False, msg)
            self._last_verify_time = now
            return False, msg

    def analyze_and_respond(
        self,
        message: str,
        mode: str,
        memories: List[Dict[str, Any]],
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.available():
            self.last_error = "GEMINI_API_KEY is not configured."
            return None

        # Build context from stored memories
        memories_text = "\n".join(
            f"ID #{m.get('id')}: {m.get('content')} [Category: {m.get('category', 'general')}]"
            for m in memories[:40]
        ) or "(No memories saved in SQLite yet)"

        history_text = "\n".join(
            f"{h.get('role', 'user')}: {h.get('text', '')}"
            for h in (recent_history or [])[-6:]
        ) or "(No previous messages)"

        system_prompt = (
            "You are MEMORA AI, an intelligent personal voice-memory assistant.\n"
            "You understand conversational Tamil (தமிழ்), Tanglish (Tamil spoken/written using English letters), and Indian English naturally.\n"
            "You have direct access to the user's persistent SQLite memory database.\n\n"
            "CRITICAL LANGUAGE RULE:\n"
            "Reply in the EXACT SAME language and conversational style the user used:\n"
            "- If user speaks/types Tanglish (e.g. 'Machi, en peru Ganesh...', 'En peru enna?', 'En project deadline eppo?'):\n"
            "  Reply in natural, friendly, conversational Tanglish (simple Tamil words written in English letters).\n"
            "  Example acknowledgement: 'Kandippa Ganesh! Neenga II Year CSE student nu nyabagam vachikitten.'\n"
            "  Example recall: 'Un peru Ganesh, nee II Year CSE student.'\n"
            "- If user speaks/types pure Tamil (Tamil script):\n"
            "  Reply in natural Tamil script. Example: 'கண்டிப்பாக! உங்கள் தகவலை நினைவில் குறித்துக்கொண்டேன்.'\n"
            "- If user speaks/types English:\n"
            "  Reply in natural English. Example: 'Got it! I have remembered your details.'\n"
            "Keep replies concise, clear, and voice-friendly (1-2 sentences).\n\n"
            "REAL MEMORY RULES:\n"
            "1. SAVE INTENT: If user states personal facts or asks to remember/save anything\n"
            "   (e.g., 'Machi, en peru Ganesh. Naan II Year CSE student. Idha remember panniko', '... nu nyabagam vachiko', 'remember that...'):\n"
            "   - action: 'save'\n"
            "   - memory_content: clean factual statement without conversational fillers (e.g. 'Name: Ganesh, II Year CSE student')\n"
            "   - category: 'personal' (or 'project', 'work', 'deadline', 'preference', etc.)\n"
            "   - reply: warm, natural conversational acknowledgment in matching language\n"
            "2. RECALL INTENT: If user asks a question about saved memories or previous information\n"
            "   (e.g., 'En peru enna? Naan endha year padikkiren?', 'En project deadline eppo?', 'Where are my keys?'):\n"
            "   - Answer the question directly and concisely using ONLY the SAVED MEMORIES or RECENT CONVERSATION.\n"
            "   - Example: If memory has 'Name: Ganesh, II Year CSE student' and question is 'En peru enna? Naan endha year padikkiren?',\n"
            "     answer: 'Un peru Ganesh, nee II Year CSE student.'\n"
            "   - CRITICAL: Do NOT merely repeat or echo the original saved message. Extract the specific facts to answer the question asked!\n"
            "   - If no relevant memory exists, state clearly in the user's language that you do not have that saved yet (e.g. 'Andha thagaval en kitta save aagala.').\n"
            "   - NEVER invent or hallucinate facts that are not saved!\n"
            "   - action: 'none'\n"
            "3. LIST INTENT: If user asks what you remember (e.g. 'Enna nyabagam vechiruka?', 'What do you remember?'):\n"
            "   - Summarize or list their memories in their language. action: 'none'\n"
            "4. DELETE INTENT: If user asks to delete/forget a memory:\n"
            "   - action: 'delete', target_id: ID of the matching memory from the list.\n"
            "5. CHAT/GENERAL: If conversational greetings, reply warmly in their language. action: 'none'\n\n"
            "You MUST output valid JSON matching this exact schema:\n"
            "{\n"
            '  "intent": "save_memory" | "recall" | "list_memories" | "delete_memory" | "greeting" | "chat",\n'
            '  "reply": "assistant conversational response string in matching language/style",\n'
            '  "action": "save" | "delete" | "none",\n'
            '  "memory_content": "factual statement to save or null",\n'
            '  "category": "category name or null",\n'
            '  "target_id": integer memory id to delete or null,\n'
            '  "detected_language": "tanglish" | "tamil" | "english"\n'
            "}"
        )

        user_content = (
            f"SAVED MEMORIES IN SQLITE:\n{memories_text}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_text}\n\n"
            f"USER INPUT (Language mode selected: {mode}):\n{message}"
        )

        raw = self.complete(system_prompt, user_content, json_mode=True)
        if not raw:
            return None

        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned.strip())
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "reply" in parsed:
                return parsed
        except Exception as e:
            self.last_error = f"Invalid JSON from Gemini: {sanitize_log(str(e))}"

        return None


class OpenAICompatibleProvider(AIProvider):
    """Talks to any OpenAI-compatible completions endpoint."""

    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.active_model = self.model
        self.last_error = None

    def available(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def verify_connection(self) -> Tuple[bool, Optional[str]]:
        if not self.available():
            return False, "OpenAI-compatible credentials not configured"
        res = self.complete("Say hi", "Ping", json_mode=False)
        if res:
            return True, None
        return False, self.last_error or "OpenAI endpoint failed"

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> Optional[str]:
        if not self.available():
            return None
        import urllib.request
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
            choices = body.get("choices") or []
            if not choices:
                return None
            msg = choices[0].get("message") or {}
            self.last_error = None
            return (msg.get("content") or "").strip() or None
        except Exception as e:
            self.last_error = sanitize_log(str(e))
            return None

    def analyze_and_respond(
        self,
        message: str,
        mode: str,
        memories: List[Dict[str, Any]],
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        memories_text = "\n".join(
            f"ID #{m.get('id')}: {m.get('content')} [Category: {m.get('category', 'general')}]"
            for m in memories[:40]
        ) or "(No memories saved in SQLite yet)"

        system_prompt = (
            "You are MEMORA AI, an intelligent personal voice-memory assistant. Output JSON with fields: "
            "intent, reply, action, memory_content, category, target_id, detected_language."
        )
        user_content = f"Saved memories:\n{memories_text}\nUser input: {message}"
        raw = self.complete(system_prompt, user_content, json_mode=True)
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "reply" in parsed:
                    return parsed
            except Exception as e:
                self.last_error = sanitize_log(str(e))
        return None


# Global singleton provider instance
_provider_instance: Optional[AIProvider] = None


def get_provider() -> Optional[AIProvider]:
    """Return the active AI provider configured via environment variables.

    Prioritizes Google Gemini (GEMINI_API_KEY, GOOGLE_API_KEY),
    followed by generic AI_API_KEY with AI_PROVIDER=gemini or openai-compatible.
    """
    global _provider_instance
    gemini_key = (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    provider_name = os.getenv("AI_PROVIDER", "").strip().lower()

    if gemini_key or provider_name in ("gemini", "google", "google-gemini"):
        key = gemini_key or os.getenv("AI_API_KEY", "").strip()
        if key:
            model = os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL") or DEFAULT_GEMINI_MODEL
            if _provider_instance is None or not isinstance(_provider_instance, GeminiProvider) or _provider_instance.api_key != key:
                _provider_instance = GeminiProvider(api_key=key, model=model)
            return _provider_instance

    generic_key = os.getenv("AI_API_KEY", "").strip()
    if provider_name in ("openai", "openai-compatible", "openai_compatible", "oai") and generic_key:
        base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("AI_MODEL", "gpt-4o-mini").strip()
        if _provider_instance is None or not isinstance(_provider_instance, OpenAICompatibleProvider) or _provider_instance.api_key != generic_key:
            _provider_instance = OpenAICompatibleProvider(base_url=base_url, api_key=generic_key, model=model)
        return _provider_instance

    _provider_instance = None
    return None


def provider_status(check_live: bool = False) -> Dict[str, Any]:
    """Report the active AI provider status for /api/health and frontend settings.

    Never exposes API keys or secrets.
    """
    provider = get_provider()
    if provider and provider.available():
        connected = True
        error_msg = provider.get_last_error_message()
        if error_msg:
            connected = False

        if check_live:
            ok, err = provider.verify_connection()
            connected = ok
            if err:
                error_msg = err

        active_mod = getattr(provider, "active_model", provider.model) or provider.model
        return {
            "ai_provider": provider.name,
            "ai_model": active_mod,
            "configured_model": provider.model,
            "mode": "ai-assisted" if connected else "ai-error",
            "connected": connected,
            "error": error_msg,
            "message": (
                f"Connected to {provider.name.capitalize()} ({active_mod})"
                if connected
                else f"{provider.name.capitalize()} error: {error_msg}"
            ),
            "setup_guide": None,
        }

    return {
        "ai_provider": "none",
        "ai_model": "local-rule-engine",
        "configured_model": None,
        "mode": "local-fallback",
        "connected": False,
        "error": None,
        "message": "Local memory mode. To enable Google Gemini AI, configure GEMINI_API_KEY in backend/.env.",
        "setup_guide": (
            "Windows Setup Instructions:\n"
            "1. Open PowerShell or Command Prompt in the backend folder.\n"
            "2. Run: copy .env.example .env\n"
            "3. Edit .env and enter: GEMINI_API_KEY=your_gemini_api_key\n"
            "4. Get a free API key at: https://aistudio.google.com/\n"
            "5. Restart the MEMORA AI backend (python main.py)."
        ),
    }
