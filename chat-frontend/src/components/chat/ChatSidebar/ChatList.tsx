import { Button } from "@/components/ui/button";
import type { Chat } from "@/types/chat";
import { Plus, X } from "lucide-react";
import { ChatListItem } from "./ChatListItem";

interface ChatListProps {
	chats: Chat[];
	currentChatId: number | null;
	selectMode: boolean;
	selectedChats: Set<number>;
	onChatSelect: (chatId: number) => void;
	onToggleSelect: (chatId: number) => void;
	onStartNewChat: () => void;
	onSelectAll: () => void;
	onClearSelection: () => void;
	onDeleteSelected: () => void;
	onToggleSelectMode: () => void;
}

export function ChatList({
	chats,
	currentChatId,
	selectMode,
	selectedChats,
	onChatSelect,
	onToggleSelect,
	onStartNewChat,
	onSelectAll,
	onClearSelection,
	onDeleteSelected,
	onToggleSelectMode,
}: ChatListProps) {
	return (
		<>
			<div className="p-4 border-b">
				<div className="flex items-center justify-between mb-2">
					<h2 className="font-semibold text-lg">Chats</h2>
					{!selectMode && (
						<Button variant="outline" size="icon" onClick={onStartNewChat}>
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
							onClick={onSelectAll}
						>
							Select All
						</Button>
						<Button variant="outline" size="sm" onClick={onClearSelection}>
							<X className="h-4 w-4" />
						</Button>
						<Button
							variant="destructive"
							size="sm"
							onClick={onDeleteSelected}
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
						onClick={onToggleSelectMode}
					>
						Select Chats
					</Button>
				)}
			</div>
			<div className="flex-1 overflow-y-auto p-4 space-y-2">
				{chats.map((chat) => (
					<ChatListItem
						key={chat.id}
						chat={chat}
						isSelected={selectedChats.has(chat.id)}
						isActive={chat.id === currentChatId}
						selectMode={selectMode}
						onSelect={() => onChatSelect(chat.id)}
						onToggleSelect={() => onToggleSelect(chat.id)}
					/>
				))}
			</div>
		</>
	);
}
