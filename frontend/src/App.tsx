import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Brain, MessageCircle, Database, Bell, Settings, Mic, Send, Plus, Search, Trash2,
  Volume2, Sparkles, Menu, X, Check, LoaderCircle, Square, Languages, AudioLines,
} from 'lucide-react'
import { LANGUAGES, getLanguage, modeFor, isLanguageId, type LanguageId } from './languages'
import {
  classifySpeechError, getSpeechRecognition, isSpeechSynthesisSupported, loadVoices,
  pickVoiceForLanguage, speak, stopSpeaking, hasTamilVoice,
  type SpeechErrorKind, type SpeechRecognitionInstance,
} from './speech'
import type { ChatPending, ChatResponse, Memory, Message, Reminder } from './types'

const API = 'http://127.0.0.1:8000/api'
const MAX_LISTEN_MS = 45000
const SILENCE_MS = 12000

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
/* Preferences stored in the browser                                             */
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
    /* storage is optional - the app still works without it */
  }
}

/* -------------------------------------------------------------------------- */
/* Friendly messages for every supported language                               */
/* -------------------------------------------------------------------------- */

type MessageKind =
  | 'permission' | 'unsupported' | 'no-speech' | 'network' | 'audio' | 'language'
  | 'timeout' | 'silent' | 'no-synthesis' | 'no-tamil-voice' | 'unknown'

const VOICE_MESSAGES: Record<MessageKind, Record<LanguageId, string>> = {
  permission: {
    tamil: 'நுண்ணுறைப் பயன்பாட்டு அனுமதி இல்லை. உலாவை நீக்கி "அனுமதி" கொடுக்கவும்.',
    tanglish: 'Microphone permission illai. Browser settings la "Allow" kodu.',
    english: 'Microphone permission was denied. Please allow microphone access in your browser settings.',
  },
  unsupported: {
    tamil: 'இந்த உலாவில் பேச்சு அடையாளம் இல்லை. சமீபத்திய Chrome அல்லது Edge ஐப் பயன்படுத்துங்கள்.',
    tanglish: 'Indha browser la speech recognition illai. Recent Chrome or Edge use pannunga.',
    english: 'Voice input is not supported in this browser. Try a current version of Chrome or Edge.',
  },
  'no-speech': {
    tamil: 'நீங்கள் ஏதும் பேசவில்லை. மீண்டும் முயற்சி செய்யுங்கள்.',
    tanglish: 'Ningal edhum pesavillai. Meendum muyarchi seyunga.',
    english: "I didn't hear anything. Please try again.",
  },
  network: {
    tamil: 'இணைய வழங்கல் பிழை. பேச்சு அடையாளத்திற்கு இணையம் தேவை.',
    tanglish: 'Internet connection error. Speech recognition ku internet venum.',
    english: 'Network error. Speech recognition needs an internet connection.',
  },
  audio: {
    tamil: 'நுண்ணுறை கிடைக்கவில்லை. உபகரணத்தைச் சரிபார்க்கவும்.',
    tanglish: 'Microphone kidaikkavillai. Device eh check pannunga.',
    english: 'No microphone was found. Please check your audio input device.',
  },
  language: {
    tamil: 'இந்த உலாவில் தமிழ் பேச்சு அடையாளம் இல்லை. வேறு மொழியைத் தேர்ந்தெடுக்கவும்.',
    tanglish: 'Indha browser la Tamil speech recognition illai. Vevi pothu select pannunga.',
    english: 'This browser does not support Tamil speech recognition. Please pick another language.',
  },
  timeout: {
    tamil: 'பதிவு நிறுத்தப்பட்டது. கீழே உள்ள உரையைத் திருத்தி அனுப்பவும்.',
    tanglish: 'Recording stop pannitten. Keezhulla uraikku thiruthi anuppuva.',
    english: 'Recording stopped. You can edit the transcript below before sending it.',
  },
  silent: {
    tamil: 'நீங்கள் சிறிது நேரம் பேசவில்லை, எனவே பதிவு நிறுத்தப்பட்டது.',
    tanglish: 'Ningal konjam neram pesavillai, athukku recording stop pannitten.',
    english: "I didn't hear anything for a while, so I stopped recording.",
  },
  'no-synthesis': {
    tamil: 'இந்த உலாவில் பேசும் தொழில்நுட்பம் இல்லை. பதிலை உரையாகவே படிக்கலாம்.',
    tanglish: 'Indha browser la speech synthesis illai. Pathilai uraikku mattum vaangunga.',
    english: 'This browser cannot read replies aloud. The text is shown below instead.',
  },
  'no-tamil-voice': {
    tamil: 'இந்தச் சாதனத்தில் தமிழ் குரல் இல்லை, எனவே பதில் உரையாகவே காட்டப்படுகிறது.',
    tanglish: 'Indha device la Tamil voice illai, athukku pathilai uraivaaga mattum kattu padikkudhu.',
    english: 'No Tamil voice is installed on this device, so the reply is shown as text.',
  },
  unknown: {
    tamil: 'பேச்சு அடையாளத்தில் ஏதோ தவறு நடந்தது. மீண்டும் முயற்சி செய்யுங்கள்.',
    tanglish: 'Speech recognition la edhu thavaru nadanthu. Meendum muyarchi seyunga.',
    english: 'Something went wrong while listening. Please try again.',
  },
}

