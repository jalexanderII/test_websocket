import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Plus, Trash2, X } from "lucide-react";
import type { Chat } from "@/types/chat";

export interface BaseChatListProps {
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
	showNewChatButton?: boolean;
}

export function BaseChatList({
	chats,
	currentChatId,
	selectMode,
	selectedChats,
	isConnected,
	onChatSelect,
	onToggleSelect,
	onStartNewChat,
	onSelectAll,
	onClearSelection,
	onDeleteSelected,
	onToggleSelectMode,
	showNewChatButton = true,
}: BaseChatListProps) {
	return (
		<div className="flex-1 flex flex-col">
			<div className="p-4 border-b">
				<div className="flex items-center justify-between mb-2">
					<h2 className="font-semibold text-lg">Chats</h2>
					{!selectMode && showNewChatButton && (
						<Button
							variant="outline"
							size="icon"
							onClick={onStartNewChat}
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
					<div key={chat.id} className="flex items-center gap-2">
						{selectMode && (
							<Checkbox
								checked={selectedChats.has(chat.id)}
								onCheckedChange={() => onToggleSelect(chat.id)}
							/>
						)}
						<Button
							variant={chat.id === currentChatId ? "secondary" : "outline"}
							className="w-full justify-start"
							onClick={() => !selectMode && onChatSelect(chat.id)}
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
									onToggleSelect(chat.id);
									onToggleSelectMode();
								}}
							>
								<Trash2 className="h-4 w-4" />
							</Button>
						)}
					</div>
				))}
			</div>
		</div>
	);
} 