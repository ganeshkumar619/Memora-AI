/**
 * Thin, typed wrappers around the browser Web Speech APIs.
 *
 * The recognition API is still not part of TypeScript's DOM library, so the
 * small surface that is used here is declared locally.  Nothing in this file
 * touches the network and every helper fails softly when a browser does not
 * support a feature.
 */

/* -------------------------------------------------------------------------- */
/* Minimal typings for the Web Speech recognition API                          */
/* -------------------------------------------------------------------------- */

export interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

export interface SpeechRecognitionErrorEventLike extends Event {
  readonly error: string
  readonly message?: string
}

export interface SpeechRecognitionInstance extends EventTarget {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onstart: ((ev: Event) => unknown) | null
  onend: ((ev: Event) => unknown) | null
  onerror: ((ev: SpeechRecognitionErrorEventLike) => unknown) | null
  onresult: ((ev: SpeechRecognitionEventLike) => unknown) | null
}

export type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance

/* -------------------------------------------------------------------------- */
/* Recognition                                                                  */
/* -------------------------------------------------------------------------- */

/** Returns the SpeechRecognition constructor, or null when unsupported. */
export function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const scope = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return scope.SpeechRecognition || scope.webkitSpeechRecognition || null
}

export function isSpeechRecognitionSupported(): boolean {
  return getSpeechRecognition() !== null
}

export type SpeechErrorKind =
  | 'permission'
  | 'unsupported'
  | 'no-speech'
  | 'network'
  | 'audio'
  | 'language'
  | 'aborted'
  | 'unknown'

/** Maps a browser `SpeechRecognitionError.code` onto a friendly kind. */
export function classifySpeechError(code: string): SpeechErrorKind {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'permission'
    case 'no-speech':
      return 'no-speech'
    case 'audio-capture':
      return 'audio'
    case 'network':
      return 'network'
    case 'language-not-supported':
      return 'language'
    case 'aborted':
      return 'aborted'
    default:
      return 'unknown'
  }
}

/* -------------------------------------------------------------------------- */
/* Synthesis                                                                    */
/* -------------------------------------------------------------------------- */

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * Loads the available voices.  Chrome populates the list asynchronously, so we
 * wait for the `voiceschanged` event and fall back to a timeout.
 */
export function loadVoices(timeoutMs = 1500): Promise<SpeechSynthesisVoice[]> {
  return new Promise(resolve => {
    if (!isSpeechSynthesisSupported()) {
      resolve([])
      return
    }
    const synth = window.speechSynthesis
    const existing = synth.getVoices()
    if (existing.length) {
      resolve(existing)
      return
    }
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      synth.removeEventListener('voiceschanged', finish)
      resolve(synth.getVoices())
    }
    synth.addEventListener('voiceschanged', finish)
    window.setTimeout(finish, timeoutMs)
  })
}

/** True when the device has at least one Tamil voice installed. */
export function hasTamilVoice(voices: SpeechSynthesisVoice[]): boolean {
  return voices.some(voice => /^ta([-_]|$)/i.test(voice.lang))
}

/**
 * Picks the voice used to read a reply.
 *
 * Tamil replies prefer a `ta-IN` voice.  English and Tanglish replies prefer
 * an English voice - Tanglish is written with Latin letters, so an English
 * voice pronounces it far better than a Tamil one.  A manually chosen voice
 * always wins.
 */
export function pickVoice(
  voices: SpeechSynthesisVoice[],
  preferredURI: string,
): SpeechSynthesisVoice | null {
  if (!voices.length) return null
  if (preferredURI) {
    const chosen = voices.find(voice => voice.voiceURI === preferredURI)
    if (chosen) return chosen
  }
  return (
    voices.find(voice => /^en[-_]IN/i.test(voice.lang)) ??
    voices.find(voice => /^en([-_]|$)/i.test(voice.lang)) ??
    voices.find(voice => /^ta([-_]|$)/i.test(voice.lang)) ??
    voices.find(voice => voice.default) ??
    null
  )
}

/** Picks the voice that suits a reply written in a given output language. */
export function pickVoiceForLanguage(
  voices: SpeechSynthesisVoice[],
  language: 'ta-IN' | 'tanglish' | 'en-IN',
  preferredURI: string,
): SpeechSynthesisVoice | null {
  if (!voices.length) return null
  if (preferredURI) {
    const chosen = voices.find(voice => voice.voiceURI === preferredURI)
    if (chosen) return chosen
  }
  if (language === 'ta-IN') {
    return voices.find(voice => /^ta([-_]|$)/i.test(voice.lang)) ?? null
  }
  return (
    voices.find(voice => /^en[-_]IN/i.test(voice.lang)) ??
    voices.find(voice => /^en([-_]|$)/i.test(voice.lang)) ??
    voices.find(voice => voice.default) ??
    null
  )
}

export type SpeakOptions = {
  voice: SpeechSynthesisVoice | null
  rate: number
  lang: string
  onStart?: () => void
  onEnd?: () => void
}

/**
 * Speaks the given text.  Any previous speech is cancelled first so replies
 * never overlap.  Returns the utterance so callers can track its state.
 */
export function speak(text: string, options: SpeakOptions): SpeechSynthesisUtterance | null {
  if (!isSpeechSynthesisSupported() || !text.trim()) return null
  const synth = window.speechSynthesis
  synth.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  if (options.voice) {
    utterance.voice = options.voice
    utterance.lang = options.voice.lang
  } else {
    utterance.lang = options.lang
  }
  utterance.rate = Math.min(2, Math.max(0.5, options.rate))
  utterance.pitch = 1
  utterance.onstart = () => options.onStart?.()
  utterance.onend = () => options.onEnd?.()
  utterance.onerror = () => options.onEnd?.()
  synth.speak(utterance)
  return utterance
}

/** Stops any speech that is currently playing. */
export function stopSpeaking(): void {
  if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel()
}
