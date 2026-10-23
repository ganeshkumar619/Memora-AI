/** Shared types for the MEMORA AI frontend. */

export type Message = {
  role: 'assistant' | 'user'
  text: string
  time?: string
  saved?: boolean
  mode?: string
  intent?: string
}

export type Memory = {
  id: number
  content: string
  category: string
  created_at: string
  updated_at?: string
  text?: string
  tag?: string
}

export type Reminder = {
  id: number
  title: string
  due_text: string
  completed: number
  created_at?: string
}

export type PendingCandidate = { id: number; content: string }

export type ChatPending =
  | { action: 'save_memory'; content: string; ambiguous?: boolean }
  | { action: 'delete_memory'; candidates: PendingCandidate[] }

export type ChatResponse = {
  reply: string
  mode: string
  intent: string
  language: string
  detected_language: string
  saved: boolean
  pending: ChatPending | null
  normalized?: string
  ai_provider?: string
  ai_model?: string
  error?: string
}

export type HealthResponse = {
  status: string
  app: string
  version?: string
  languages: string[]
  ai_provider: string
  ai_model?: string
  configured_model?: string
  mode: string
  connected?: boolean
  error?: string
  message?: string
}

