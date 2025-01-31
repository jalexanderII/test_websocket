// API Types (matching backend)
export interface APIMessage {
  id: number;
  chat_id: number;
  content: string;
  is_ai: boolean;
  timestamp: string;
  task_id?: string;
}

export interface APIChat {
  id: number;
  user_id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: APIMessage[];
}

// UI Types
export interface Message {
  id: number;
  chat_id: number;
  text: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  task_id?: string;
  structured?: JsonValue;
}

export interface Chat {
  id: number;
  user_id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
}

// WebSocket message types
export interface CreateChatMessage {
  action: 'create_chat';
  user_id: number;
  initial_message?: string;
}

export interface SendMessagePayload {
  action: 'send_message';
  chat_id: number;
  content: string;
}

export interface JoinChatPayload {
  action: 'join_chat';
  chat_id: number;
}

// Type for handling any JSON value
export type JsonValue = 
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }; 