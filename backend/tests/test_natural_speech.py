"""Tests for natural Tamil, Tanglish, and English speech understanding in MEMORA AI."""

import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory()
os.environ["MEMORA_DB_PATH"] = str(Path(tmp.name) / "natural_test.db")
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("AI_API_KEY", None)

from app.main import app


class NaturalSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def tearDown(self):
        # Clear memories between tests
        for item in self.client.get("/api/memories").json():
            self.client.delete(f"/api/memories/{item['id']}")

    def test_tanglish_save_with_nyabagam_vachiko(self):
        """User says: 'En project deadline Friday nu nyabagam vachiko.'

        Must directly save the fact to SQLite without asking unnecessary confirmation.
        """
        response = self.client.post(
            "/api/chat",
            json={
                "message": "En project deadline Friday nu nyabagam vachiko.",
                "language": "tanglish",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["saved"], "Expected memory to be saved directly")
        self.assertEqual(data["intent"], "save_memory")

        # Verify saved record in SQLite
        items = self.client.get("/api/memories").json()
        self.assertTrue(len(items) >= 1)
        content = items[0]["content"].lower()
        self.assertIn("project deadline", content)
        self.assertIn("friday", content)

    def test_tanglish_recall_with_eppo(self):
        """User asks: 'En project deadline eppo?'

        Must recall the stored deadline from SQLite.
        """
        # First save the memory
        self.client.post(
            "/api/memories",
            json={"content": "Project deadline is Friday", "category": "project"},
        )

        response = self.client.post(
            "/api/chat",
            json={
                "message": "En project deadline eppo?",
                "language": "tanglish",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "recall")
        self.assertIn("Friday", data["reply"])

    def test_tanglish_recall_naan_enna_sonnen(self):
        """User asks: 'Naan enna sonnen?'

        Must recall the previous user input or memory.
        """
        # Save a conversation message
        self.client.post(
            "/api/chat",
            json={
                "message": "En friend Ramesh birthday tomorrow nu nyabagam vachiko.",
                "language": "tanglish",
            },
        )

        response = self.client.post(
            "/api/chat",
            json={
                "message": "Naan enna sonnen?",
                "language": "tanglish",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "recall")
        self.assertTrue(
            "Ramesh" in data["reply"] or "birthday" in data["reply"] or "sonnadhu" in data["reply"]
        )

    def test_tanglish_list_enna_nyabagam_vechiruka(self):
        """User asks: 'Enna nyabagam vechiruka?'

        Must list all currently stored memories.
        """
        self.client.post(
            "/api/memories",
            json={"content": "Dentist appointment at 4 PM", "category": "health"},
        )
        response = self.client.post(
            "/api/chat",
            json={
                "message": "Enna nyabagam vechiruka?",
                "language": "tanglish",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Dentist appointment", data["reply"])

    def test_tamil_script_natural_save_and_recall(self):
        """User speaks Tamil:

        Save: 'என் ப்ராஜெக்ட் டெட்லைன் வெள்ளிக்கிழமை என்று ஞாபகம் வச்சுக்கோ'
        Recall: 'என் ப்ராஜெக்ட் டெட்லைன் எப்போது?'
        """
        save_res = self.client.post(
            "/api/chat",
            json={
                "message": "என் ப்ராஜெக்ட் டெட்லைன் வெள்ளிக்கிழமை என்று ஞாபகம் வச்சுக்கோ",
                "language": "ta-IN",
            },
        )
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.json()["saved"])

        recall_res = self.client.post(
            "/api/chat",
            json={
                "message": "என் ப்ராஜெக்ட் டெட்லைன் எப்போது?",
                "language": "ta-IN",
            },
        )
        self.assertEqual(recall_res.status_code, 200)
        self.assertEqual(recall_res.json()["intent"], "recall")
        self.assertIn("வெள்ளிக்கிழமை", recall_res.json()["reply"])

    def test_acceptance_criteria_1_tamil_explicit_save(self):
        """1. “நாளைக்கு எனக்கு எக்ஸாம் என்று ஞாபகம் வைத்துக்கொள்” -> saves the correct fact and confirms in Tamil."""
        response = self.client.post(
            "/api/chat",
            json={
                "message": "நாளைக்கு எனக்கு எக்ஸாம் என்று ஞாபகம் வைத்துக்கொள்",
                "language": "ta-IN",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["saved"], "Expected memory to be saved directly in SQLite")
        self.assertEqual(data["intent"], "save_memory")
        self.assertIn("சேமித்துவிட்டேன்", data["reply"])
        self.assertIn("நாளைக்கு எனக்கு எக்ஸாம்", data["reply"])

        # Verify persistence in SQLite
        items = self.client.get("/api/memories").json()
        saved_facts = [i["content"] for i in items]
        self.assertIn("நாளைக்கு எனக்கு எக்ஸாம்", saved_facts)

    def test_acceptance_criteria_2_tamil_list_memories(self):
        """2. “எனக்கு என்ன ஞாபகம் வைத்திருக்கிறாய்?” -> lists actual saved memories."""
        # Pre-seed memory
        self.client.post("/api/memories", json={"content": "ப்ராஜெக்ட் டெட்லைன் வெள்ளி"})
        response = self.client.post(
            "/api/chat",
            json={
                "message": "எனக்கு என்ன ஞாபகம் வைத்திருக்கிறாய்?",
                "language": "ta-IN",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "list_memories")
        self.assertIn("உங்கள் நினைவில் இருப்பவை", data["reply"])
        self.assertIn("ப்ராஜெக்ட் டெட்லைன் வெள்ளி", data["reply"])

    def test_acceptance_criteria_3_tanglish_save_deadline(self):
        """3. “En project deadline Friday nu nyabagam vachiko” -> saves the fact and confirms in Tanglish."""
        response = self.client.post(
            "/api/chat",
            json={
                "message": "En project deadline Friday nu nyabagam vachiko",
                "language": "tanglish",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["saved"], "Expected memory to be saved directly in SQLite")
        self.assertEqual(data["intent"], "save_memory")
        self.assertIn("save pannitten", data["reply"].lower())

        # Verify persistence
        items = self.client.get("/api/memories").json()
        self.assertTrue(any("project deadline" in i["content"].lower() for i in items))

    def test_acceptance_criteria_4_tanglish_recall_deadline(self):
        """4. “En project deadline eppo?” -> retrieves the saved deadline."""
        self.client.post("/api/memories", json={"content": "Project deadline is Friday"})
        response = self.client.post(
            "/api/chat",
            json={
                "message": "En project deadline eppo?",
                "language": "tanglish",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intent"], "recall")
        self.assertIn("Friday", data["reply"])

    def test_acceptance_criteria_5_ordinary_message_conversational_reply(self):
        """5. Ordinary messages receive relevant conversational replies instead of repeated generic fallback.

        “நாளைக்கு எனக்கு எக்ஸாம்” must NOT be saved automatically, and must receive a helpful,
        relevant conversational reply wishing them well.
        """
        response = self.client.post(
            "/api/chat",
            json={
                "message": "நாளைக்கு எனக்கு எக்ஸாம்",
                "language": "ta-IN",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["saved"], "Ordinary statements must NOT be saved automatically")
        self.assertIn("வாழ்த்துகள்", data["reply"])
        # Ensure it does NOT return the canned robotic fallback
        self.assertNotIn("இந்தப் பதிப்பில் மேம்பட்ட AI இல்லை", data["reply"])
        self.assertNotIn("AI connect aagala", data["reply"])

    def test_relative_date_resolution(self):
        """Relative dates like 'நாளைக்கு' resolve to tomorrow's date using local time."""
        response = self.client.post(
            "/api/chat",
            json={
                "message": "நாளைக்கு எனக்கு எக்ஸாம் என்று ஞாபகம் வைத்துக்கொள்",
                "language": "ta-IN",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should contain resolved date note e.g. "2026"
        self.assertIn("என்பது", data["reply"])


if __name__ == "__main__":
    unittest.main()

