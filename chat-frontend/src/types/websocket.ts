export interface WebSocketMessage {
	type: string;
	[key: string]: unknown;
}

export interface ChatCreatedMessage extends WebSocketMessage {
	type: "chat_created";
	chat_id: number;
}

export interface UpdateTitleMessage extends WebSocketMessage {
	type: "update_title";
	chat_id: number;
	title: string;
}

export interface ChatJoinedMessage extends WebSocketMessage {
	type: "chat_joined";
	chat_id: number;
}

export interface ChatMessage extends WebSocketMessage {
	type: "message";
	message: {
		id: number;
		chat_id: number;
		content: string;
		is_ai: boolean;
		structured?: boolean;
		task_id?: string;
	};
}

export interface TokenMessage extends WebSocketMessage {
	type: "token";
	chat_id: number;
	content: string;
	task_id?: string;
	streaming?: boolean;
}

export interface TaskCompletedMessage extends WebSocketMessage {
	type: "task_completed";
	task_id: string;
	result?: {
		content: string;
	};
}

export interface TaskFailedMessage extends WebSocketMessage {
	type: "task_failed";
	task_id: string;
	error: string;
}

export interface ErrorMessage extends WebSocketMessage {
	type: "error";
	message: string;
}

export interface GenerationCompleteMessage extends WebSocketMessage {
	type: "generation_complete";
	task_id: string;
}

export type WebSocketResponse =
	| ChatCreatedMessage
	| UpdateTitleMessage
	| ChatJoinedMessage
	| ChatMessage
	| TokenMessage
	| TaskCompletedMessage
	| TaskFailedMessage
	| ErrorMessage
	| GenerationCompleteMessage;

export interface CreateChatMessage {
	action: "create_chat";
	user_id: number;
	initial_message?: string;
}

export interface SendMessagePayload {
	action: "send_message";
	chat_id: number;
	content: string;
}

export interface JoinChatPayload {
	action: "join_chat";
	chat_id: number;
}

export type ConnectionStatus = "connected" | "disconnected" | "connecting";
export type ConnectionHealth = "healthy" | "unhealthy";

export interface WebSocketConfig {
	onMessage: (event: MessageEvent) => void;
	onOpen?: () => void;
	onClose?: () => void;
	onError?: (error: Event) => void;
}
