import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Brain, MessageCircle, Database, Bell, Settings, Mic, Send, Plus, Search, Trash2,
  Volume2, VolumeX, Sparkles, Menu, X, Check, LoaderCircle, Square, Languages, AudioLines,
  Zap, Info, CornerDownLeft, Play,
} from 'lucide-react'
import { LANGUAGES, getLanguage, modeFor, isLanguageId, type LanguageId } from './languages'
import {
  classifySpeechError, getSpeechRecognition, isSpeechSynthesisSupported, loadVoices,
  pickVoiceForLanguage, speak, stopSpeaking,
  type SpeechErrorKind, type SpeechRecognitionInstance,
} from './speech'
import type { ChatPending, ChatResponse, HealthResponse, Memory, Message, Reminder } from './types'

const API = 'http://127.0.0.1:8000/api'
const MAX_LISTEN_MS = 45000
const SILENCE_MS = 8000

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
  return data as T
}

/* -------------------------------------------------------------------------- */
/* Preferences stored in browser localStorage                                  */
/* -------------------------------------------------------------------------- */

function readString(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

function readBool(key: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(key)
    return raw === null ? fallback : raw === 'true'
  } catch {
    return fallback
  }
}

function readNumber(key: string, fallback: number): number {
  try {
    const raw = window.localStorage.getItem(key)
    const parsed = raw === null ? NaN : Number(raw)
    return Number.isFinite(parsed) ? parsed : fallback
  } catch {
    return fallback
  }
}

function writePref(key: string, value: string | number | boolean): void {
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    /* ignore */
  }
}

/* -------------------------------------------------------------------------- */
/* Multilingual Error Messages                                                */
/* -------------------------------------------------------------------------- */

type MessageKind =
  | 'permission' | 'unsupported' | 'no-speech' | 'network' | 'audio' | 'language'
  | 'timeout' | 'silent' | 'no-synthesis' | 'no-tamil-voice' | 'unknown'

const VOICE_MESSAGES: Record<MessageKind, Record<LanguageId, string>> = {
  permission: {
    tamil: 'நுண்ணுறைப் பயன்பாட்டு அனுமதி மறுக்கப்பட்டது. உலாவி முகவரிப் பட்டியில் உள்ள அனுமதி அமைப்புகளில் மைக்ரோஃபோனை இயக்கவும்.',
    tanglish: 'Microphone permission blocked. Browser address bar la camera/mic icon click panni "Allow" kudunga.',
    english: 'Microphone permission was denied. Please allow microphone access in your browser address bar settings.',
  },
  unsupported: {
    tamil: 'இந்த உலாவில் பேச்சு அடையாளம் இல்லை. Chrome அல்லது Edge உலாவியைப் பயன்படுத்தவும்.',
    tanglish: 'Indha browser la speech recognition illa. Latest Chrome or Edge use pannunga.',
    english: 'Voice input is not supported in this browser. Try a current version of Chrome or Edge.',
  },
  'no-speech': {
    tamil: 'பேச்சு எதுவும் கேட்கவில்லை. மீண்டும் மைக்ரோஃபோனை அழுத்திப் பேசவும்.',
    tanglish: 'Edhum kekkala. Marubadiyum mic click panni pesunga.',
    english: "I didn't hear anything. Please press the mic and speak again.",
  },
  network: {
    tamil: 'இணைய இணைப்புப் பிழை. பேச்சு அடையாளத்திற்கு இணையம் தேவைப்படுகிறது.',
    tanglish: 'Internet connection issue. Speech recognition ku internet venum.',
    english: 'Network error. Speech recognition requires an active internet connection.',
  },
  audio: {
    tamil: 'மைக்ரோஃபோன் கிடைக்கவில்லை. உங்கள் ஆடியோ சாதனத்தைச் சரிபார்க்கவும்.',
    tanglish: 'Microphone kidaikkala. Audio device connect aayirukka nu paarunga.',
    english: 'No microphone was found. Please check your audio input hardware.',
  },
  language: {
    tamil: 'இந்த உலாவில் இந்த மொழிப் பேச்சு அடையாளம் இல்லை.',
    tanglish: 'Indha browser la speech recognition language pack illa.',
    english: 'This browser does not support the selected recognition language.',
  },
  timeout: {
    tamil: 'அதிகபட்ச நேரம் முடிந்தது. உங்கள் பேச்சு அனுப்பப்பட்டது.',
    tanglish: 'Max time mudinjadhu.',
    english: 'Listening session reached time limit.',
  },
  silent: {
    tamil: 'சிறிது நேரம் அமைதி இருந்ததால் கேட்பது நிறுத்தப்பட்டது.',
    tanglish: 'Konjam neram pesala, so listening stop pannitten.',
    english: "Stopped listening after silence.",
  },
  'no-synthesis': {
    tamil: 'இந்த உலாவில் குரல் வாசிப்பு இல்லை. பதில் உரையாகக் காட்டப்பட்டுள்ளது.',
    tanglish: 'Indha browser la voice output illa. Text ah padikkalaam.',
    english: 'Voice output is not supported on this browser. Replies are shown as text.',
  },
  'no-tamil-voice': {
    tamil: 'சாதனத்தில் தமிழ் குரல் இல்லை. பதில் உரையாகக் காட்டப்பட்டுள்ளது.',
    tanglish: 'Tamil voice illai. Text reply kaattappadugiradhu.',
    english: 'No Tamil voice is installed on this device. Reply shown as text.',
  },
  unknown: {
    tamil: 'பேச்சு அடையாளத்தில் பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.',
    tanglish: 'Speech recognition la error vandhadhu. Meendum muyarchi pannunga.',
    english: 'An error occurred during speech recognition. Please try again.',
  },
}

