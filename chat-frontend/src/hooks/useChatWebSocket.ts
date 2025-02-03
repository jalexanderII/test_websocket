import { WebSocketService } from "@/services/WebSocketService";
import type { Message } from "@/types/chat";
import type {
	ChatMessage,
	ErrorMessage,
	TaskCompletedMessage,
	TaskFailedMessage,
	TokenMessage,
	WebSocketResponse,
} from "@/types/websocket";
import {
	createErrorMessage,
	createStreamingMessage,
} from "@/utils/messageFormatters";
import { useCallback } from "react";
import { useWebSocketService } from "./useWebSocketService";

interface UseChatWebSocketProps {
	userId: string;
	currentChatId: number | null;
	setCurrentChatId: (id: number | null) => void;
	setMessages: (updater: Message[] | ((prev: Message[]) => Message[])) => void;
	setIsStreaming: (streaming: boolean) => void;
	fetchChatHistory: () => void;
	setConnectionHealth: (health: "healthy" | "unhealthy") => void;
}

export function useChatWebSocket({
	userId,
	currentChatId,
	setCurrentChatId,
	setMessages,
	setIsStreaming,
	fetchChatHistory,
	setConnectionHealth,
}: UseChatWebSocketProps) {
	const ws = WebSocketService.getInstance();

	const handleMessage = useCallback(
		(event: MessageEvent) => {
			const data = JSON.parse(event.data) as WebSocketResponse;
			console.log("[WebSocket] Message received:", data);

			switch (data.type) {
				case "chat_created": {
					console.log("[WebSocket] Chat created with ID:", data.chat_id);
					setCurrentChatId(data.chat_id);
					if (data.message) {
						fetchChatHistory();
					}
					break;
				}
				case "update_title": {
					console.log("[WebSocket] Received title update:", data);
					fetchChatHistory();
					break;
				}
				case "chat_joined": {
					console.log("[WebSocket] Successfully joined chat:", data.chat_id);
					setCurrentChatId(data.chat_id);
					break;
				}
				case "message": {
					const messageData = data as ChatMessage;
					if (messageData.message.is_ai && !messageData.message.structured) {
						setIsStreaming(true);
					}
					setMessages((prev: Message[]) => {
						const isDuplicate = prev.some(msg => 
							msg.id === messageData.message.id || 
							(msg.chat_id === messageData.message.chat_id && 
							 msg.text === messageData.message.content && 
							 msg.sender === (messageData.message.is_ai ? "assistant" : "user"))
						);
						
						if (isDuplicate) {
							return prev;
						}

						return [
							...prev,
							{
								id: messageData.message.id,
								chat_id: messageData.message.chat_id,
								text: messageData.message.content,
								sender: messageData.message.is_ai ? "assistant" : "user",
								timestamp: new Date().toISOString(),
								task_id: messageData.message.task_id?.toString(),
							},
						];
					});
					break;
				}
				case "token": {
					const tokenData = data as TokenMessage;
					if (!tokenData.content || typeof tokenData.content !== "string")
						break;

					if (!tokenData.streaming) {
						setIsStreaming(true);
					}

					setMessages((prev: Message[]) => {
						const lastMessage = prev[prev.length - 1];
						if (
							lastMessage &&
							lastMessage.sender === "assistant" &&
							lastMessage.task_id === tokenData.task_id?.toString() &&
							!lastMessage.structured
						) {
							const newMessages = [...prev];
							newMessages[newMessages.length - 1] = {
								...lastMessage,
								text: lastMessage.text + tokenData.content,
							};
							return newMessages;
						}
						return [
							...prev,
							createStreamingMessage(
								tokenData.chat_id,
								tokenData.content,
								tokenData.task_id,
							),
						];
					});
					break;
				}
				case "task_completed": {
					const completedData = data as TaskCompletedMessage;
					if (completedData.result?.content) {
						setIsStreaming(false);
					}
					break;
				}
				case "task_failed": {
					const failedData = data as TaskFailedMessage;
					setIsStreaming(false);
					setMessages((prev: Message[]) => [
						...prev,
						createErrorMessage(currentChatId || 0, failedData.error),
					]);
					break;
				}
				case "error": {
					const errorData = data as ErrorMessage;
					setMessages((prev: Message[]) => [
						...prev,
						createErrorMessage(currentChatId || 0, errorData.message),
					]);
					break;
				}
				case "generation_complete": {
					setIsStreaming(false);
					break;
				}
			}
		},
		[
			currentChatId,
			setCurrentChatId,
			setMessages,
			setIsStreaming,
			fetchChatHistory,
		],
	);

	const { sendMessage, isConnected } = useWebSocketService(userId, {
		onMessage: handleMessage,
		onOpen: () => setConnectionHealth("healthy"),
		onClose: () => setConnectionHealth("unhealthy"),
		onError: () => setConnectionHealth("unhealthy"),
	});

	const sendChatMessage = useCallback(
		(content: string) => {
			if (isConnected && currentChatId) {
				sendMessage(ws.sendMessage(currentChatId, content));
			}
		},
		[isConnected, currentChatId, sendMessage, ws],
	);

	const createNewChat = useCallback(
		(initialMessage?: string) => {
			if (isConnected) {
				sendMessage(ws.createChat(Number(userId), initialMessage));
			}
		},
		[isConnected, userId, sendMessage, ws],
	);

	const joinChat = useCallback(
		(chatId: number) => {
			if (isConnected) {
				sendMessage(ws.joinChat(chatId));
			}
		},
		[isConnected, sendMessage, ws],
	);

	return {
		isConnected,
		sendChatMessage,
		createNewChat,
		joinChat,
	};
}
