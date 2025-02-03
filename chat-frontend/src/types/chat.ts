import type { JsonValue } from "@/types/json";

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
	sender: "user" | "assistant";
	timestamp: string;
	task_id?: string;
	structured?: JsonValue;
	metadata?: Record<string, JsonValue>;
	error?: boolean;
}

export interface Chat {
	id: number;
	user_id: number;
	title: string | null;
	created_at: string;
	updated_at: string;
}