const SPEECH_ERROR_TO_MESSAGE: Record<SpeechErrorKind, MessageKind> = {
  permission: 'permission',
  unsupported: 'unsupported',
  'no-speech': 'no-speech',
  network: 'network',
  audio: 'audio',
  language: 'language',
  aborted: 'silent',
  unknown: 'unknown',
}

export default function App() {
  const [tab, setTab] = useState<'chat' | 'memories' | 'reminders' | 'settings'>('chat')
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      text: 'Vanakkam! I am MEMORA AI, your personal voice memory assistant. Speak naturally in Tamil, Tanglish, or English. Try: “En project deadline Friday nu nyabagam vachiko.”',
      time: 'Just now',
    },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [memories, setMemories] = useState<Memory[]>([])
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [search, setSearch] = useState('')
  const [memoryText, setMemoryText] = useState('')
  const [reminderText, setReminderText] = useState('')
  const [dueText, setDueText] = useState('')
  const [voiceOn, setVoiceOn] = useState(() => readBool('memora.voiceOn', true))
  const [autoSubmit, setAutoSubmit] = useState(() => readBool('memora.autoSubmit', true))
  const [listening, setListening] = useState(false)
  const [notice, setNotice] = useState('')
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [healthInfo, setHealthInfo] = useState<HealthResponse | null>(null)
  const [mobileNav, setMobileNav] = useState(false)

  /* --- voice input --- */
  const [language, setLanguage] = useState<LanguageId>(() => {
    const stored = readString('memora.language', 'tanglish')
    return isLanguageId(stored) ? stored : 'tanglish'
  })
  const [draft, setDraft] = useState('')
  const [hasDraft, setHasDraft] = useState(false)
  const [interim, setInterim] = useState('')
  const [pending, setPending] = useState<ChatPending | null>(null)

  /* --- voice output --- */
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [voiceURI, setVoiceURI] = useState(() => readString('memora.voiceURI', ''))
  const [rate, setRate] = useState(() => readNumber('memora.rate', 1))
  const [speaking, setSpeaking] = useState(false)

  const endRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const listeningRef = useRef(false)
  const sendingRef = useRef(false)
  const sessionRef = useRef(false)
  const userStoppedRef = useRef(false)
  const maxTimerRef = useRef<number | null>(null)
  const silenceTimerRef = useRef<number | null>(null)

  const languageOption = getLanguage(language)
  const tamilVoices = voices.filter(voice => /^ta([-_]|$)/i.test(voice.lang))

  async function loadData() {
    try {
      const [m, r, h] = await Promise.all([
        request<Memory[]>('/memories'),
        request<Reminder[]>('/reminders'),
        request<HealthResponse>('/health'),
      ])
      setMemories(m)
      setReminders(r)
      setHealthInfo(h)
      setApiOk(true)
    } catch {
      setApiOk(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy, interim])

  /* --- speech synthesis voices --- */
  useEffect(() => {
    let cancelled = false
    void loadVoices().then(list => {
      if (!cancelled) setVoices(list)
    })
    return () => {
      cancelled = true
    }
  }, [])

  /* --- clean up --- */
  useEffect(() => {
    return () => {
      clearTimers()
      try {
        recognitionRef.current?.abort()
      } catch {
        /* ignore */
      }
      stopSpeaking()
    }
  }, [])

  function clearTimers() {
    if (maxTimerRef.current !== null) {
      window.clearTimeout(maxTimerRef.current)
      maxTimerRef.current = null
    }
    if (silenceTimerRef.current !== null) {
      window.clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }

  function armSilenceTimer() {
    if (silenceTimerRef.current !== null) window.clearTimeout(silenceTimerRef.current)
    silenceTimerRef.current = window.setTimeout(() => {
      if (listeningRef.current) {
        stopListening()
      }
    }, SILENCE_MS)
  }

  function armMaxTimer() {
    if (maxTimerRef.current !== null) window.clearTimeout(maxTimerRef.current)
    maxTimerRef.current = window.setTimeout(() => {
      if (listeningRef.current) {
        setNotice(VOICE_MESSAGES.timeout[language])
        stopListening()
      }
    }, MAX_LISTEN_MS)
  }

  function stopListening() {
    const recognition = recognitionRef.current
    if (!recognition) return
    userStoppedRef.current = true
    try {
      recognition.stop()
    } catch {
      /* ignore */
    }
  }

  function startListening() {
    if (sessionRef.current) return
    const Recognition = getSpeechRecognition()
    if (!Recognition) {
      setNotice(VOICE_MESSAGES.unsupported[language])
      return
    }

    const recognition = new Recognition()
    // For Tanglish, we use ta-IN by default (or en-IN if preferred)
    recognition.lang = languageOption.recLang
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    let finalText = ''
    let lastCombined = ''
    let receivedAnything = false
    let failed = false

    recognition.onstart = () => {
      if (userStoppedRef.current) {
        try {
          recognition.stop()
        } catch {
          /* ignore */
        }
        return
      }
      listeningRef.current = true
      setListening(true)
      setInterim('')
      setDraft('')
      setHasDraft(false)
      setNotice('')
      armMaxTimer()
      armSilenceTimer()
    }

    recognition.onresult = event => {
      receivedAnything = true
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const text = result[0]?.transcript ?? ''
        if (result.isFinal) finalText += text
        else interimText += text
      }
      const combined = `${finalText} ${interimText}`.trim()
      lastCombined = combined
      setInterim(combined)
      setDraft(combined)
      armSilenceTimer()
    }

    recognition.onerror = event => {
      const kind = classifySpeechError(event.error)
      if (kind === 'aborted') return
      failed = true
      setNotice(VOICE_MESSAGES[SPEECH_ERROR_TO_MESSAGE[kind]][language])
    }

    recognition.onend = () => {
      listeningRef.current = false
      sessionRef.current = false
      setListening(false)
      setInterim('')
      clearTimers()

      const captured = (lastCombined || finalText).trim()
      recognitionRef.current = null

      if (!captured && !receivedAnything && !failed && !userStoppedRef.current) {
        setNotice(VOICE_MESSAGES['no-speech'][language])
      }

      userStoppedRef.current = false

      if (captured) {
        if (autoSubmit) {
          // Reliable automatic speech submission
          setDraft('')
          setHasDraft(false)
          void sendMessage(undefined, captured)
        } else {
          setDraft(captured)
          setHasDraft(true)
        }
      }
    }

    recognitionRef.current = recognition
    sessionRef.current = true
    userStoppedRef.current = false
    try {
      recognition.start()
    } catch {
      listeningRef.current = false
      sessionRef.current = false
      recognitionRef.current = null
      setNotice(VOICE_MESSAGES.unsupported[language])
    }
  }

  function discardDraft() {
    setDraft('')
    setHasDraft(false)
  }

  /* --- Speaking the reply aloud --- */
  function speakReply(text: string, replyLanguage?: string) {
    if (!isSpeechSynthesisSupported()) {
      setNotice(VOICE_MESSAGES['no-synthesis'][language])
      return
    }
    const mode = (replyLanguage || modeFor(language)) as 'ta-IN' | 'tanglish' | 'en-IN'
    const voice = pickVoiceForLanguage(voices, mode, voiceURI)
    if (mode === 'ta-IN' && !voice) {
      setNotice(VOICE_MESSAGES['no-tamil-voice'][language])
      return
    }
    const utterance = speak(text, {
      voice,
      rate,
      lang: mode === 'ta-IN' ? 'ta-IN' : 'en-IN',
      onStart: () => setSpeaking(true),
      onEnd: () => setSpeaking(false),
    })
    if (!utterance) setSpeaking(false)
  }

  /* --- Sending a message to MEMORA AI --- */
  async function sendMessage(e?: FormEvent, forced?: string) {
    e?.preventDefault()
    const text = (forced ?? input).trim()
    if (!text) return
    if (sendingRef.current) return
    sendingRef.current = true

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setMessages(prev => [...prev, { role: 'user', text, time: timeStr }])
    if (forced === undefined) setInput('')
    setBusy(true)
    setNotice('')

    try {
      const result = await request<ChatResponse>('/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          language: modeFor(language),
          pending_memory: pending && pending.action === 'save_memory' ? pending.content : undefined,
        }),
      })

      const assistantTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: result.reply,
          time: assistantTime,
          saved: result.saved,
          intent: result.intent,
          mode: result.mode,
        },
      ])
      setPending(result.pending ?? null)

      if (voiceOn) {
        speakReply(result.reply, result.language)
      }
      await loadData()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not reach backend.'
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: `Backend connection error. Please ensure the backend server is running on http://127.0.0.1:8000. Details: ${msg}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ])
    } finally {
      sendingRef.current = false
      setBusy(false)
    }
  }

  function sendCapture() {
    const text = draft.trim()
    if (!text || sendingRef.current) return
    setDraft('')
    setHasDraft(false)
    void sendMessage(undefined, text)
  }

  async function saveMemory(e: FormEvent) {
    e.preventDefault()
    if (!memoryText.trim()) return
    try {
      await request('/memories', {
        method: 'POST',
        body: JSON.stringify({ content: memoryText.trim(), category: 'personal' }),
      })
      setMemoryText('')
      setNotice('Memory saved to SQLite successfully.')
      await loadData()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Could not save memory.')
    }
  }

  async function deleteMemory(id: number) {
    if (!window.confirm('Delete this memory permanently from SQLite?')) return
    try {
      await request(`/memories/${id}`, { method: 'DELETE' })
      setNotice('Memory deleted.')
      await loadData()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Could not delete memory.')
    }
  }

  async function updateMemory(m: Memory) {
    const content = window.prompt('Edit this memory:', m.content)
    if (content === null || !content.trim()) return
    try {
      await request(`/memories/${m.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ content: content.trim(), category: m.category }),
      })
      setNotice('Memory updated in SQLite.')
      await loadData()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Could not update memory.')
    }
  }

  async function addReminder(e: FormEvent) {
    e.preventDefault()
    if (!reminderText.trim()) return
    try {
      await request('/reminders', {
        method: 'POST',
        body: JSON.stringify({ title: reminderText.trim(), due_text: dueText.trim() }),
      })
      setReminderText('')
      setDueText('')
      setNotice('Reminder created.')
      await loadData()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Could not create reminder.')
    }
  }

  async function deleteReminder(id: number) {
    if (!window.confirm('Delete this reminder?')) return
    try {
      await request(`/reminders/${id}`, { method: 'DELETE' })
      await loadData()
      setNotice('Reminder deleted.')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Could not delete reminder.')
    }
  }

  function chooseLanguage(id: LanguageId) {
    setLanguage(id)
    writePref('memora.language', id)
  }

  function toggleVoiceReplies() {
    const next = !voiceOn
    setVoiceOn(next)
    writePref('memora.voiceOn', next)
    if (!next) {
      stopSpeaking()
      setSpeaking(false)
    }
  }

  function toggleAutoSubmit() {
    const next = !autoSubmit
    setAutoSubmit(next)
    writePref('memora.autoSubmit', next)
  }

  const filtered = memories.filter(m =>
    `${m.content} ${m.category}`.toLowerCase().includes(search.toLowerCase())
  )

  const nav = [
    { id: 'chat' as const, label: 'Assistant', icon: MessageCircle },
    { id: 'memories' as const, label: 'My memories', icon: Database },
    { id: 'reminders' as const, label: 'Reminders', icon: Bell },
    { id: 'settings' as const, label: 'Settings', icon: Settings },
  ]

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">
            <Brain size={22} />
          </div>
          <div>
            <strong>
              MEMORA<span> AI</span>
            </strong>
            <small>INTELLIGENT VOICE MEMORY</small>
          </div>
          <button
            className="icon-btn mobile-close"
            onClick={() => setMobileNav(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <button
          className="new-chat"
          onClick={() => {
            setTab('chat')
            setMessages([
              {
                role: 'assistant',
                text: 'New conversation started. What would you like me to remember?',
                time: 'Just now',
              },
            ])
            setMobileNav(false)
          }}
        >
          <Plus size={17} /> New conversation
        </button>

        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(item => (
            <button
              key={item.id}
              className={`nav-item ${tab === item.id ? 'active' : ''}`}
              onClick={() => {
                setTab(item.id)
                setMobileNav(false)
                setNotice('')
              }}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.id === 'memories' && <span className="nav-count">{memories.length}</span>}
              {item.id === 'reminders' && <span className="nav-count">{reminders.length}</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className={`connection-dot ${apiOk ? 'online' : ''}`} />
          <span>{apiOk ? 'SQLite Connected' : 'Backend Disconnected'}</span>
        </div>
      </aside>

      {mobileNav && (
        <button
          className="nav-backdrop"
          onClick={() => setMobileNav(false)}
          aria-label="Close navigation"
        />
      )}

      <main className="main">
        <header className="topbar">
          <button
            className="icon-btn menu-btn"
            onClick={() => setMobileNav(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>
          <div className="crumb">
            Workspace <span>/</span> <b>{nav.find(n => n.id === tab)?.label}</b>
          </div>

          <div className="top-status">
            <span
              className={`status-dot ${
                apiOk ? (healthInfo?.mode === 'ai-error' ? 'error' : 'ok') : ''
              }`}
            />
            {healthInfo?.ai_provider === 'gemini' ? (
              healthInfo.connected ? (
                <span
                  className="status-badge gemini"
                  title={`Powered by Google Gemini (${healthInfo.ai_model || 'Connected'})`}
                >
                  <Sparkles size={13} /> Gemini Connected ({healthInfo.ai_model || 'Active'})
                </span>
              ) : (
                <span
                  className="status-badge error"
                  title={healthInfo.error || healthInfo.message || 'Gemini Connection Issue'}
                >
                  <Zap size={13} /> Gemini Error
                </span>
              )
            ) : healthInfo?.ai_provider === 'openai-compatible' ? (
              <span
                className="status-badge openai"
                title="Connected to OpenAI Compatible Provider"
              >
                <Sparkles size={13} /> OpenAI Compatible
              </span>
            ) : (
              <span className="status-badge local" title="Local offline SQLite memory mode">
                <Zap size={13} /> Local Mode
              </span>
            )}
          </div>
        </header>

        {notice && (
          <div className="notice" role="status">
            <span>{notice}</span>
            <button onClick={() => setNotice('')} aria-label="Dismiss message">
              <X size={15} />
            </button>
          </div>
        )}

        {apiOk === false && (
          <div className="warning">
            <strong>Backend connection unavailable.</strong> Run <code>start.bat</code> or start
            Uvicorn on port 8000, then refresh this page.
          </div>
        )}

        {tab === 'chat' && (
          <section className="chat-page">
            <div className="welcome">
              <div className="eyebrow">
                <Sparkles size={14} /> INTELLIGENT VOICE MEMORY
              </div>
              <h1>
                Your mind,<br />
                <span>remembered.</span>
              </h1>
              <p>
                Natural voice & text conversations in Tamil, Tanglish, and English. Speak your
                deadlines, notes, and tasks just like ChatGPT.
              </p>
            </div>

            <div className="suggestions">
              {[
                'En project deadline Friday nu nyabagam vachiko.',
                'En project deadline eppo?',
                'Naan enna sonnen?',
                'Enna nyabagam vechiruka?',
                'என் ப்ராஜெக்ட் டெட்லைன் வெள்ளிக்கிழமை என்று ஞாபகம் வச்சுக்கோ',
                'Remember that my passport expires in 2028',
              ].map(s => (
                <button key={s} onClick={() => void sendMessage(undefined, s)}>
                  {s} <span>↗</span>
                </button>
              ))}
            </div>

            <div className="chat-feed">
              {messages.map((m, i) => (
                <div key={`${i}-${m.role}`} className={`message ${m.role}`}>
                  <div className="avatar">
                    {m.role === 'assistant' ? <Brain size={17} /> : 'You'}
                  </div>
                  <div className="message-body">
                    <div className="message-header">
                      <span className="message-name">
                        {m.role === 'assistant' ? 'Memora AI' : 'You'}
                      </span>
                      {m.time && <span className="message-time">{m.time}</span>}
                      {m.mode === 'ai-assisted' && (
                        <span className="ai-tag">✨ Gemini AI</span>
                      )}
                      {m.mode === 'local-fallback' && (
                        <span className="local-tag">⚡ Local Mode</span>
                      )}
                      {m.mode === 'ai-error' && (
                        <span className="error-tag">⚠️ AI Error</span>
                      )}
                    </div>
                    <div className="message-text">{m.text}</div>
                    {m.saved && (
                      <div className="saved-memory-pill">
                        <Database size={13} /> Saved to persistent SQLite memory
                      </div>
                    )}
                    {m.role === 'assistant' && (
                      <div className="message-actions">
                        <button
                          type="button"
                          className="msg-action-btn"
                          onClick={() => speakReply(m.text, languageOption.speechLang)}
                          title="Speak response aloud"
                        >
                          <Play size={12} /> Listen
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {busy && (
                <div className="message assistant">
                  <div className="avatar">
                    <Brain size={17} />
                  </div>
                  <div className="message-body">
                    <div className="message-text thinking">
                      <LoaderCircle size={15} className="spin" /> Thinking and checking memory…
                    </div>
                  </div>
                </div>
              )}
              <div ref={endRef} />
            </div>

            {pending && (
              <div className="pending-bar" role="status">
                {pending.action === 'save_memory' ? (
                  <>
                    <span className="pending-text">
                      <b>Confirm save:</b> {pending.content}
                    </span>
                    <span className="pending-actions">
                      <button
                        type="button"
                        className="pending-yes"
                        onClick={() => void sendMessage(undefined, 'yes')}
                      >
                        Yes, save it
                      </button>
                      <button type="button" onClick={() => void sendMessage(undefined, 'no')}>
                        No
                      </button>
                    </span>
                  </>
                ) : (
                  <>
                    <span className="pending-text">
                      <b>Which memory?</b> Pick the memory to delete:
                    </span>
                    <span className="pending-actions">
                      {pending.candidates.map(candidate => (
                        <button
                          key={candidate.id}
                          type="button"
                          onClick={() => void sendMessage(undefined, `delete #${candidate.id}`)}
                        >
                          #{candidate.id} {candidate.content.slice(0, 26)}
                        </button>
                      ))}
                    </span>
                  </>
                )}
              </div>
            )}

            {(listening || hasDraft) && (
              <div
                className={`capture-panel ${listening ? 'recording' : ''}`}
                role="group"
                aria-label="Voice capture"
              >
                <div className="capture-head">
                  <span className="capture-status">
                    {listening ? (
                      <>
                        <span className="rec-dot" /> Listening in {languageOption.label}…{' '}
                        {autoSubmit ? '(Auto-sending on silence)' : ''}
                      </>
                    ) : (
                      'Captured speech transcript'
                    )}
                  </span>
                  <span className="capture-actions">
                    {listening ? (
                      <button type="button" className="stop-btn" onClick={stopListening}>
                        <Square size={12} /> Stop & Send
                      </button>
                    ) : (
                      <>
                        <button type="button" className="ghost-btn" onClick={discardDraft}>
                          Discard
                        </button>
                        <button
                          type="button"
                          className="send-capture"
                          disabled={!draft.trim() || busy}
                          onClick={sendCapture}
                        >
                          <Send size={13} /> Send
                        </button>
                      </>
                    )}
                  </span>
                </div>
                <textarea
                  className="capture-text"
                  value={draft}
                  readOnly={listening}
                  onChange={e => {
                    setDraft(e.target.value)
                    setHasDraft(true)
                  }}
                  placeholder={
                    listening
                      ? 'Speak now in Tamil, Tanglish, or English…'
                      : 'Recognized speech will appear here.'
                  }
                  aria-label="Transcribed speech"
                  rows={2}
                />
                <div className="capture-hint">
                  {listening
                    ? interim
                      ? `Live transcript: ${interim}`
                      : 'Microphone active. Speak naturally.'
                    : 'Edit transcript or click Send.'}
                </div>
              </div>
            )}

            <form className="composer" onSubmit={e => void sendMessage(e)}>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Talk or type to Memora in Tamil, Tanglish, or English…"
                rows={1}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void sendMessage()
                  }
                }}
              />
              <select
                className="lang-select"
                value={language}
                onChange={e => chooseLanguage(e.target.value as LanguageId)}
                aria-label="Voice input language"
                title={languageOption.hint}
              >
                {LANGUAGES.map(option => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className={`voice-btn ${listening ? 'listening' : ''}`}
                onClick={listening ? stopListening : startListening}
                title={listening ? 'Stop listening' : `Speak to Memora (${languageOption.name})`}
                aria-label={
                  listening ? 'Stop listening' : `Start listening in ${languageOption.name}`
                }
                aria-pressed={listening}
              >
                <Mic size={19} />
              </button>
              <button
                type="submit"
                className="send-btn"
                disabled={!input.trim() || busy}
                aria-label="Send message"
              >
                <Send size={18} />
              </button>
            </form>

            <div className="composer-footer">
              <span className="footer-info">
                Press Enter <CornerDownLeft size={11} /> to send • Persistent SQLite memory
              </span>
              <span className="footer-controls">
                {speaking && (
                  <button
                    type="button"
                    className="speaking-chip"
                    onClick={() => {
                      stopSpeaking()
                      setSpeaking(false)
                    }}
                    title="Stop speaking"
                  >
                    <Volume2 size={13} className="spin" /> Speaking… (Click to mute)
                  </button>
                )}
                <button
                  type="button"
                  className={voiceOn ? 'voice-toggle enabled' : 'voice-toggle'}
                  onClick={toggleVoiceReplies}
                  aria-pressed={voiceOn}
                  title="Toggle automatic speech replies"
                >
                  {voiceOn ? <Volume2 size={14} /> : <VolumeX size={14} />}
                  {voiceOn ? 'Voice replies ON' : 'Voice replies OFF'}
                </button>
              </span>
            </div>
          </section>
        )}

        {tab === 'memories' && (
          <section className="content-page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">PERSISTENT SQLITE STORAGE</div>
                <h1>My memories</h1>
                <p>Personal facts, preferences, deadlines, and project notes saved across restarts.</p>
              </div>
              <span className="stat-pill">
                <Database size={15} />
                {memories.length} memories saved
              </span>
            </div>

            <form className="add-form" onSubmit={e => void saveMemory(e)}>
              <input
                value={memoryText}
                onChange={e => setMemoryText(e.target.value)}
                placeholder="Add a new memory manually (e.g. Project deadline is Friday)…"
                maxLength={2000}
              />
              <button className="primary-btn" disabled={!memoryText.trim()}>
                <Plus size={17} /> Save memory
              </button>
            </form>

            <div className="search-box">
              <Search size={17} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search memories in Tamil, Tanglish, or English…"
              />
            </div>

            <div className="memory-list">
              {filtered.map(m => (
                <article className="memory-card" key={m.id}>
                  <div className="memory-icon">
                    <Brain size={18} />
                  </div>
                  <div className="memory-content">
                    <span className="category">{m.category}</span>
                    <p>{m.content}</p>
                    <small>ID #{m.id} • Saved {new Date(m.created_at).toLocaleString()}</small>
                  </div>
                  <div className="memory-actions">
                    <button
                      onClick={() => void updateMemory(m)}
                      aria-label="Edit memory"
                      title="Edit memory"
                    >
                      <Settings size={16} />
                    </button>
                    <button
                      onClick={() => void deleteMemory(m.id)}
                      aria-label="Delete memory"
                      title="Delete memory"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </article>
              ))}
              {filtered.length === 0 && (
                <div className="empty-state">
                  <Database size={28} />
                  <h3>No memories found</h3>
                  <p>Speak to Memora or add a memory using the input box above.</p>
                </div>
              )}
            </div>
          </section>
        )}

        {tab === 'reminders' && (
          <section className="content-page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">TASK TRACKING</div>
                <h1>Reminders</h1>
                <p>Keep your critical deadlines and to-dos organized.</p>
              </div>
              <span className="stat-pill">
                <Bell size={15} />
                {reminders.length} reminders
              </span>
            </div>

            <form className="add-form reminder-form" onSubmit={e => void addReminder(e)}>
              <input
                value={reminderText}
                onChange={e => setReminderText(e.target.value)}
                placeholder="What should I remind you about?"
                maxLength={300}
              />
              <input
                value={dueText}
                onChange={e => setDueText(e.target.value)}
                placeholder="Due date / time (e.g. Friday at 5 PM)"
                maxLength={200}
              />
              <button className="primary-btn" disabled={!reminderText.trim()}>
                <Plus size={17} /> Add reminder
              </button>
            </form>

            <div className="memory-list">
              {reminders.map(r => (
                <article className="memory-card" key={r.id}>
                  <div className="memory-icon">
                    <Bell size={18} />
                  </div>
                  <div className="memory-content">
                    <p>{r.title}</p>
                    <small>{r.due_text ? `Due: ${r.due_text}` : 'No due date specified'}</small>
                  </div>
                  <button
                    className="action-icon"
                    onClick={() => void deleteReminder(r.id)}
                    aria-label="Delete reminder"
                  >
                    <Trash2 size={16} />
                  </button>
                </article>
              ))}
              {reminders.length === 0 && (
                <div className="empty-state">
                  <Bell size={28} />
                  <h3>No reminders yet</h3>
                  <p>Say "Remind me to submit project on Friday" or create one above.</p>
                </div>
              )}
            </div>
          </section>
        )}

        {tab === 'settings' && (
          <section className="content-page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">SYSTEM & PREFERENCES</div>
                <h1>Settings</h1>
                <p>Configure Google Gemini AI brain, speech controls, and database storage.</p>
              </div>
            </div>

            <article className="setting-card">
              <div className="setting-icon">
                <Sparkles size={19} />
              </div>
              <div>
                <h3>AI Brain Provider</h3>
                <p>
                  {healthInfo?.ai_provider === 'gemini'
                    ? healthInfo.connected
                      ? `Google Gemini AI (${healthInfo.ai_model || 'active'}) is connected and actively understanding natural Tamil, Tanglish, and English conversation.`
                      : `Google Gemini AI is configured (${healthInfo.configured_model || healthInfo.ai_model || 'Gemini'}), but encountered an issue: ${healthInfo.error || healthInfo.message}`
                    : healthInfo?.ai_provider === 'openai-compatible'
                    ? `OpenAI-compatible provider (${healthInfo.ai_model}) is active.`
                    : 'Running in Local Offline Mode. To activate Google Gemini, add GEMINI_API_KEY=your_key in backend/.env.'}
                </p>
              </div>
              <span
                className={`setting-badge ${
                  healthInfo?.connected ? 'good' : (healthInfo?.mode === 'ai-error' ? 'error' : '')
                }`}
              >
                {healthInfo?.connected
                  ? 'Gemini Connected'
                  : healthInfo?.mode === 'ai-error'
                  ? 'Gemini Error'
                  : 'Local Fallback'}
              </span>
            </article>

            <article className="setting-card">
              <div className="setting-icon">
                <Mic size={19} />
              </div>
              <div>
                <h3>Automatic Speech Submission</h3>
                <p>
                  When enabled, finishes recording and automatically sends your speech to Memora
                  when you stop talking. Disable if you prefer to review/edit before sending.
                </p>
              </div>
              <button
                type="button"
                className={`switch ${autoSubmit ? 'on' : ''}`}
                onClick={toggleAutoSubmit}
                aria-label="Toggle auto submit"
                aria-pressed={autoSubmit}
              >
                <span />
              </button>
            </article>

            <article className="setting-card">
              <div className="setting-icon">
                <Languages size={19} />
              </div>
              <div>
                <h3>Default Speech Language</h3>
                <p>
                  Choose default voice recognition mode. Tanglish seamlessly understands spoken
                  Tamil mixed with English words.
                </p>
              </div>
              <select
                className="setting-select"
                value={language}
                onChange={e => chooseLanguage(e.target.value as LanguageId)}
                aria-label="Voice input language"
              >
                {LANGUAGES.map(option => (
                  <option key={option.id} value={option.id}>
                    {option.label} — {option.name}
                  </option>
                ))}
              </select>
            </article>

            <article className="setting-card">
              <div className="setting-icon">
                <Volume2 size={19} />
              </div>
              <div>
                <h3>Spoken Voice Replies</h3>
                <p>
                  Read assistant replies aloud automatically using system speech synthesis.
                </p>
              </div>
              <button
                type="button"
                className={`switch ${voiceOn ? 'on' : ''}`}
                onClick={toggleVoiceReplies}
                aria-label="Toggle voice replies"
                aria-pressed={voiceOn}
              >
                <span />
              </button>
            </article>

            <article className="setting-card">
              <div className="setting-icon">
                <AudioLines size={19} />
              </div>
              <div>
                <h3>Speech Synthesis Voice</h3>
                <p>
                  {tamilVoices.length
                    ? `${tamilVoices.length} Tamil voice(s) available on this device.`
                    : 'No Tamil OS voice installed (Tamil replies will show as text).'}
                  {' '}{voices.length} total voices detected.
                </p>
              </div>
              <select
                className="setting-select"
                value={voiceURI}
                onChange={e => {
                  setVoiceURI(e.target.value)
                  writePref('memora.voiceURI', e.target.value)
                }}
                aria-label="Speech voice"
              >
                <option value="">Automatic (Recommended)</option>
                {voices.map(voice => (
                  <option key={voice.voiceURI} value={voice.voiceURI}>
                    {voice.name} ({voice.lang})
                  </option>
                ))}
              </select>
            </article>

            <article className="setting-card">
              <div className="setting-icon">
                <AudioLines size={19} />
              </div>
              <div>
                <h3>Voice Speed Rate: {rate}x</h3>
                <p>Adjust speaking speed for voice responses.</p>
              </div>
              <input
                className="rate-slider"
                type="range"
                min="0.6"
                max="1.5"
                step="0.1"
                value={rate}
                onChange={e => {
                  const next = Number(e.target.value)
                  setRate(next)
                  writePref('memora.rate', next)
                }}
                aria-label="Speech rate"
              />
            </article>

            <article className="setting-card">
              <div className="setting-icon">
                <Database size={19} />
              </div>
              <div>
                <h3>SQLite Database Storage</h3>
                <p>
                  Memories and reminders are persisted in <code>backend/memora.db</code>. They
                  remain safely stored even after system restart.
                </p>
              </div>
              <span className={`setting-badge ${apiOk ? 'good' : ''}`}>
                {apiOk ? 'Connected' : 'Offline'}
              </span>
            </article>

            <div className="privacy-note">
              <strong>
                <Info size={14} /> Configuring Google Gemini API:
              </strong>
              <p>
                To enable Google Gemini reasoning, create a <code>.env</code> file in the{' '}
                <code>backend/</code> folder with:
                <br />
                <code>GEMINI_API_KEY=your_google_gemini_api_key_here</code>
                <br />
                Get your key at{' '}
                <a
                  href="https://aistudio.google.com/"
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: '#a9a1ff' }}
                >
                  Google AI Studio
                </a>
                . Keys are stored securely on your local computer and never exposed to the frontend.
              </p>
            </div>
          </section>
        )}

        <footer className="app-footer">
          <span>
            MEMORA AI <i>•</i> Tamil, Tanglish & English Voice Memory Assistant
          </span>
          <span>SQLite Persistent Memory</span>
        </footer>
      </main>
    </div>
  )
}
