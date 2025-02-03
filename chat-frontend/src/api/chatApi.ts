import { API_BASE_URL } from "@/config/constants";
import type { APIChat, Chat } from "@/types/chat";

export const chatApi = {
	async fetchChatHistory(userId: string): Promise<Chat[]> {
		const response = await fetch(`${API_BASE_URL}/users/${userId}/chats`);
		if (!response.ok) throw new Error("Failed to fetch chat history");
		const chats = await response.json();
		return chats.sort(
			(a: Chat, b: Chat) =>
				new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
		);
	},

	async fetchChat(chatId: number): Promise<APIChat> {
		const response = await fetch(`${API_BASE_URL}/chats/${chatId}`);
		if (!response.ok) throw new Error("Failed to fetch chat");
		return response.json();
	},

	async deleteChats(chatIds: number[]): Promise<void> {
		const response = await fetch(`${API_BASE_URL}/chats/batch-delete`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({ chat_ids: chatIds }),
		});

		if (!response.ok) {
			const errorData = await response.json();
			throw new Error(errorData.detail || "Failed to delete chats");
		}
	},

	async cleanupEmptyChats(userId: string): Promise<{ deleted_count: number }> {
		const response = await fetch(
			`${API_BASE_URL}/users/${userId}/chats/empty`,
			{
				method: "DELETE",
				headers: {
					"Content-Type": "application/json",
				},
			},
		);

		if (!response.ok) {
			const errorData = await response
				.json()
				.catch(() => ({ detail: "Failed to cleanup empty chats" }));
			throw new Error(errorData.detail || "Failed to cleanup empty chats");
		}

		return response.json();
	},
};
