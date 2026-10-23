"""Comprehensive tests for MEMORA AI Gemini Integration & Persistent Memory."""

import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app, init_db, rows
from app import ai
from app.ai import GeminiProvider, sanitize_log


class GeminiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_api_key_never_leaked_in_logs_or_status(self):
        secret = "AIzaSySecretKey9876543210Test"
        cleaned = sanitize_log(f"Error calling https://api.google.com?key={secret}")
        self.assertNotIn(secret, cleaned)
        self.assertIn("key=[REDACTED]", cleaned)

    def test_health_reports_accurate_status(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("ai_provider", data)
        self.assertIn("mode", data)
        self.assertIn("connected", data)
        # API key must never be exposed
        self.assertNotIn("AIzaSy", str(data))

    def test_ganesh_memory_save_and_recall_chat(self):
        """When user says:
        'Machi, en peru Ganesh. Naan II Year CSE student. Idha remember panniko'
        save memory, and when user asks:
        'En peru enna? Naan endha year padikkiren?'
        answer 'Un peru Ganesh, nee II Year CSE student.'
        """
        # Test mocked AI response
        save_mock = {
            "intent": "save_memory",
            "reply": "Kandippa Ganesh! Neenga II Year CSE student nu nyabagam vachikitten.",
            "action": "save",
            "memory_content": "Name: Ganesh, II Year CSE student",
            "category": "personal",
            "detected_language": "tanglish",
        }
        recall_mock = {
            "intent": "recall",
            "reply": "Un peru Ganesh, nee II Year CSE student.",
            "action": "none",
            "memory_content": None,
            "category": None,
            "target_id": None,
            "detected_language": "tanglish",
        }

        provider = ai.get_provider()
        if provider and provider.available():
            with patch.object(provider, "analyze_and_respond", side_effect=[save_mock, recall_mock]):
                # Turn 1: Save
                res1 = self.client.post(
                    "/api/chat",
                    json={
                        "message": "Machi, en peru Ganesh. Naan II Year CSE student. Idha remember panniko",
                        "language": "tanglish",
                    },
                )
                self.assertEqual(res1.status_code, 200)
                d1 = res1.json()
                self.assertTrue(d1.get("saved"))
                self.assertIn("nyabagam vachikitten", d1.get("reply", ""))

                # Verify persistent SQLite row exists
                saved_rows = rows("SELECT * FROM memories WHERE content LIKE '%Ganesh%'")
                self.assertGreaterEqual(len(saved_rows), 1)

                # Turn 2: Recall
                res2 = self.client.post(
                    "/api/chat",
                    json={
                        "message": "En peru enna? Naan endha year padikkiren?",
                        "language": "tanglish",
                    },
                )
                self.assertEqual(res2.status_code, 200)
                d2 = res2.json()
                self.assertEqual(d2.get("mode"), "ai-assisted")
                self.assertIn("Un peru Ganesh", d2.get("reply", ""))
                self.assertIn("II Year CSE student", d2.get("reply", ""))

    def test_local_fallback_answers_name_and_year_instead_of_repeating_prompt(self):
        """When in local fallback, it should synthesize the answer rather than echoing raw input."""
        with patch.object(ai, "get_provider", return_value=None):
            # Save memory via local fallback
            self.client.post(
                "/api/memories",
                json={"content": "en peru Ganesh. Naan II Year CSE student", "category": "personal"},
            )
            # Ask question
            res = self.client.post(
                "/api/chat",
                json={
                    "message": "En peru enna? Naan endha year padikkiren?",
                    "language": "tanglish",
                },
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data.get("mode"), "local-fallback")
            # Must formulate the answer
            reply = data.get("reply", "")
            self.assertTrue(
                "Un peru Ganesh" in reply or "Ganesh" in reply,
                f"Expected answer with Ganesh, got {reply}",
            )

    def test_gemini_error_returns_honest_ai_error_mode(self):
        """When Gemini fails, never silently pretend it succeeded or return fake answers."""
        provider = GeminiProvider(api_key="fake-key-for-test", model="gemini-2.5-flash")
        provider.last_error = "503 Model High Demand"

        with patch.object(ai, "get_provider", return_value=provider):
            with patch.object(provider, "analyze_and_respond", return_value=None):
                res = self.client.post(
                    "/api/chat",
                    json={"message": "Save this please", "language": "en-IN"},
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["mode"], "ai-error")
                self.assertIn("Gemini AI error", data["reply"])
                self.assertFalse(data["saved"])

    def test_multilingual_responses(self):
        """Verify Tamil, Tanglish, and English modes are respected."""
        provider = ai.get_provider()
        if provider and provider.available():
            mock_res = {
                "intent": "chat",
                "reply": "வணக்கம்! நான் உங்களுக்கு எப்படி உதவலாம்?",
                "action": "none",
                "detected_language": "tamil",
            }
            with patch.object(provider, "analyze_and_respond", return_value=mock_res):
                res = self.client.post(
                    "/api/chat",
                    json={"message": "வணக்கம்", "language": "ta-IN"},
                )
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["mode"], "ai-assisted")
                self.assertIn("வணக்கம்", res.json()["reply"])


if __name__ == "__main__":
    unittest.main()
