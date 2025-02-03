import { chatApi } from "@/api/chatApi";
import {
	chatsAtom,
	currentChatIdAtom,
	messagesAtom,
	selectedChatsAtom,
	streamingAtom,
} from "@/store/chat/atoms";
import type { Message } from "@/types/chat";
import type { ConnectionHealth } from "@/types/websocket";
import { formatAPIMessage } from "@/utils/messageFormatters";
import { useAtom } from "jotai";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

export function useChat(userId: string) {
	const navigate = useNavigate();
	const chatCacheRef = useRef<Map<number, { messages: Message[], lastFetched: number }>>(new Map());
	const loadingRef = useRef<Set<number>>(new Set());

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
			// Don't load if already loading
			if (loadingRef.current.has(chatId)) {
				return;
			}

			try {
				// Check cache first
				const cached = chatCacheRef.current.get(chatId);
				const now = Date.now();
				if (cached && (now - cached.lastFetched) < 5000) { // 5 second cache
					setMessages(cached.messages);
					setCurrentChatId(chatId);
					return;
				}

				// Mark as loading
				loadingRef.current.add(chatId);

				const chat = await chatApi.fetchChat(chatId);
				const formattedMessages = chat.messages.map(formatAPIMessage);
				
				// Update cache
				chatCacheRef.current.set(chatId, {
					messages: formattedMessages,
					lastFetched: now
				});

				// Only update state if this is still the current request
				if (loadingRef.current.has(chatId)) {
					setMessages(formattedMessages);
					setCurrentChatId(chatId);
				}
			} catch (error) {
				console.error("Error loading chat:", error);
			} finally {
				loadingRef.current.delete(chatId);
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

			// Clear cache for deleted chats
			for (const chatId of selectedChats) {
				chatCacheRef.current.delete(chatId);
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
