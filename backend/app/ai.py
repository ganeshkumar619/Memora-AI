"""AI provider abstraction for MEMORA AI.

Integrates real language models—primarily Google Gemini (gemini-2.5-flash / gemini-1.5-flash),
as well as optional OpenAI-compatible endpoints—with secure environment-based configuration.
API keys are loaded securely from .env and never exposed to the frontend or logs.
If the API key is not configured or an API error occurs, MEMORA AI falls back gracefully
to local memory handling with clear notification.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load .env securely from backend directory
try:
    from dotenv import load_dotenv
    _backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(_backend_dir / ".env")
except Exception:
    pass

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_GEMINI_MODEL = "gemini-1.5-flash"
REQUEST_TIMEOUT_SECONDS = 25


class AIProvider:
    """Base class for chat completion and reasoning providers."""

    name: str = "none"
    model: str = ""

    def available(self) -> bool:
        """True when the provider has valid credentials and is configured."""
        return False

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
        """Understand the user's intent in Tamil, Tanglish, or English,

        returning structured data: intent, reply, memory action, and extracted slots.
        """
        return None


class GeminiProvider(AIProvider):
    """Native Google Gemini API integration using official REST endpoint."""

    name = "gemini"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key.strip()
        self.model = (model or DEFAULT_GEMINI_MODEL).strip()

    def available(self) -> bool:
        return bool(self.api_key)

    def _call_gemini_endpoint(
        self,
        model_name: str,
        system_instruction: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> Optional[str]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            f"?key={self.api_key}"
        )
        generation_config: Dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        body: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": generation_config,
        }
        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        payload_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                res_data = json.loads(response.read().decode("utf-8"))
            candidates = res_data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts") or []
            if not parts:
                return None
            return parts[0].get("text", "").strip() or None
        except urllib.error.HTTPError as e:
            # If 404 on newer model, retry with fallback model
            if e.code == 404 and model_name != FALLBACK_GEMINI_MODEL:
                return self._call_gemini_endpoint(
                    FALLBACK_GEMINI_MODEL, system_instruction, user_prompt, json_mode
                )
            return None
        except Exception:
            return None

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> Optional[str]:
        if not self.available():
            return None
        return self._call_gemini_endpoint(self.model, system, user, json_mode)

    def analyze_and_respond(
        self,
        message: str,
        mode: str,
        memories: List[Dict[str, Any]],
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.available():
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
            "You understand conversational Tamil (தமிழ்), Tanglish (Tamil spoken/written using English letters), and English naturally, just like ChatGPT.\n"
            "You have direct access to the user's persistent SQLite memory database.\n\n"
            "CRITICAL LANGUAGE RULE:\n"
            "Reply in the EXACT SAME language and conversational style the user used:\n"
            "- If user speaks/types Tanglish (e.g. 'En project deadline Friday nu nyabagam vachiko', 'Naan enna sonnen?', 'Enna nyabagam vechiruka?'):\n"
            "  Reply in natural, clear, friendly Tanglish (Tamil words written in English letters).\n"
            "  Example: 'Kandippa! Ungal project deadline Friday nu nyabagam vachikitten.'\n"
            "- If user speaks/types pure Tamil (Tamil script):\n"
            "  Reply in natural Tamil script. Example: 'கண்டிப்பாக! உங்கள் திட்டத்தின் இறுதி நாள் வெள்ளிக்கிழமை என்று நினைவில் குறித்துக்கொண்டேன்.'\n"
            "- If user speaks/types English:\n"
            "  Reply in natural English. Example: 'Got it! I have remembered that your project deadline is Friday.'\n"
            "Keep replies concise and voice-friendly (1-3 sentences).\n\n"
            "REAL MEMORY RULES:\n"
            "1. SAVE INTENT: If the user asks to save, remember, note, or keep any detail/task/deadline/preference\n"
            "   (e.g., '... nu nyabagam vachiko', 'remember that...', 'save pannu', 'ஞாபகம் வைத்துக்கொள்'):\n"
            "   - action: 'save'\n"
            "   - memory_content: the clean factual information without conversational wrapper phrases (e.g. 'Project deadline is Friday')\n"
            "   - category: appropriate short category ('project', 'personal', 'work', 'deadline', 'preference', etc.)\n"
            "2. RECALL INTENT: If the user asks a question about saved memories or previous information\n"
            "   (e.g., 'En project deadline eppo?', 'Where are my keys?', 'Naan enna sonnen?'):\n"
            "   - Answer strictly from the SAVED MEMORIES or RECENT CONVERSATION.\n"
            "   - If no relevant memory exists, state clearly in the user's language that you don't have that saved yet.\n"
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
            # Strip markdown formatting if any
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned.strip())
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "reply" in parsed:
                return parsed
        except Exception:
            pass

        return None


class OpenAICompatibleProvider(AIProvider):
    """Talks to any OpenAI-compatible completions endpoint."""

    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()

    def available(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> Optional[str]:
        if not self.available():
            return None
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
            message = choices[0].get("message") or {}
            return (message.get("content") or "").strip() or None
        except Exception:
            return None

    def analyze_and_respond(
        self,
        message: str,
        mode: str,
        memories: List[Dict[str, Any]],
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        # Use complete with JSON mode
        # Re-use the same prompt logic
        gemini_dummy = GeminiProvider(api_key="dummy")
        # Reuse prompt generation
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
            except Exception:
                pass
        return None


def get_provider() -> Optional[AIProvider]:
    """Return the active AI provider configured via environment variables.

    Prioritizes Google Gemini (GEMINI_API_KEY, GOOGLE_API_KEY),
    followed by generic AI_API_KEY with AI_PROVIDER=gemini or openai-compatible.
    """
    gemini_key = (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    provider_name = os.getenv("AI_PROVIDER", "").strip().lower()

    if gemini_key or provider_name in ("gemini", "google", "google-gemini"):
        key = gemini_key or os.getenv("AI_API_KEY", "").strip()
        if key:
            model = os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL") or DEFAULT_GEMINI_MODEL
            return GeminiProvider(api_key=key, model=model)

    generic_key = os.getenv("AI_API_KEY", "").strip()
    if provider_name in ("openai", "openai-compatible", "openai_compatible", "oai") and generic_key:
        base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("AI_MODEL", "gpt-4o-mini").strip()
        return OpenAICompatibleProvider(base_url=base_url, api_key=generic_key, model=model)

    return None


def provider_status() -> Dict[str, Any]:
    """Report the active AI provider status for /api/health and frontend settings."""
    provider = get_provider()
    if provider and provider.available():
        return {
            "ai_provider": provider.name,
            "ai_model": provider.model,
            "mode": "ai-assisted",
            "message": f"Connected to {provider.name.capitalize()} ({provider.model})",
        }
    return {
        "ai_provider": "none",
        "ai_model": "local-rule-engine",
        "mode": "local-fallback",
        "message": "Local memory mode. To enable Gemini AI, configure GEMINI_API_KEY in backend/.env.",
    }
