import type {
	CreateChatMessage,
	JoinChatPayload,
	SendMessagePayload,
} from "../types/websocket";

export class WebSocketService {
	private static instance: WebSocketService;

	private constructor() {}

	static getInstance(): WebSocketService {
		if (!WebSocketService.instance) {
			WebSocketService.instance = new WebSocketService();
		}
		return WebSocketService.instance;
	}

	createChat(userId: number, initialMessage?: string) {
		const message: CreateChatMessage = {
			action: "create_chat",
			user_id: userId,
			...(initialMessage && { initial_message: initialMessage }),
		};
		return JSON.stringify(message);
	}

	sendMessage(chatId: number, content: string) {
		const message: SendMessagePayload = {
			action: "send_message",
			chat_id: chatId,
			content,
		};
		return JSON.stringify(message);
	}

	joinChat(chatId: number) {
		const message: JoinChatPayload = {
			action: "join_chat",
			chat_id: chatId,
		};
		return JSON.stringify(message);
	}
}
