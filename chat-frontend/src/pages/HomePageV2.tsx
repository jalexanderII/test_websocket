import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { initialMessageAtom, pendingMessageAtom } from "@/atoms/chat";
import { useChat } from "@/hooks/useChat";
import { useChatWebSocket } from "@/hooks/useChatWebSocket";
import { Home, Plus, Trash2, X } from "lucide-react";
import { useSetAtom } from "jotai";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

export default function HomePageV2() {
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

	const toggleChatSelection = (chatId: number) => {
		setSelectedChats((prev) => {
			const newSet = new Set(prev);
			if (newSet.has(chatId)) {
				newSet.delete(chatId);
			} else {
				newSet.add(chatId);
			}
			return newSet;
		});
	};

	const selectAllChats = () => {
		setSelectedChats(new Set(chats.map((chat) => chat.id)));
	};

	const clearSelection = () => {
		setSelectedChats(new Set());
		setSelectMode(false);
	};

	return (
		<div className="min-h-screen bg-background flex">
			{/* Sidebar */}
			<div className="w-80 border-r bg-card flex flex-col h-screen">
				<ErrorBoundary>
					<div className="p-4 border-b">
						<div className="flex items-center justify-between mb-2">
							<div className="flex items-center gap-2">
								<Button
									variant="ghost"
									size="icon"
									className="h-6 w-6"
									onClick={() => navigate("/")}
								>
									<Home className="h-4 w-4" />
								</Button>
								<h2 className="font-semibold text-lg">Chats</h2>
							</div>
							{!selectMode && (
								<Button
									variant="outline"
									size="icon"
									onClick={handleStartNewChat}
									disabled={!isConnected}
								>
									<Plus className="h-4 w-4" />
								</Button>
							)}
						</div>
						{selectMode && (
							<div className="flex items-center gap-2 mt-2">
								<Button
									variant="outline"
									size="sm"
									className="flex-1"
									onClick={selectAllChats}
								>
									Select All
								</Button>
								<Button variant="outline" size="sm" onClick={clearSelection}>
									<X className="h-4 w-4" />
								</Button>
								<Button
									variant="destructive"
									size="sm"
									onClick={deleteSelectedChats}
									disabled={selectedChats.size === 0}
								>
									Delete ({selectedChats.size})
								</Button>
							</div>
						)}
						{!selectMode && (
							<Button
								variant="outline"
								size="sm"
								className="w-full mt-2"
								onClick={() => setSelectMode(true)}
							>
								Select Chats
							</Button>
						)}
					</div>
				</ErrorBoundary>

				<ErrorBoundary>
					<div className="flex-1 overflow-y-auto p-4 space-y-2">
						{chats.map((chat) => (
							<div key={chat.id} className="flex items-center gap-2">
								{selectMode && (
									<Checkbox
										checked={selectedChats.has(chat.id)}
										onCheckedChange={() => toggleChatSelection(chat.id)}
									/>
								)}
								<Button
									variant="outline"
									className="w-full justify-start"
									onClick={() => !selectMode && loadChat(chat.id)}
								>
									Chat #{chat.id}
									<span className="ml-2 text-xs text-muted-foreground">
										{new Date(chat.created_at).toLocaleDateString()}
									</span>
								</Button>
								{!selectMode && (
									<Button
										variant="ghost"
										size="icon"
										onClick={(e) => {
											e.stopPropagation();
											toggleChatSelection(chat.id);
											setSelectMode(true);
										}}
									>
										<Trash2 className="h-4 w-4" />
									</Button>
								)}
							</div>
						))}
					</div>
				</ErrorBoundary>
			</div>

			{/* Main Content Area */}
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