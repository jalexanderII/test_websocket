import { initialMessageAtom, pendingMessageAtom } from "@/atoms/chat";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChat } from "@/hooks/useChat";
import { useChatWebSocket } from "@/hooks/useChatWebSocket";
import { useSetAtom } from "jotai";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

export default function HomePage() {
	const navigate = useNavigate();
	const { userId } = useParams();
	const [inputMessage, setInputMessage] = useState("");
	const setInitialMessage = useSetAtom(initialMessageAtom);
	const setPendingMessage = useSetAtom(pendingMessageAtom);

	if (!userId) {
		return <div>User ID is required</div>;
	}

	const {
		chats,
		selectedChats,
		selectMode,
		setSelectMode,
		setSelectedChats,
		fetchChatHistory,
		deleteSelectedChats,
	} = useChat(userId);

	const { isConnected, createNewChat } = useChatWebSocket({
		userId,
		currentChatId: null,
		setCurrentChatId: (chatId) => {
			if (chatId) {
				if (inputMessage.trim()) {
					setInitialMessage(inputMessage.trim());
					setPendingMessage({
						id: Date.now(),
						chat_id: chatId,
						text: inputMessage.trim(),
						sender: "user",
						timestamp: new Date().toISOString(),
					});
				}
				navigate(`/users/${userId}/chat?chat=${chatId}`);
			}
		},
		setMessages: () => {},
		setIsStreaming: () => {},
		fetchChatHistory,
		setConnectionHealth: () => {},
	});

	const handleStartNewChat = () => {
		if (inputMessage.trim()) {
			createNewChat(inputMessage.trim());
			setInputMessage("");
		} else {
			createNewChat();
		}
	};

	const handleKeyPress = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" && !e.shiftKey && inputMessage.trim()) {
			e.preventDefault();
			handleStartNewChat();
		}
	};

	const loadChat = (chatId: number) => {
		navigate(`/users/${userId}/chat?chat=${chatId}`);
	};

	return (
		<div className="min-h-screen bg-background flex">
			<ChatSidebar
				variant="home"
				chats={chats}
				currentChatId={null}
				selectMode={selectMode}
				selectedChats={selectedChats}
				isConnected={isConnected}
				onChatSelect={loadChat}
				onToggleSelect={(chatId: number) => {
					setSelectedChats((prev) => {
						const newSet = new Set(prev);
						if (newSet.has(chatId)) {
							newSet.delete(chatId);
						} else {
							newSet.add(chatId);
						}
						return newSet;
					});
				}}
				onStartNewChat={handleStartNewChat}
				onSelectAll={() =>
					setSelectedChats(new Set(chats.map((chat) => chat.id)))
				}
				onClearSelection={() => {
					setSelectedChats(new Set());
					setSelectMode(false);
				}}
				onDeleteSelected={deleteSelectedChats}
				onToggleSelectMode={() => setSelectMode(!selectMode)}
				onNavigateHome={() => navigate("/")}
			/>

			<div className="flex-1 flex items-center justify-center p-4">
				<ErrorBoundary>
					<div className="max-w-2xl w-full space-y-4">
						<h1 className="text-2xl font-bold text-center">
							Welcome to the Chat App
						</h1>
						<div className="space-y-2">
							<Textarea
								placeholder="Type a message to start a new chat..."
								value={inputMessage}
								onChange={(e) => setInputMessage(e.target.value)}
								onKeyDown={handleKeyPress}
								className="min-h-[100px]"
								disabled={!isConnected}
							/>
							<Button
								className="w-full"
								onClick={handleStartNewChat}
								disabled={!isConnected}
							>
								Start New Chat
							</Button>
						</div>
					</div>
				</ErrorBoundary>
			</div>
		</div>
	);
}
