import { initialMessageAtom, pendingMessageAtom } from "@/atoms/chat";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ChatHeader } from "@/components/chat/ChatMain/ChatHeader";
import { ChatInput } from "@/components/chat/ChatMain/ChatInput";
import { MessageList } from "@/components/chat/ChatMain/MessageList";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { useChat } from "@/hooks/useChat";
import { useChatWebSocket } from "@/hooks/useChatWebSocket";
import { useAtomValue, useSetAtom } from "jotai";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useRef } from "react";

export default function ChatPage() {
	const navigate = useNavigate();
	const { userId } = useParams();
	const [searchParams] = useSearchParams();
	const initialMessage = useAtomValue(initialMessageAtom);
	const pendingMessage = useAtomValue(pendingMessageAtom);
	const setInitialMessage = useSetAtom(initialMessageAtom);
	const setPendingMessage = useSetAtom(pendingMessageAtom);

	if (!userId) {
		return <div>User ID is required</div>;
	}

	const {
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
		setIsConnected,
	} = useChat(userId);

	const { isConnected, sendChatMessage, createNewChat, joinChat } =
		useChatWebSocket({
			userId,
			currentChatId,
			setCurrentChatId,
			setMessages,
			setIsStreaming,
			fetchChatHistory,
			setConnectionHealth,
		});

	// Update connection state when WebSocket connection changes
	useEffect(() => {
		setIsConnected(isConnected);
	}, [isConnected, setIsConnected]);

	const handleStartNewChat = () => {
		const message = initialMessage;
		setMessages([]);
		setCurrentChatId(null);
		createNewChat(message || undefined);
		setInitialMessage(null);
		setPendingMessage(null);
	};

	const handleSendMessage = (message: string) => {
		if (message.trim()) {
			sendChatMessage(message);
		}
	};

	// biome-ignore lint/correctness/useExhaustiveDependencies: This effect should only run on URL changes to prevent infinite loops with URL updates
	useEffect(() => {
		const chatId = searchParams.get("chat");

		if (chatId) {
			const parsedChatId = Number.parseInt(chatId, 10);
			if (!Number.isNaN(parsedChatId) && parsedChatId !== currentChatId) {
				// If we have a pending message for this chat, add it to the UI immediately
				if (pendingMessage && pendingMessage.chat_id === parsedChatId) {
					setMessages([pendingMessage]);
					setPendingMessage(null);
				}
				// Load chat first, then join after messages are loaded
				loadChat(parsedChatId).then(() => {
					joinChat(parsedChatId);
				});
			}
		}
	}, [searchParams]);

	// Only update URL if chat ID changes from a user action (not from URL)
	const lastUserActionRef = useRef<number | null>(null);

	const handleChatSelect = (chatId: number) => {
		lastUserActionRef.current = chatId;
		loadChat(chatId).then(() => {
			joinChat(chatId);
		});
	};

	// biome-ignore lint/correctness/useExhaustiveDependencies: This effect updates URL on user-initiated chat changes only
	useEffect(() => {
		if (currentChatId && lastUserActionRef.current === currentChatId) {
			const chatParam = searchParams.get("chat");
			if (!chatParam || Number(chatParam) !== currentChatId) {
				const newSearchParams = new URLSearchParams(searchParams);
				newSearchParams.set("chat", currentChatId.toString());
				navigate(`/users/${userId}/chat?${newSearchParams.toString()}`, {
					replace: true,
				});
			}
		}
	}, [currentChatId]);

	return (
		<div className="min-h-screen bg-background flex">
			<ChatSidebar
				variant="chat"
				chats={chats}
				currentChatId={currentChatId}
				selectMode={selectMode}
				selectedChats={selectedChats}
				isConnected={isConnected}
				onChatSelect={handleChatSelect}
				onToggleSelect={(chatId: number) => {
					const newSet = new Set(selectedChats);
					if (newSet.has(chatId)) {
						newSet.delete(chatId);
					} else {
						newSet.add(chatId);
					}
					setSelectedChats(newSet);
				}}
				onStartNewChat={handleStartNewChat}
				onSelectAll={() => setSelectedChats(new Set(chats.map((c) => c.id)))}
				onClearSelection={() => {
					setSelectedChats(new Set());
					setSelectMode(false);
				}}
				onDeleteSelected={deleteSelectedChats}
				onToggleSelectMode={() => setSelectMode(!selectMode)}
				onNavigateHome={() => navigate("/")}
			/>

			<div className="flex-1 flex flex-col h-screen">
				<ErrorBoundary>
					<ChatHeader
						currentChat={chats.find((c) => c.id === currentChatId)}
						isStreaming={isStreaming}
						connected={isConnected}
						connectionHealth={connectionHealth}
					/>
				</ErrorBoundary>

				<div className="flex-1 flex flex-col p-4 overflow-hidden">
					<ErrorBoundary>
						<MessageList messages={messages} />
					</ErrorBoundary>

					<ErrorBoundary>
						<ChatInput
							disabled={!isConnected || !currentChatId}
							placeholder={
								currentChatId ? "Type your message..." : "Connecting..."
							}
							onSend={handleSendMessage}
						/>
					</ErrorBoundary>
				</div>
			</div>
		</div>
	);
}
