import os, tempfile
os.environ["MEMORA_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.pop("ANTHROPIC_API_KEY", None)
from fastapi.testclient import TestClient
from main import app
c = TestClient(app)

def test_memory_crud():
    m = c.post("/api/memories", json={"text": "Dentist on Friday at 4pm", "tag": "plans"}).json()
    assert c.get("/api/memories", params={"q": "dentist"}).json()[0]["id"] == m["id"]
    u = c.put(f"/api/memories/{m['id']}", json={"text": "Dentist on Monday"}).json()
    assert "Monday" in u["text"]
    assert c.delete(f"/api/memories/{m['id']}").status_code in (200, 204)
    assert c.get("/api/memories", params={"q": "dentist"}).json() == []
    assert c.delete(f"/api/memories/{m['id']}").status_code == 404

def test_assistant_remember_recall_forget_and_history():
    r = c.post("/api/assistant", json={"message": "Alexa, remember that my keys are in the blue drawer"}).json()
    assert r["intent"] == "remember"
    r = c.post("/api/assistant", json={"message": "where are my keys"}).json()
    assert "blue drawer" in r["reply"]
    assert len(c.get("/api/history").json()) >= 4
    assert c.post("/api/assistant", json={"message": "forget keys"}).json()["intent"] == "forget"
    assert "don't have" in c.post("/api/assistant", json={"message": "where are my keys"}).json()["reply"]
