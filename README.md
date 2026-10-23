# MEMORA AI — Intelligent Personal Voice-Memory Assistant

MEMORA AI is an intelligent, privacy-first personal voice-memory assistant built with a **React + Vite + TypeScript** frontend, a **Python FastAPI** backend, and persistent **SQLite** database storage.

It understands spoken and typed conversations naturally in **Tamil (தமிழ்)**, **Tanglish (Tamil spoken/written using English letters)**, and **English**, just like ChatGPT.

---

## Key Features

### 1. Natural Language & Tanglish Understanding
- **True Conversational NLU:** Understands informal sentences, mixed-language phrasing, and spelling variations without depending on rigid keywords.
  - *Example:* `“En project deadline Friday nu nyabagam vachiko.”` — directly recognized as an explicit command to save your project deadline.
  - *Example:* `“En project deadline eppo?”` — understands you are asking when the deadline is and returns the saved date.
  - *Example:* `“Naan enna sonnen?”` — recalls your previous conversation and notes.
  - *Example:* `“Enna nyabagam vechiruka?”` — lists what has been stored in memory.
  - *Example (Tamil):* `“என் ப்ராஜெக்ட் டெட்லைன் வெள்ளிக்கிழமை என்று ஞாபகம் வச்சுக்கோ”`
- **Matching Style & Language:**
  - Speaks Tanglish? Replies in natural, friendly Tanglish.
  - Speaks Tamil? Replies in natural Tamil script.
  - Speaks English? Replies in clear, natural English.

### 2. Dual-Engine AI Brain (Google Gemini + Local SQLite NLU)
- **Primary AI Brain:** Integrated with **Google Gemini** (`gemini-2.5-flash` with automatic fallback to `gemini-1.5-flash`). Powered by Google AI Studio.
- **Grounding without Hallucination:** Gemini is fed your real SQLite memories as context; it strictly never invents facts or claims something was saved when it was not.
- **Local Fallback Mode:** If no API key is provided or the network is offline, MEMORA AI automatically falls back to an enhanced local deterministic memory engine and clearly flags local mode in the UI.

### 3. Voice Assistant with Hands-Free Auto-Submission
- **Microphone Input:** Browser Web Speech API with live interim transcript display.
- **Automatic Speech Submission:** Detects when you finish speaking and automatically submits the recognized text for hands-free conversational flow.
- **Voice Replies (TTS):** Speaks assistant replies aloud using appropriate browser speech synthesis (`ta-IN` for Tamil, Indian English `en-IN` for natural Tanglish pronunciation).
- **Graceful Error Handling:** Explicit, friendly error messages in Tamil, Tanglish, or English for permission blocks, silence, or network dropouts.

### 4. Real SQLite Memory Persistence
- Stored locally in `backend/memora.db` (never lost across restarts).
- Full CRUD operations: Save, search, view, update, and delete memories.
- Built-in Reminders tracker for deadlines and tasks.

---

## Quick Start on Windows

### Option A: One-Click Launch (Recommended)
Double-click `start.bat` in the project root. It automatically sets up the Python virtual environment, installs dependencies, and starts both backend and frontend servers in separate windows.

---

### Option B: Manual Terminal Execution

#### 1. Backend Setup (Terminal 1)
Open PowerShell in `d:\MEMORA_AI`:
```powershell
cd backend

# Create virtual environment if not already created
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\activate.bat

# Install dependencies
python -m pip install -r requirements.txt

# Start FastAPI backend (port 8000)
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
The backend API runs at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

#### 2. Frontend Setup (Terminal 2)
Open a second PowerShell in `d:\MEMORA_AI`:
```powershell
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
Open `http://localhost:5173` in Google Chrome or Microsoft Edge.

---

## Configuring Google Gemini AI Brain

1. In the `backend/` folder, copy `.env.example` to `.env`:
   ```powershell
   cd backend
   copy .env.example .env
   ```
2. Open `backend/.env` in any text editor and add your API key from [Google AI Studio](https://aistudio.google.com/):
   ```env
   GEMINI_API_KEY=AIzaSy...your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```
3. Restart or save the backend. MEMORA AI will automatically detect the key and show `✨ Gemini 2.5 Flash` in the top bar!

*Note: Your API key is stored only on your computer in `.env` and is never sent to the frontend or printed in logs.*

---

## Verification & Testing

### 1. Run Backend Automated Test Suite
From the `backend/` folder:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
**Results:** 85 tests covering:
- Natural Tanglish save (`"Machi, en peru Ganesh. Naan II Year CSE student. Idha remember panniko."`)
- Natural Tanglish recall (`"En peru enna? Naan endha year padikkiren?"`)
- Tamil script commands and question answering
- Google Gemini API integration and mocked structured outputs
- Local fallback behavior and memory grounding
- Memory CRUD and reminder CRUD
- API key masking and honest error reporting

### 2. Verify Frontend Production Build
From the `frontend/` folder:
```powershell
npm run build
```
Builds the optimized production bundle into `frontend/dist/` with zero TypeScript errors.

---

## Sample Voice Prompts to Try

| Goal | Spoken Prompt | Language Mode |
|---|---|---|
| **Save identity/year** | `“Machi, en peru Ganesh. Naan II Year CSE student. Idha remember panniko.”` | Tanglish |
| **Ask identity/year** | `“En peru enna? Naan endha year padikkiren?”` | Tanglish |
| **Save deadline** | `“En project deadline Friday nu nyabagam vachiko.”` | Tanglish |
| **Ask deadline** | `“En project deadline eppo?”` | Tanglish |
| **Recall conversation** | `“Naan enna sonnen?”` | Tanglish |
| **List memories** | `“Enna nyabagam vechiruka?”` | Tanglish |
| **Save in Tamil** | `“என் ப்ராஜெக்ட் டெட்லைன் வெள்ளிக்கிழமை என்று ஞாபகம் வச்சுக்கோ”` | Tamil |
| **Recall in Tamil** | `“என் ப்ராஜெக்ட் டெட்லைன் எப்போது?”` | Tamil |
| **Save in English** | `“Remember that my passport is in the top drawer.”` | English |
| **Recall in English**| `“Where is my passport?”` | English |

---

## Project Structure

```text
MEMORA_AI/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── ai.py                   # Google Gemini & OpenAI provider abstraction
│   │   ├── language.py             # Multilingual tokenization & NLU engine
│   │   └── main.py                 # FastAPI application, SQLite persistence & endpoints
│   ├── tests/
│   │   ├── test_api.py             # API endpoint regression suite
│   │   ├── test_gemini_ai.py       # Gemini AI Brain & fallback tests
│   │   ├── test_gemini_integration.py # 2-turn Ganesh flow & health status tests
│   │   ├── test_language.py        # Language normalization unit tests
│   │   └── test_natural_speech.py  # Spoken Tamil/Tanglish/English tests
│   ├── .env.example                # Environment variable template
│   ├── main.py                     # Root ASGI entrypoint (uvicorn main:app)
│   ├── memora.db                   # SQLite database
│   ├── requirements.txt            # Python production dependencies
│   └── test_memora.py              # Backwards compatibility test
├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Main responsive UI with mic & auto-submit
│   │   ├── languages.ts    # Voice recognition & speech language mapping
│   │   ├── speech.ts       # Web Speech API recognition & synthesis wrappers
│   │   ├── style.css       # Clean dark-mode UI design system
│   │   └── types.ts        # TypeScript interfaces
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── start.bat               # Windows one-click launcher
└── README.md
```
