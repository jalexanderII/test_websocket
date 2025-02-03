import type { APIMessage, Message } from "../types/chat";

export function formatAPIMessage(msg: APIMessage): Message {
	// If it's a structured response, try to parse it
	if (msg.is_ai && msg.content.startsWith("{") && msg.content.endsWith("}")) {
		try {
			const structured = JSON.parse(msg.content);
			return {
				id: msg.id,
				chat_id: msg.chat_id,
				text: "",
				sender: "assistant",
				timestamp: msg.timestamp,
				task_id: msg.task_id,
				structured,
			};
		} catch (e) {
			console.warn("[Chat] Failed to parse structured content:", e);
		}
	}

	// Regular message
	return {
		id: msg.id,
		chat_id: msg.chat_id,
		text: msg.content,
		sender: msg.is_ai ? "assistant" : "user",
		timestamp: msg.timestamp,
		task_id: msg.task_id,
	};
}

export function createErrorMessage(chatId: number, error: string): Message {
	return {
		id: Date.now(),
		chat_id: chatId,
		text: `Error: ${error}`,
		sender: "assistant",
		timestamp: new Date().toISOString(),
		error: true,
	};
}

export function createStreamingMessage(
	chatId: number,
	content: string,
	taskId?: string,
): Message {
	return {
		id: Date.now(),
		chat_id: chatId,
		text: content,
		sender: "assistant",
		timestamp: new Date().toISOString(),
		task_id: taskId,
	};
}
