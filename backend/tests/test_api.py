import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory()
os.environ["MEMORA_DB_PATH"] = str(Path(tmp.name) / "test.db")

from app.main import app

class MemoraApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_memory_crud(self):
        created = self.client.post("/api/memories", json={"content": "Project deadline is Friday", "category": "study"})
        self.assertEqual(created.status_code, 201)
        item = created.json()
        self.assertEqual(item["content"], "Project deadline is Friday")
        self.assertEqual(self.client.get("/api/memories?q=deadline").status_code, 200)
        updated = self.client.patch(f"/api/memories/{item['id']}", json={"content": "Deadline is Saturday", "category": "study"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["content"], "Deadline is Saturday")
        deleted = self.client.delete(f"/api/memories/{item['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.delete(f"/api/memories/{item['id']}").status_code, 404)

    def test_chat_does_not_invent_memory(self):
        response = self.client.post("/api/chat", json={"message": "What is my secret project?"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("won't invent", response.json()["reply"])

    def test_reminder_crud(self):
        created = self.client.post("/api/reminders", json={"title": "Submit demo", "due_text": "Friday"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.get("/api/reminders").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/reminders/{created.json()['id']}").status_code, 200)


class MultilingualChatTests(unittest.TestCase):
    """Tamil / Tanglish / English command handling against the real API."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def _clean_matching(self, needle):
        for item in self.client.get("/api/memories").json():
            if needle.lower() in item["content"].lower():
                self.client.delete(f"/api/memories/{item['id']}")

    # -- explicit save intent ------------------------------------------------
    def test_english_save_command_creates_a_memory(self):
        response = self.client.post("/api/chat", json={"message": "Remember that my project deadline is Friday"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["saved"])
        self.assertEqual(body["intent"], "save_memory")
        items = self.client.get("/api/memories?q=project deadline").json()
        self.assertTrue(any("my project deadline is Friday" == item["content"] for item in items))
        self._clean_matching("project deadline is Friday")

    def test_tanglish_save_command_creates_a_memory(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Naan sonna project details save pannu.", "language": "tanglish"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["saved"])
        self.assertEqual(body["intent"], "save_memory")
        items = self.client.get("/api/memories?q=project details").json()
        self.assertTrue(any("project details" in item["content"] for item in items))
        self._clean_matching("project details")

    def test_tamil_script_save_command_creates_a_memory(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "எனது திட்ட விவரங்களை சேமி", "language": "ta-IN"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["saved"])
        items = self.client.get("/api/memories").json()
        self.assertTrue(any("திட்ட" in item["content"] for item in items))
        self._clean_matching("திட்ட")

    def test_plain_statement_is_not_saved_automatically(self):
        before = len(self.client.get("/api/memories").json())
        response = self.client.post(
            "/api/chat",
            json={"message": "En project deadline Friday.", "language": "tanglish"},
        )
        body = response.json()
        self.assertFalse(body["saved"])
        self.assertIsNotNone(body["pending"])
        self.assertEqual(body["pending"]["action"], "save_memory")
        self.assertIn("saamikka", body["reply"].lower())
        self.assertEqual(len(self.client.get("/api/memories").json()), before)

    def test_confirmation_saves_the_pending_memory(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "En project deadline Friday.", "language": "tanglish"},
        )
        pending = response.json()["pending"]["content"]
        confirm = self.client.post(
            "/api/chat",
            json={"message": "yes", "language": "tanglish", "pending_memory": pending},
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertTrue(confirm.json()["saved"])
        items = self.client.get("/api/memories?q=project deadline").json()
        self.assertTrue(any("project deadline" in item["content"] for item in items))
        self._clean_matching("project deadline")

    def test_rejection_cancels_the_pending_memory(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "En project deadline Friday.", "language": "tanglish"},
        )
        pending = response.json()["pending"]["content"]
        reject = self.client.post(
            "/api/chat",
            json={"message": "no", "language": "tanglish", "pending_memory": pending},
        )
        self.assertFalse(reject.json()["saved"])
        items = self.client.get("/api/memories?q=project deadline").json()
        self.assertFalse(any("project deadline" in item["content"] for item in items))

    # -- retrieval ------------------------------------------------------------
    def test_memory_retrieval_returns_real_records(self):
        created = self.client.post(
            "/api/memories", json={"content": "Team standup at 9 AM", "category": "work"}
        )
        self.addCleanup(self.client.delete, f"/api/memories/{created.json()['id']}")
        response = self.client.post(
            "/api/chat", json={"message": "What do you remember?", "language": "en-IN"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Team standup at 9 AM", response.json()["reply"])

    def test_tanglish_search_returns_real_records(self):
        created = self.client.post(
            "/api/memories", json={"content": "Bus pass renewal on 12 May", "category": "personal"}
        )
        self.addCleanup(self.client.delete, f"/api/memories/{created.json()['id']}")
        response = self.client.post(
            "/api/chat", json={"message": "En bus pass kidaikkum?", "language": "tanglish"}
        )
        self.assertIn("Bus pass renewal", response.json()["reply"])

    def test_search_does_not_invent_records(self):
        response = self.client.post(
            "/api/chat", json={"message": "Find zzzzznotarealrecord", "language": "en-IN"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("•", response.json()["reply"])

    def test_question_answers_with_the_real_record(self):
        created = self.client.post(
            "/api/memories", json={"content": "Water the balcony plants", "category": "home"}
        )
        self.addCleanup(self.client.delete, f"/api/memories/{created.json()['id']}")
        response = self.client.post(
            "/api/chat", json={"message": "What about the balcony plants?", "language": "en-IN"}
        )
        body = response.json()
        self.assertEqual(body["intent"], "recall")
        self.assertIn("Water the balcony plants", body["reply"])

    def test_question_without_a_match_does_not_invent(self):
        response = self.client.post(
            "/api/chat", json={"message": "What about the zzzz topic?", "language": "en-IN"}
        )
        body = response.json()
        self.assertEqual(body["intent"], "recall")
        self.assertNotIn("•", body["reply"])
        self.assertIn("won't invent", body["reply"])

    def test_tamil_question_answers_with_the_real_record(self):
        created = self.client.post(
            "/api/memories", json={"content": "பூந்தோட்டம் தண்ணீர் ஊற்ற வேண்டும்", "category": "home"}
        )
        self.addCleanup(self.client.delete, f"/api/memories/{created.json()['id']}")
        response = self.client.post(
            "/api/chat", json={"message": "பூந்தோட்டம் பற்றி என்ன?", "language": "ta-IN"}
        )
        body = response.json()
        self.assertEqual(body["intent"], "recall")
        self.assertIn("பூந்தோட்டம்", body["reply"])

    # -- ambiguous commands --------------------------------------------------
    def test_ambiguous_delete_asks_for_clarification(self):
        created = self.client.post(
            "/api/memories", json={"content": "Delete candidate note", "category": "test"}
        )
        self.addCleanup(self.client.delete, f"/api/memories/{created.json()['id']}")
        response = self.client.post(
            "/api/chat", json={"message": "Intha memory delete pannu.", "language": "tanglish"}
        )
        body = response.json()
        self.assertEqual(body["intent"], "delete_memory")
        self.assertIsNotNone(body["pending"])
        self.assertTrue(body["pending"]["candidates"])
        still_there = self.client.get("/api/memories?q=Delete candidate note").json()
        self.assertEqual(len(still_there), 1)

    def test_ambiguous_delete_with_number_deletes_that_record(self):
        created = self.client.post(
            "/api/memories", json={"content": "Numbered target note", "category": "test"}
        )
        self.addCleanup(self.client.delete, f"/api/memories/{created.json()['id']}")
        memory_id = created.json()["id"]
        response = self.client.post(
            "/api/chat",
            json={"message": f"delete #{memory_id}", "language": "en-IN"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "delete_memory")
        self.assertEqual(self.client.get("/api/memories?q=Numbered target note").json(), [])

    # -- greetings, reminders, empty input ------------------------------------
    def test_greeting_is_not_a_save(self):
        response = self.client.post(
            "/api/chat", json={"message": "Enna nyabagam vechirukka?", "language": "tanglish"}
        )
        self.assertEqual(response.json()["intent"], "greeting")
        self.assertFalse(response.json()["saved"])

    def test_tanglish_reminder_list(self):
        created = self.client.post("/api/reminders", json={"title": "Pay rent", "due_text": "Friday"})
        self.addCleanup(self.client.delete, f"/api/reminders/{created.json()['id']}")
        response = self.client.post(
            "/api/chat", json={"message": "En reminders enna irukku?", "language": "tanglish"}
        )
        self.assertEqual(response.json()["intent"], "reminder_list")
        self.assertIn("Pay rent", response.json()["reply"])

    def test_tanglish_reminder_creation(self):
        response = self.client.post(
            "/api/chat", json={"message": "Remind me to pay the rent tomorrow", "language": "tanglish"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "reminder_create")
        reminders = self.client.get("/api/reminders").json()
        created = [r for r in reminders if "pay the rent" in r["title"].lower()]
        self.assertTrue(created)
        self.client.delete(f"/api/reminders/{created[0]['id']}")

    def test_empty_message_is_rejected(self):
        self.assertEqual(self.client.post("/api/chat", json={"message": ""}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"message": "   "}).status_code, 422)

    def test_all_language_modes_are_accepted(self):
        for mode in ("ta-IN", "tanglish", "en-IN"):
            response = self.client.post("/api/chat", json={"message": "help", "language": mode})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["language"], mode)

    def test_languages_endpoint_lists_the_three_modes(self):
        response = self.client.get("/api/languages")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["languages"]]
        self.assertEqual(ids, ["ta-IN", "tanglish", "en-IN"])

    def test_health_reports_language_support(self):
        body = self.client.get("/api/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("tanglish", body["languages"])


if __name__ == "__main__":
    unittest.main()
