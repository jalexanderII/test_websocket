import { Button } from "@/components/ui/button";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Home } from "lucide-react";
import type { Chat } from "@/types/chat";
import { HomeChatList } from "./HomeChatList";
import { ChatPageList } from "./ChatPageList";

interface ChatSidebarProps {
	chats: Chat[];
	currentChatId: number | null;
	selectMode: boolean;
	selectedChats: Set<number>;
	isConnected: boolean;
	onChatSelect: (chatId: number) => void;
	onToggleSelect: (chatId: number) => void;
	onStartNewChat: () => void;
	onSelectAll: () => void;
	onClearSelection: () => void;
	onDeleteSelected: () => void;
	onToggleSelectMode: () => void;
	onNavigateHome: () => void;
	variant: "home" | "chat";
}

export function ChatSidebar({
	variant,
	onNavigateHome,
	onChatSelect,
	...props
}: ChatSidebarProps) {
	return (
		<div className="w-80 border-r bg-card flex flex-col h-screen">
			<div className="p-4 border-b">
				<Button
					variant="ghost"
					size="icon"
					className="h-6 w-6"
					onClick={onNavigateHome}
				>
					<Home className="h-4 w-4" />
				</Button>
			</div>
			<ErrorBoundary>
				{variant === "home" ? (
					<HomeChatList {...props} onNavigateToChat={onChatSelect} />
				) : (
					<ChatPageList {...props} onLoadAndJoinChat={onChatSelect} />
				)}
			</ErrorBoundary>
		</div>
	);
} 