"""Unit tests for the Google Gemini AI Brain integration in MEMORA AI."""

import os
import unittest
from unittest.mock import MagicMock, patch
from app import ai
from app.ai import GeminiProvider, OpenAICompatibleProvider


class GeminiAITests(unittest.TestCase):
    def test_provider_status_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            status = ai.provider_status()
            self.assertEqual(status["ai_provider"], "none")
            self.assertEqual(status["mode"], "local-fallback")
            self.assertIn("Local", status["message"])

    def test_provider_status_with_gemini_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyFakeTestKey123"}, clear=True):
            provider = ai.get_provider()
            self.assertIsNotNone(provider)
            self.assertIsInstance(provider, GeminiProvider)
            self.assertTrue(provider.available())
            status = ai.provider_status()
            self.assertEqual(status["ai_provider"], "gemini")
            self.assertEqual(status["mode"], "ai-assisted")
            # Ensure API key is never leaked in status
            self.assertNotIn("AIzaSy", str(status))

    def test_gemini_mocked_natural_tanglish_save(self):
        provider = GeminiProvider(api_key="fake-test-key", model="gemini-2.5-flash")
        mock_gemini_response = (
            '{\n'
            '  "intent": "save_memory",\n'
            '  "reply": "Kandippa! Ungal project deadline Friday nu nyabagam vachikitten.",\n'
            '  "action": "save",\n'
            '  "memory_content": "Project deadline is Friday",\n'
            '  "category": "project",\n'
            '  "detected_language": "tanglish"\n'
            '}'
        )

        with patch.object(provider, "complete", return_value=mock_gemini_response):
            result = provider.analyze_and_respond(
                message="En project deadline Friday nu nyabagam vachiko.",
                mode="tanglish",
                memories=[],
            )
            self.assertIsNotNone(result)
            self.assertEqual(result["intent"], "save_memory")
            self.assertEqual(result["action"], "save")
            self.assertEqual(result["memory_content"], "Project deadline is Friday")
            self.assertIn("nyabagam vachikitten", result["reply"])

    def test_gemini_mocked_natural_tanglish_recall(self):
        provider = GeminiProvider(api_key="fake-test-key", model="gemini-2.5-flash")
        mock_gemini_response = (
            '{\n'
            '  "intent": "recall",\n'
            '  "reply": "Ungal project deadline Friday.",\n'
            '  "action": "none",\n'
            '  "memory_content": null,\n'
            '  "detected_language": "tanglish"\n'
            '}'
        )

        with patch.object(provider, "complete", return_value=mock_gemini_response):
            result = provider.analyze_and_respond(
                message="En project deadline eppo?",
                mode="tanglish",
                memories=[{"id": 1, "content": "Project deadline is Friday", "category": "project"}],
            )
            self.assertIsNotNone(result)
            self.assertEqual(result["intent"], "recall")
            self.assertEqual(result["action"], "none")
            self.assertIn("Friday", result["reply"])

    def test_gemini_failure_returns_none_for_local_fallback(self):
        provider = GeminiProvider(api_key="fake-test-key", model="gemini-2.5-flash")
        with patch.object(provider, "complete", return_value=None):
            result = provider.analyze_and_respond(
                message="En project deadline Friday nu nyabagam vachiko.",
                mode="tanglish",
                memories=[],
            )
            self.assertIsNone(result, "When Gemini call fails, should return None for fallback")


if __name__ == "__main__":
    unittest.main()
