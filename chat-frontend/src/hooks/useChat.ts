import { chatApi } from "@/api/chatApi";
import {
	chatsAtom,
	currentChatIdAtom,
	messagesAtom,
	selectedChatsAtom,
	streamingAtom,
} from "@/store/chat/atoms";
import type { ConnectionHealth } from "@/types/websocket";
import { formatAPIMessage } from "@/utils/messageFormatters";
import { useAtom } from "jotai";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export function useChat(userId: string) {
	const navigate = useNavigate();

	const [isStreaming, setIsStreaming] = useAtom(streamingAtom);
	const [messages, setMessages] = useAtom(messagesAtom);
	const [chats, setChats] = useAtom(chatsAtom);
	const [selectedChats, setSelectedChats] = useAtom(selectedChatsAtom);
	const [currentChatId, setCurrentChatId] = useAtom(currentChatIdAtom);

	const [selectMode, setSelectMode] = useState(false);
	const [connectionHealth, setConnectionHealth] =
		useState<ConnectionHealth>("healthy");
	const [isConnected, setIsConnected] = useState(false);

	const fetchChatHistory = useCallback(async () => {
		try {
			const chats = await chatApi.fetchChatHistory(userId);
			setChats(chats);
		} catch (error) {
			console.error("Error fetching chat history:", error);
		}
	}, [userId, setChats]);

	const loadChat = useCallback(
		async (chatId: number) => {
			try {
				const chat = await chatApi.fetchChat(chatId);
				const formattedMessages = chat.messages.map(formatAPIMessage);
				setMessages(formattedMessages);
				setCurrentChatId(chatId);
			} catch (error) {
				console.error("Error loading chat:", error);
			}
		},
		[setMessages, setCurrentChatId],
	);

	const deleteSelectedChats = async () => {
		try {
			await chatApi.deleteChats(Array.from(selectedChats));
			setChats((prev) => prev.filter((chat) => !selectedChats.has(chat.id)));

			if (currentChatId && selectedChats.has(currentChatId)) {
				setCurrentChatId(null);
				setMessages([]);
				navigate("/");
			}

			setSelectedChats(new Set());
			setSelectMode(false);

			await fetchChatHistory();
		} catch (error) {
			console.error("Error deleting chats:", error);
		}
	};

	const cleanupEmptyChats = useCallback(async () => {
		try {
			const result = await chatApi.cleanupEmptyChats(userId);
			if (result.deleted_count > 0) {
				await fetchChatHistory();
			}
		} catch (error) {
			console.error("Error cleaning up empty chats:", error);
			// Don't rethrow - this is a background cleanup task
		}
	}, [userId, fetchChatHistory]);

	// Run cleanup on mount and when connection status changes
	useEffect(() => {
		cleanupEmptyChats();
	}, [cleanupEmptyChats]);

	// Fetch chat history on mount
	useEffect(() => {
		fetchChatHistory();
	}, [fetchChatHistory]);

	useEffect(() => {
		if (!isConnected) {
			cleanupEmptyChats();
		}
	}, [isConnected, cleanupEmptyChats]);

	return {
		isStreaming,
		setIsStreaming,
		messages,
		setMessages,
		chats,
		selectedChats,
		currentChatId,
		selectMode,
		setSelectMode,
		connectionHealth,
		setConnectionHealth,
		loadChat,
		deleteSelectedChats,
		setSelectedChats,
		setCurrentChatId,
		fetchChatHistory,
		isConnected,
		setIsConnected,
	};
}
