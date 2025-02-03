import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import type { Chat } from "@/types";
import { atom, useAtom } from "jotai";
import { Home, Plus, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import useWebSocket, { ReadyState } from "react-use-websocket";

const chatsAtom = atom<Chat[]>([]);
const selectedChatsAtom = atom<Set<number>>(new Set<number>());

export default function HomePage() {
	const [chats, setChats] = useAtom(chatsAtom);
	const [selectedChats, setSelectedChats] = useAtom(selectedChatsAtom);
	const [selectMode, setSelectMode] = useState(false);
	const [inputMessage, setInputMessage] = useState("");
	const navigate = useNavigate();
	const { userId } = useParams();

	const { readyState } = useWebSocket(`ws://localhost:8005/api/ws/${userId}`);
	const connected = readyState === ReadyState.OPEN;

	const fetchChatHistory = useCallback(async () => {
		try {
			const response = await fetch(
				`http://localhost:8005/api/users/${userId}/chats`,
			);
			if (!response.ok) throw new Error("Failed to fetch chat history");
			const chats = await response.json();
			// Sort chats by creation date, newest first
			const sortedChats = [...chats].sort(
				(a, b) =>
					new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
			);
			setChats(sortedChats);
		} catch (error) {
			console.error("Error fetching chat history:", error);
		}
	}, [setChats, userId]);

	useEffect(() => {
		fetchChatHistory();
	}, [fetchChatHistory]);

	const startNewChat = useCallback(
		(initialMessage?: string) => {
			if (connected) {
				const searchParams = new URLSearchParams();
				if (initialMessage) {
					searchParams.set("message", initialMessage);
				}
				navigate(`/users/${userId}/chat?${searchParams.toString()}`);
				setInputMessage(""); // Clear input after sending
			}
		},
		[connected, navigate, userId],
	);

	const handleKeyPress = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" && !e.shiftKey && inputMessage.trim()) {
			e.preventDefault();
			startNewChat(inputMessage.trim());
		}
	};

	const handleSubmit = () => {
		if (inputMessage.trim()) {
			startNewChat(inputMessage.trim());
		}
	};

	const loadChat = useCallback(
		(chatId: number) => {
			navigate(`/users/${userId}/chat?chat=${chatId}`);
		},
		[navigate, userId],
	);

	const toggleChatSelection = (chatId: number) => {
		setSelectedChats((prev: Set<number>) => {
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

	const deleteSelectedChats = async () => {
		try {
			const response = await fetch(
				"http://localhost:8005/api/chats/batch-delete",
				{
					method: "POST",
					headers: {
						"Content-Type": "application/json",
					},
					body: JSON.stringify({
						chat_ids: Array.from(selectedChats),
					}),
				},
			);

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || "Failed to delete chats");
			}

			setChats((prev) => prev.filter((chat) => !selectedChats.has(chat.id)));
			clearSelection();
			await fetchChatHistory();
		} catch (error) {
			console.error("Error deleting chats:", error);
		}
	};

	return (
		<div className="min-h-screen bg-background flex">
			{/* Sidebar */}
			<div className="w-80 border-r bg-card flex flex-col h-screen">
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
								onClick={() => startNewChat()}
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
			</div>

			{/* Main Content Area */}
			<div className="flex-1 flex items-center justify-center p-4">
				<div className="max-w-2xl w-full space-y-4">
					<h1 className="text-4xl font-bold text-center mb-8">
						Chat Interface
					</h1>
					<div className="flex gap-2">
						<Textarea
							value={inputMessage}
							onChange={(e) => setInputMessage(e.target.value)}
							onKeyDown={handleKeyPress}
							placeholder="Type your message to start a new chat..."
							className="min-h-[80px]"
						/>
						<Button
							onClick={handleSubmit}
							disabled={!connected || !inputMessage.trim()}
							className="px-8 min-w-[100px]"
						>
							Start Chat
						</Button>
					</div>
				</div>
			</div>
		</div>
	);
}
