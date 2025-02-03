import type { Message } from "@/types/chat";
import { renderStructuredData } from "@/utils/structuredDataRenderer";
import { memo } from "react";

interface MessageItemProps {
	message: Message;
}

export const MessageItem = memo(function MessageItem({
	message,
}: MessageItemProps) {
	return (
		<div
			className={`flex ${message.sender === "user" ? "justify-end" : "justify-start"}`}
		>
			<div
				className={`
          max-w-[80%] rounded-lg px-4 py-2 break-words relative
          ${
						message.sender === "user"
							? "bg-primary text-primary-foreground"
							: "bg-muted"
					}
          ${message.error ? "bg-destructive text-destructive-foreground" : ""}
        `}
			>
				{message.structured ? (
					<div className="space-y-2">
						{renderStructuredData(message.structured)}
					</div>
				) : (
					message.text
				)}
			</div>
		</div>
	);
});
