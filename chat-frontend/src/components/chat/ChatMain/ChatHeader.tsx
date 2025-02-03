import { CardTitle } from "@/components/ui/card";
import type { Chat } from "@/types/chat";
import type { ConnectionHealth } from "@/types/websocket";
import { Loader2 } from "lucide-react";

interface ChatHeaderProps {
	currentChat: Chat | undefined;
	isStreaming: boolean;
	connected: boolean;
	connectionHealth: ConnectionHealth;
}

export function ChatHeader({
	currentChat,
	isStreaming,
	connected,
	connectionHealth,
}: ChatHeaderProps) {
	return (
		<div className="border-b p-4">
			<div className="flex items-center justify-between">
				<CardTitle className="text-2xl">
					{currentChat?.title || "Chat Interface"}
				</CardTitle>
				<div className="flex items-center gap-2 text-sm text-muted-foreground">
					{isStreaming && (
						<>
							<div className="flex items-center gap-1">
								<Loader2 className="h-3 w-3 animate-spin mr-1" />
								Streaming
							</div>
							<span>•</span>
						</>
					)}
					<div
						className={`w-2 h-2 rounded-full ${
							!connected
								? "bg-red-500"
								: connectionHealth === "healthy"
									? "bg-green-500"
									: "bg-yellow-400"
						}`}
					/>
					{!connected
						? "Disconnected"
						: connectionHealth === "healthy"
							? "Connected"
							: "Inactive"}
					{currentChat && <span>• Chat #{currentChat.id}</span>}
				</div>
			</div>
		</div>
	);
}
