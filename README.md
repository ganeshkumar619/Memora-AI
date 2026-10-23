# MEMORA AI — Personal Memory Assistant

A local-first full-stack starter for a **multilingual, voice-friendly** personal memory assistant. This version includes a React interface, FastAPI backend, SQLite persistence, memory CRUD, reminders, browser speech input/output in **Tamil, Tanglish and English**, and a deterministic offline command engine.

> This is a verified starter prototype, not a zero-error guarantee or a production-secure service. Advanced generative AI is not configured by default. The app will not invent personal facts.

## What is new in the multilingual voice release

- **Language selector next to the microphone** — தமிழ் (Tamil, `ta-IN`), Tanglish, English (`en-IN`).
- **Voice input** through the browser `SpeechRecognition` API with a `webkitSpeechRecognition` fallback: live interim transcript, a visible **Stop** button, and automatic handling of silence, permission and network errors.
- **Editable transcript** — nothing is sent until you press *Send*, so a misheard word can be corrected first. Partial or empty results are never auto-submitted.
- **Tamil / Tanglish / English command understanding** — save, list, recall, search, delete, reminders, greetings and help. The original transcript is always preserved; names, dates and numbers survive normalisation.
- **Safe memory handling** — a plain sentence is *never* saved silently. Memora asks first and only writes after an explicit "yes".
- **Real retrieval** — questions are answered from the actual SQLite rows. When nothing matches, Memora says so instead of guessing.
- **Voice replies** — a toggle in the composer footer, plus a voice picker and a speech-rate slider in Settings. Tamil prefers a `ta-IN` voice; Tanglish and English use an English voice.
- **Friendly errors** in the language you are speaking in, including for missing microphone permission and for devices with no Tamil voice installed.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- Node.js 20 or newer (LTS recommended)
- Internet connection for first-time package installation
- A Chromium-based browser (Chrome or Edge) for voice input — see [Browser support](#browser-support)

## 1. Start backend (Terminal 1)

Open PowerShell in the `MEMORA_AI` folder:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal open. The backend API will be at `http://127.0.0.1:8000`; interactive API docs are at `http://127.0.0.1:8000/docs`.

If `python` is not recognized, install Python from https://www.python.org/downloads/windows/ and enable the option to add Python to PATH. Then reopen PowerShell.

## 2. Start frontend (Terminal 2)

Open a second PowerShell in the `MEMORA_AI` folder:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL Vite prints, normally `http://127.0.0.1:5173`.

## 3. Verify

Open `http://127.0.0.1:8000/api/health`. It should return JSON containing `"status":"ok"` and `"languages":["ta-IN","tanglish","en-IN"]`.

In the app:
1. Open **My memories**, save a note.
2. Refresh the page; the note should still be there.
3. Edit and delete a note.
4. Add and delete a reminder.
5. In **Assistant**, try `Remember that my project deadline is Friday`, then `What do you remember?`.
6. Pick **தமிழ்** in the language selector, press the microphone and say `எனது திட்ட விவரங்களை சேமி`. The transcript appears in the editable box — press **Send**.
7. Try **Tanglish**: `Enna nyabagam vechirukka?` and `Naan sonna project details save pannu.`
8. Toggle **Voice replies on** and choose a voice and rate under **Settings**.

### Multilingual API

`POST /api/chat` accepts a `language` field:

```jsonc
{ "message": "என் பெயர் என்ன?", "language": "ta-IN" }   // ta-IN | tanglish | en-IN
```

The reply is written in the language you selected. The response also reports
`detected_language` (the script the text was actually written in), `intent`,
`normalized` (the canonical form) and `pending` (a confirmation request).
`GET /api/languages` lists the supported modes and the recognition code used for each.

## 4. Run backend tests

From PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers the normalisation rules, explicit-save intent, retrieval from
real records, ambiguity handling, empty input and the multilingual API. It uses
a temporary database, so `backend/memora.db` is never modified.

## 5. Build frontend

From a second terminal:

```powershell
cd frontend
npm run build
```

## Browser support

| Feature | Requirement |
| --- | --- |
| Voice input | Chrome or Edge (desktop). The Web Speech API is not available in Firefox, and Safari support is limited. |
| Tamil recognition | The browser must have a `ta-IN` model; Chrome downloads it on demand. |
| Tanglish recognition | **Best effort.** Browsers have no Tanglish model, so the Tamil (`ta-IN`) engine is used and the transcript is normalised afterwards. Accuracy depends on the device. |
| Tamil voice output | Requires an installed `ta-IN` speech-synthesis voice. On Windows, install *Tamil (India)* under *Settings → Time & language → Speech*. If none is available the reply is shown as readable text instead. |
| Tanglish voice output | Tanglish is written with Latin letters, so it is read with an English voice. The pronunciation is an approximation and will not match a native speaker exactly. |

Everything works without a microphone: the chat, memories and reminders tabs are fully usable by typing.

## Optional AI provider

The deterministic command layer always runs first, so saving, deleting and
retrieval never depend on an external service. A provider is consulted only
for open ended questions, and only when the operator explicitly configures it:

```powershell
$env:AI_PROVIDER = "openai-compatible"
$env:AI_API_KEY = "your-own-key"
$env:AI_BASE_URL = "https://api.openai.com/v1"
$env:AI_MODEL = "gpt-4o-mini"
```

No key ships with this project and no paid service is contacted by default.
See `backend/.env.example`. If the provider fails, the local answer is used.

## Troubleshooting

- **Backend connection unavailable:** Make sure the backend terminal is still running at port 8000.
- **Port 8000 already in use:** Stop the other server with `Ctrl+C`, or run Uvicorn on another port and update `API` in `frontend/src/App.tsx`.
- **`python` not recognized:** Install Python and reopen the terminal; use `py` only if the Python launcher is installed.
- **`npm` not recognized:** Install Node.js LTS and reopen the terminal.
- **Voice input unavailable:** Use current Chrome or Edge, allow microphone access, or continue with text input.
- **"Tamil speech recognition is not supported":** The browser has no `ta-IN` model. Switch the selector to English or install the Tamil language pack in the browser settings.
- **No Tamil voice:** Install the Tamil speech voice in the operating system, or read the reply as text.
- **Advanced AI answers:** Not included in this offline-friendly build by default — see *Optional AI provider* above.

## Data and privacy

The SQLite database is stored at `backend/memora.db` by default (override with `MEMORA_DB_PATH`). Keep it private. This local prototype does not include user accounts or multi-user isolation; do not expose it publicly as-is. The browser sends chat text to the local backend. No external AI provider is called by default.

## Amazon Alexa+ hackathon note

This app is a standalone simulated assistant prototype. Do not claim it is an actual Alexa+ integration. Before submitting to any hackathon, confirm the current track requirements and adapt the demo to the permitted route.
