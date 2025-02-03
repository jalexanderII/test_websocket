import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { Chat } from "@/types/chat";
import { Trash2 } from "lucide-react";

interface ChatListItemProps {
	chat: Chat;
	isSelected: boolean;
	isActive: boolean;
	selectMode: boolean;
	onSelect: () => void;
	onToggleSelect: () => void;
}

export function ChatListItem({
	chat,
	isSelected,
	isActive,
	selectMode,
	onSelect,
	onToggleSelect,
}: ChatListItemProps) {
	return (
		<div className="flex items-center gap-2">
			{selectMode && (
				<Checkbox checked={isSelected} onCheckedChange={onToggleSelect} />
			)}
			<Button
				variant={isActive ? "default" : "outline"}
				className="w-full justify-start"
				onClick={() => !selectMode && onSelect()}
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
						onToggleSelect();
					}}
				>
					<Trash2 className="h-4 w-4" />
				</Button>
			)}
		</div>
	);
}
