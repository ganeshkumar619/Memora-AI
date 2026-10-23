/** Language options offered by the MEMORA AI voice controls. */

export type LanguageId = 'tamil' | 'tanglish' | 'english'

export type LanguageOption = {
  id: LanguageId
  /** Short label shown in the compact selector. */
  label: string
  /** Full name shown in Settings. */
  name: string
  /** BCP-47 code handed to the browser SpeechRecognition engine. */
  recLang: string
  /** BCP-47 code preferred when reading the reply aloud. */
  speechLang: string
  /** Longer description used for the title / help text. */
  hint: string
}

export const LANGUAGES: LanguageOption[] = [
  {
    id: 'tamil',
    label: 'தமிழ்',
    name: 'Tamil (தமிழ்)',
    recLang: 'ta-IN',
    speechLang: 'ta-IN',
    hint: 'தமிழ் — Tamil, recognition code ta-IN',
  },
  {
    id: 'tanglish',
    label: 'Tanglish',
    name: 'Tanglish (Tamil spoken with English words)',
    recLang: 'ta-IN',
    speechLang: 'en-IN',
    hint: 'Tanglish — Tamil words spoken with English words. There is no separate browser recognition code, so the Tamil (ta-IN) engine is used as a best effort.',
  },
  {
    id: 'english',
    label: 'English',
    name: 'English (India)',
    recLang: 'en-IN',
    speechLang: 'en-IN',
    hint: 'English — India, recognition code en-IN',
  },
]

const BY_ID: Record<LanguageId, LanguageOption> = LANGUAGES.reduce((acc, option) => {
  acc[option.id] = option
  return acc
}, {} as Record<LanguageId, LanguageOption>)

export function getLanguage(id: LanguageId): LanguageOption {
  return BY_ID[id] ?? BY_ID.english
}

/** The value sent to the backend as `ChatRequest.language`. */
export function modeFor(id: LanguageId): string {
  if (id === 'tamil') return 'ta-IN'
  if (id === 'tanglish') return 'tanglish'
  return 'en-IN'
}

/** The value used to pick a speech synthesis voice for a reply. */
export function speechLangFor(id: LanguageId): string {
  return getLanguage(id).speechLang
}

export function isLanguageId(value: unknown): value is LanguageId {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(BY_ID, value)
}
