import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send } from "lucide-react";
import { useState } from "react";

interface ChatInputProps {
	disabled: boolean;
	placeholder?: string;
	onSend: (message: string) => void;
}

export function ChatInput({ disabled, placeholder, onSend }: ChatInputProps) {
	const [inputMessage, setInputMessage] = useState("");

	const handleSend = () => {
		if (inputMessage.trim()) {
			onSend(inputMessage);
			setInputMessage("");
		}
	};

	const handleKeyPress = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	};

	return (
		<div className="mt-4 flex gap-2">
			<Textarea
				value={inputMessage}
				onChange={(e) => setInputMessage(e.target.value)}
				onKeyDown={handleKeyPress}
				placeholder={placeholder || "Type your message..."}
				disabled={disabled}
				className="min-h-[80px]"
			/>
			<Button
				onClick={handleSend}
				disabled={disabled || !inputMessage.trim()}
				variant="default"
				className="px-8 min-w-[100px]"
			>
				<Send className="h-4 w-4 mr-2" />
				Send
			</Button>
		</div>
	);
}