/** Maps a browser speech error onto the message catalogue above. */
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
  const [messages, setMessages] = useState<Message[]>([{ role: 'assistant', text: 'Hi! I’m Memora. I can save facts you ask me to remember and retrieve them later. Try: “Remember that my project deadline is Friday.”' }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [memories, setMemories] = useState<Memory[]>([])
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [search, setSearch] = useState('')
  const [memoryText, setMemoryText] = useState('')
  const [reminderText, setReminderText] = useState('')
  const [dueText, setDueText] = useState('')
  const [voiceOn, setVoiceOn] = useState(() => readBool('memora.voiceOn', false))
  const [listening, setListening] = useState(false)
  const [notice, setNotice] = useState('')
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [mobileNav, setMobileNav] = useState(false)

  /* --- voice input ------------------------------------------------------- */
  const [language, setLanguage] = useState<LanguageId>(() => {
    const stored = readString('memora.language', 'tamil')
    return isLanguageId(stored) ? stored : 'tamil'
  })
  const [draft, setDraft] = useState('')
  const [hasDraft, setHasDraft] = useState(false)
  const [interim, setInterim] = useState('')
  const [pending, setPending] = useState<ChatPending | null>(null)

  /* --- voice output ------------------------------------------------------ */
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [voiceURI, setVoiceURI] = useState(() => readString('memora.voiceURI', ''))
  const [rate, setRate] = useState(() => readNumber('memora.rate', 1))
  const [speaking, setSpeaking] = useState(false)

  const endRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const listeningRef = useRef(false)
  const sendingRef = useRef(false)
  // Guards a single microphone session: `sessionRef` is true from the moment a
  // recognition object is created until it ends, so a fast double click can
  // never open two capture sessions at once.
  const sessionRef = useRef(false)
  const userStoppedRef = useRef(false)
  const maxTimerRef = useRef<number | null>(null)
  const silenceTimerRef = useRef<number | null>(null)

  const languageOption = getLanguage(language)
  const tamilVoices = voices.filter(voice => /^ta([-_]|$)/i.test(voice.lang))

  async function loadData() {
    try {
      const [m, r] = await Promise.all([request<Memory[]>('/memories'), request<Reminder[]>('/reminders')])
      setMemories(m); setReminders(r); setApiOk(true)
    } catch { setApiOk(false) }
  }
  useEffect(() => { void loadData() }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  /* --- speech synthesis voices ------------------------------------------- */
  useEffect(() => {
    let cancelled = false
    void loadVoices().then(list => {
      if (!cancelled) setVoices(list)
    })
    return () => { cancelled = true }
  }, [])

  /* --- clean up when the app unmounts ------------------------------------- */
  useEffect(() => {
    return () => {
      clearTimers()
      try { recognitionRef.current?.abort() } catch { /* ignore */ }
      stopSpeaking()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function clearTimers() {
    if (maxTimerRef.current !== null) { window.clearTimeout(maxTimerRef.current); maxTimerRef.current = null }
    if (silenceTimerRef.current !== null) { window.clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null }
  }

  function armSilenceTimer() {
    if (silenceTimerRef.current !== null) window.clearTimeout(silenceTimerRef.current)
    silenceTimerRef.current = window.setTimeout(() => {
      if (listeningRef.current) {
        setNotice(VOICE_MESSAGES.silent[language])
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
    try { recognition.stop() } catch { /* ignore */ }
  }

  function startListening() {
    // Never run two microphone sessions at the same time - a repeated click is
    // ignored instead of opening a second capture session.
    if (sessionRef.current) return
    const Recognition = getSpeechRecognition()
    if (!Recognition) {
      setNotice(VOICE_MESSAGES.unsupported[language])
      return
    }

    const recognition = new Recognition()
    recognition.lang = languageOption.recLang
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    let finalText = ''
    let lastCombined = ''
    let receivedAnything = false
    let failed = false

    recognition.onstart = () => {
      // The user may have pressed Stop while the permission prompt was open.
      if (userStoppedRef.current) {
        try { recognition.stop() } catch { /* ignore */ }
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
      const combined = `${finalText}${interimText}`.trim()
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
      // Keep the last interim words too - the browser sometimes ends the
      // session before the final result is delivered.
      const captured = (lastCombined || finalText).trim()
      if (!captured && !receivedAnything && !failed && !userStoppedRef.current) {
        setNotice(VOICE_MESSAGES['no-speech'][language])
      }
      // The transcript is placed in the editable box - it is never sent
      // automatically.
      setDraft(captured)
      setHasDraft(Boolean(captured))
      recognitionRef.current = null
      userStoppedRef.current = false
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

  /* --- speaking the reply ------------------------------------------------ */
  function speakReply(text: string, replyLanguage: string) {
    if (!isSpeechSynthesisSupported()) {
      setNotice(VOICE_MESSAGES['no-synthesis'][language])
      return
    }
    const mode: 'ta-IN' | 'tanglish' | 'en-IN' =
      replyLanguage === 'ta-IN' || replyLanguage === 'tanglish' ? replyLanguage : 'en-IN'
    const voice = pickVoiceForLanguage(voices, mode, voiceURI)
    if (mode === 'ta-IN' && !voice) {
      // No Tamil voice on this device - the readable text is still shown.
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

  /* --- sending ------------------------------------------------------------ */
  async function sendMessage(e?: FormEvent, forced?: string) {
    e?.preventDefault()
    const text = (forced ?? input).trim()
    if (!text) return
    // Guard against double submits (double click, Enter + button, ...).
    if (sendingRef.current) return
    sendingRef.current = true
    setMessages(prev => [...prev, { role: 'user', text }])
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
      setMessages(prev => [...prev, { role: 'assistant', text: result.reply }])
      setPending(result.pending ?? null)
      if (voiceOn) speakReply(result.reply, result.language)
      await loadData()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not connect to the backend.'
      setMessages(prev => [...prev, { role: 'assistant', text: `I couldn't reach the local server. Please check that the backend is running. Details: ${msg}` }])
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
      await request('/memories', { method: 'POST', body: JSON.stringify({ content: memoryText.trim(), category: 'personal' }) })
      setMemoryText(''); setNotice('Memory saved successfully.'); await loadData()
    } catch (err) { setNotice(err instanceof Error ? err.message : 'Could not save memory.') }
  }
  async function deleteMemory(id: number) {
    if (!window.confirm('Delete this memory permanently?')) return
    try { await request(`/memories/${id}`, { method: 'DELETE' }); setNotice('Memory deleted.'); await loadData() }
    catch (err) { setNotice(err instanceof Error ? err.message : 'Could not delete memory.') }
  }
  async function updateMemory(m: Memory) {
    const content = window.prompt('Edit this memory:', m.content)
    if (content === null || !content.trim()) return
    try { await request(`/memories/${m.id}`, { method: 'PATCH', body: JSON.stringify({ content: content.trim(), category: m.category }) }); setNotice('Memory updated.'); await loadData() }
    catch (err) { setNotice(err instanceof Error ? err.message : 'Could not update memory.') }
  }
  async function addReminder(e: FormEvent) {
    e.preventDefault()
    if (!reminderText.trim()) return
    try {
      await request('/reminders', { method: 'POST', body: JSON.stringify({ title: reminderText.trim(), due_text: dueText.trim() }) })
      setReminderText(''); setDueText(''); setNotice('Reminder created.'); await loadData()
    } catch (err) { setNotice(err instanceof Error ? err.message : 'Could not create reminder.') }
  }
  async function deleteReminder(id: number) {
    if (!window.confirm('Delete this reminder?')) return
    try { await request(`/reminders/${id}`, { method: 'DELETE' }); await loadData(); setNotice('Reminder deleted.') }
    catch (err) { setNotice(err instanceof Error ? err.message : 'Could not delete reminder.') }
  }

  function chooseLanguage(id: LanguageId) {
    setLanguage(id)
    writePref('memora.language', id)
  }

  function toggleVoiceReplies() {
    const next = !voiceOn
    setVoiceOn(next)
    writePref('memora.voiceOn', next)
    if (!next) { stopSpeaking(); setSpeaking(false) }
  }

  const filtered = memories.filter(m => `${m.content} ${m.category}`.toLowerCase().includes(search.toLowerCase()))
  const nav = [
    { id: 'chat' as const, label: 'Assistant', icon: MessageCircle },
    { id: 'memories' as const, label: 'My memories', icon: Database },
    { id: 'reminders' as const, label: 'Reminders', icon: Bell },
    { id: 'settings' as const, label: 'Settings', icon: Settings },
  ]

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Brain size={22}/></div><div><strong>MEMORA<span> AI</span></strong><small>YOUR PERSONAL MEMORY</small></div><button className="icon-btn mobile-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18}/></button></div>
      <button className="new-chat" onClick={() => { setTab('chat'); setMessages([{ role: 'assistant', text: 'New conversation started. What would you like me to remember?' }]); setMobileNav(false) }}><Plus size={17}/> New conversation</button>
      <div className="nav-label">WORKSPACE</div>
      <nav>{nav.map(item => <button key={item.id} className={`nav-item ${tab === item.id ? 'active' : ''}`} onClick={() => { setTab(item.id); setMobileNav(false); setNotice('') }}><item.icon size={18}/><span>{item.label}</span>{item.id === 'memories' && <span className="nav-count">{memories.length}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className={`connection-dot ${apiOk ? 'online' : ''}`}/><span>{apiOk ? 'Local database connected' : 'Backend not connected'}</span></div>
    </aside>
    {mobileNav && <button className="nav-backdrop" onClick={() => setMobileNav(false)} aria-label="Close navigation"/>}
    <main className="main">
      <header className="topbar">
        <button className="icon-btn menu-btn" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20}/></button>
        <div className="crumb">Workspace <span>/</span> <b>{nav.find(n => n.id === tab)?.label}</b></div>
        <div className="top-status"><span className={`status-dot ${apiOk ? 'ok' : ''}`}/>{apiOk ? 'All systems ready' : 'Waiting for backend'}</div>
      </header>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message"><X size={15}/></button></div>}
      {apiOk === false && <div className="warning"><strong>Backend connection unavailable.</strong> Start the backend using the README instructions, then refresh this page.</div>}

      {tab === 'chat' && <section className="chat-page">
        <div className="welcome">
          <div className="eyebrow"><Sparkles size={14}/> PERSONAL AI MEMORY</div>
          <h1>Your mind,<br/><span>remembered.</span></h1>
          <p>A private place for the details you want to keep. Ask, save, and find them when you need them.</p>
        </div>

        <div className="suggestions">
          {['Remember that my project deadline is Friday', 'Enna nyabagam vechirukka?', 'En project deadline Friday'].map(s => <button key={s} onClick={() => void sendMessage(undefined, s)}>{s}<span>↗</span></button>)}
        </div>

        <div className="chat-feed">
          {messages.map((m, i) => <div key={`${i}-${m.role}`} className={`message ${m.role}`}><div className="avatar">{m.role === 'assistant' ? <Brain size={17}/> : 'Y'}</div><div className="message-body"><div className="message-name">{m.role === 'assistant' ? 'Memora' : 'You'}</div><div className="message-text">{m.text}</div></div></div>)}
          {busy && <div className="message assistant"><div className="avatar"><Brain size={17}/></div><div className="message-text thinking"><LoaderCircle size={15}/> Thinking…</div></div>}
          <div ref={endRef}/>
        </div>

        {pending && <div className="pending-bar" role="status">
          {pending.action === 'save_memory' ? (
            <>
              <span className="pending-text"><b>Ready to save:</b> {pending.content}</span>
              <span className="pending-actions">
                <button type="button" className="pending-yes" onClick={() => void sendMessage(undefined, 'yes')}>Yes, save it</button>
                <button type="button" onClick={() => void sendMessage(undefined, 'no')}>No</button>
              </span>
            </>
          ) : (
            <>
              <span className="pending-text"><b>Which memory?</b> Pick the one to delete.</span>
              <span className="pending-actions">
                {pending.candidates.map(candidate => <button key={candidate.id} type="button" onClick={() => void sendMessage(undefined, `delete #${candidate.id}`)}>#{candidate.id} {candidate.content.slice(0, 26)}</button>)}
              </span>
            </>
          )}
        </div>}

        {(listening || hasDraft) && <div className={`capture-panel ${listening ? 'recording' : ''}`} role="group" aria-label="Voice capture">
          <div className="capture-head">
            <span className="capture-status">
              {listening ? <><span className="rec-dot"/> Listening in {languageOption.label}…</> : 'Captured transcript — edit before sending'}
            </span>
            <span className="capture-actions">
              {listening
                ? <button type="button" className="stop-btn" onClick={stopListening}><Square size={12}/> Stop</button>
                : <><button type="button" className="ghost-btn" onClick={discardDraft}>Discard</button><button type="button" className="send-capture" disabled={!draft.trim() || busy} onClick={sendCapture}><Send size={13}/> Send</button></>}
            </span>
          </div>
          <textarea
            className="capture-text"
            value={draft}
            readOnly={listening}
            onChange={e => { setDraft(e.target.value); setHasDraft(true) }}
            placeholder={listening ? 'Speak now…' : 'Your words will appear here. You can correct them before sending.'}
            aria-label="Transcribed speech, editable before sending"
            rows={2}
          />
          <div className="capture-hint">{listening
            ? interim
              ? `Live transcript: ${interim}`
              : 'Listening. Nothing is sent until you press Send.'
            : 'Nothing is sent until you press Send.'}</div>
        </div>}

        <form className="composer" onSubmit={e => void sendMessage(e)}>
          <textarea value={input} onChange={e => setInput(e.target.value)} placeholder="Tell Memora what to remember…" rows={1} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendMessage() } }} />
          <select className="lang-select" value={language} onChange={e => chooseLanguage(e.target.value as LanguageId)} aria-label="Voice input language" title={languageOption.hint}>
            {LANGUAGES.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
          <button type="button" className={`voice-btn ${listening ? 'listening' : ''}`} onClick={listening ? stopListening : startListening} title={listening ? 'Stop listening' : `Speak to Memora (${languageOption.hint})`} aria-label={listening ? 'Stop listening' : `Start listening in ${languageOption.name}`} aria-pressed={listening}><Mic size={19}/></button>
          <button type="submit" className="send-btn" disabled={!input.trim() || busy} aria-label="Send message"><Send size={18}/></button>
        </form>

        <div className="composer-footer">
          <span>Memora uses your local database for saved memories.</span>
          <span className="footer-controls">
            {speaking && <span className="speaking-chip"><Volume2 size={13}/> Speaking…</span>}
            <button type="button" className={voiceOn ? 'voice-toggle enabled' : 'voice-toggle'} onClick={toggleVoiceReplies} aria-pressed={voiceOn}><Volume2 size={14}/>{voiceOn ? 'Voice replies on' : 'Voice replies off'}</button>
          </span>
        </div>
      </section>}

      {tab === 'memories' && <section className="content-page">
        <div className="page-heading"><div><div className="eyebrow">YOUR PERSONAL KNOWLEDGE</div><h1>My memories</h1><p>Facts and notes you choose to keep.</p></div><span className="stat-pill"><Database size={15}/>{memories.length} saved</span></div>
        <form className="add-form" onSubmit={e => void saveMemory(e)}><input value={memoryText} onChange={e => setMemoryText(e.target.value)} placeholder="Add a memory or important note…" maxLength={2000}/><button className="primary-btn" disabled={!memoryText.trim()}><Plus size={17}/> Save memory</button></form>
        <div className="search-box"><Search size={17}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search your memories…"/></div>
        <div className="memory-list">{filtered.map(m => <article className="memory-card" key={m.id}><div className="memory-icon"><Brain size={18}/></div><div className="memory-content"><span className="category">{m.category}</span><p>{m.content}</p><small>Saved {new Date(m.created_at).toLocaleString()}</small></div><div className="memory-actions"><button onClick={() => void updateMemory(m)} aria-label="Edit memory" title="Edit"><Settings size={16}/></button><button onClick={() => void deleteMemory(m.id)} aria-label="Delete memory" title="Delete"><Trash2 size={16}/></button></div></article>)}{filtered.length === 0 && <div className="empty-state"><Database size={28}/><h3>No memories found</h3><p>Save a note above or try a different search.</p></div>}</div>
      </section>}

      {tab === 'reminders' && <section className="content-page">
        <div className="page-heading"><div><div className="eyebrow">STAY ON TRACK</div><h1>Reminders</h1><p>Keep important tasks in one place.</p></div><span className="stat-pill"><Bell size={15}/>{reminders.length} reminders</span></div>
        <form className="add-form reminder-form" onSubmit={e => void addReminder(e)}><input value={reminderText} onChange={e => setReminderText(e.target.value)} placeholder="What should I remind you about?" maxLength={300}/><input value={dueText} onChange={e => setDueText(e.target.value)} placeholder="When? (e.g. Friday)" maxLength={200}/><button className="primary-btn" disabled={!reminderText.trim()}><Plus size={17}/> Add</button></form>
        <div className="memory-list">{reminders.map(r => <article className="memory-card" key={r.id}><div className="memory-icon"><Bell size={18}/></div><div className="memory-content"><p>{r.title}</p><small>{r.due_text || 'No due date added'}</small></div><button className="action-icon" onClick={() => void deleteReminder(r.id)} aria-label="Delete reminder"><Trash2 size={16}/></button></article>)}{reminders.length === 0 && <div className="empty-state"><Bell size={28}/><h3>No reminders yet</h3><p>Add a task you don't want to forget.</p></div>}</div>
      </section>}

      {tab === 'settings' && <section className="content-page">
        <div className="page-heading"><div><div className="eyebrow">PREFERENCES & PRIVACY</div><h1>Settings</h1><p>Understand how Memora stores and uses your data.</p></div></div>

        <article className="setting-card">
          <div className="setting-icon"><Database size={19}/></div>
          <div><h3>Local database</h3><p>Your memories and reminders are saved in a SQLite database on this computer. They persist across backend restarts.</p></div>
          <span className={`setting-badge ${apiOk ? 'good' : ''}`}>{apiOk ? 'Connected' : 'Offline'}</span>
        </article>

        <article className="setting-card">
          <div className="setting-icon"><Languages size={19}/></div>
          <div><h3>Voice input language</h3><p>Choose the language Memora listens in. Tamil uses ta-IN, English uses en-IN. Tanglish has no separate browser code, so the Tamil engine is used as a best effort and the transcript is normalised afterwards.</p></div>
          <select className="setting-select" value={language} onChange={e => chooseLanguage(e.target.value as LanguageId)} aria-label="Voice input language">
            {LANGUAGES.map(option => <option key={option.id} value={option.id}>{option.label} — {option.name}</option>)}
          </select>
        </article>

        <article className="setting-card">
          <div className="setting-icon"><Volume2 size={19}/></div>
          <div><h3>Voice replies</h3><p>When enabled, the browser reads the final assistant reply aloud. Loading messages are never spoken.</p></div>
          <button type="button" className={`switch ${voiceOn ? 'on' : ''}`} onClick={toggleVoiceReplies} aria-label="Toggle voice replies" aria-pressed={voiceOn}><span/></button>
        </article>

        <article className="setting-card">
          <div className="setting-icon"><AudioLines size={19}/></div>
          <div><h3>Speech voice</h3><p>{tamilVoices.length ? `${tamilVoices.length} Tamil voice${tamilVoices.length === 1 ? '' : 's'} available on this device.` : 'No Tamil voice is installed on this device, so Tamil replies are shown as readable text instead.'} {voices.length} voice{voices.length === 1 ? '' : 's'} in total.</p></div>
          <select className="setting-select" value={voiceURI} onChange={e => { setVoiceURI(e.target.value); writePref('memora.voiceURI', e.target.value) }} aria-label="Speech voice">
            <option value="">Automatic (recommended)</option>
            {voices.map(voice => <option key={voice.voiceURI} value={voice.voiceURI}>{voice.name} ({voice.lang})</option>)}
          </select>
        </article>

        <article className="setting-card">
          <div className="setting-icon"><AudioLines size={19}/></div>
          <div><h3>Speech rate</h3><p>How quickly the voice reads replies. 1.0 is the normal speed.</p></div>
          <input className="rate-slider" type="range" min="0.5" max="1.5" step="0.1" value={rate} onChange={e => { const next = Number(e.target.value); setRate(next); writePref('memora.rate', next) }} aria-label="Speech rate"/>
        </article>

        <article className="setting-card">
          <div className="setting-icon"><Mic size={19}/></div>
          <div><h3>Microphone access</h3><p>{typeof window !== 'undefined' && 'SpeechRecognition' in window ? 'Speech recognition is available in this browser. Allow microphone access when prompted.' : 'Speech recognition is not available in this browser. You can still type in the chat and use every memory feature.'}</p></div>
          <span className="setting-badge">{typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) ? 'Available' : 'Text only'}</span>
        </article>

        <article className="setting-card">
          <div className="setting-icon"><Check size={19}/></div>
          <div><h3>AI provider</h3><p>This build uses local deterministic commands for Tamil, Tanglish and English. Advanced generative AI is only used when an operator explicitly configures AI_PROVIDER and AI_API_KEY on the backend.</p></div>
          <span className="setting-badge">Local mode</span>
        </article>

        <div className="privacy-note"><strong>Your control matters.</strong><p>Review memories regularly. Delete anything you no longer want stored. This local prototype is not a substitute for a security-audited production service.</p></div>
        <div className="privacy-note"><strong>About Tanglish pronunciation.</strong><p>Browser voices differ by device and operating system. Tanglish is spoken with English letters, so it is read with an English voice and the result may not match a native speaker exactly. Tanglish speech recognition is best effort - browsers have no dedicated Tanglish model.</p></div>
      </section>}

      <footer className="app-footer"><span>MEMORA AI <i>•</i> Personal memory, on your terms.</span><span>Local-first prototype</span></footer>
    </main>
  </div>
}
