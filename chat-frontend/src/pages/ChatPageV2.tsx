import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ChatHeader } from "@/components/chat/ChatMain/ChatHeader";
import { ChatInput } from "@/components/chat/ChatMain/ChatInput";
import { MessageList } from "@/components/chat/ChatMain/MessageList";
import { ChatList } from "@/components/chat/ChatSidebar/ChatList";
import { Button } from "@/components/ui/button";
import { initialMessageAtom, pendingMessageAtom } from "@/atoms/chat";
import { useChat } from "@/hooks/useChat";
import { useChatWebSocket } from "@/hooks/useChatWebSocket";
import { Home } from "lucide-react";
import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

export default function ChatPageV2() {
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

	const handleChatSelect = (chatId: number) => {
		loadChat(chatId);
		joinChat(chatId);
	};

	useEffect(() => {
		const chatId = searchParams.get("chat");

		if (chatId) {
			const parsedChatId = Number.parseInt(chatId, 10);
			if (!Number.isNaN(parsedChatId)) {
				// If we have a pending message for this chat, add it to the UI immediately
				if (pendingMessage && pendingMessage.chat_id === parsedChatId) {
					setMessages([pendingMessage]);
					setPendingMessage(null);
				}
				loadChat(parsedChatId);
				joinChat(parsedChatId);
			}
		}
	}, [searchParams, loadChat, joinChat, setMessages, pendingMessage, setPendingMessage]);

	// Add new effect to handle URL updates when chat ID changes
	useEffect(() => {
		if (currentChatId) {
			const chatParam = searchParams.get("chat");
			if (!chatParam || Number(chatParam) !== currentChatId) {
				const newSearchParams = new URLSearchParams(searchParams);
				newSearchParams.set("chat", currentChatId.toString());
				navigate(`/users/${userId}/chat?${newSearchParams.toString()}`, { replace: true });
			}
		}
	}, [currentChatId, searchParams, userId, navigate]);

	return (
		<div className="min-h-screen bg-background flex">
			<div className="w-80 border-r bg-card flex flex-col h-screen">
				<div className="p-4 border-b">
					<Button
						variant="ghost"
						size="icon"
						className="h-6 w-6"
						onClick={() => navigate("/")}
					>
						<Home className="h-4 w-4" />
					</Button>
				</div>
				<ErrorBoundary>
					<ChatList
						chats={chats}
						currentChatId={currentChatId}
						selectMode={selectMode}
						selectedChats={selectedChats}
						onChatSelect={handleChatSelect}
						onToggleSelect={(chatId) => {
							const newSet = new Set(selectedChats);
							if (newSet.has(chatId)) {
								newSet.delete(chatId);
							} else {
								newSet.add(chatId);
							}
							setSelectedChats(newSet);
						}}
						onStartNewChat={handleStartNewChat}
						onSelectAll={() =>
							setSelectedChats(new Set(chats.map((c) => c.id)))
						}
						onClearSelection={() => {
							setSelectedChats(new Set());
							setSelectMode(false);
						}}
						onDeleteSelected={deleteSelectedChats}
						onToggleSelectMode={() => setSelectMode(!selectMode)}
					/>
				</ErrorBoundary>
			</div>

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
