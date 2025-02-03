import type { Message } from "@/types/chat";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { VirtualItem } from "@tanstack/react-virtual";
import { useEffect, useMemo, useRef } from "react";
import { MessageItem } from "./MessageItem";

interface MessageListProps {
	messages: Message[];
}

export function MessageList({ messages }: MessageListProps) {
	const scrollContainerRef = useRef<HTMLDivElement>(null);
	const messagesEndRef = useRef<HTMLDivElement>(null);

	// Create virtualizer instance
	const virtualizer = useVirtualizer({
		count: messages.length,
		getScrollElement: () => scrollContainerRef.current,
		estimateSize: () => 100, // Estimate average height of message
		overscan: 5, // Number of items to render outside of viewport
	});

	// Memoize message items to prevent unnecessary re-renders
	const messageItems = useMemo(
		() =>
			virtualizer.getVirtualItems().map((virtualRow: VirtualItem) => {
				const message = messages[virtualRow.index];
				return (
					<div
						key={virtualRow.key}
						data-index={virtualRow.index}
						ref={virtualizer.measureElement}
						style={{
							transform: `translateY(${virtualRow.start}px)`,
							position: "absolute",
							top: 0,
							left: 0,
							width: "100%",
							paddingLeft: "1rem",
							paddingRight: "1rem",
						}}
					>
						<MessageItem
							key={`${message.id}-${message.timestamp || Date.now()}`}
							message={message}
						/>
					</div>
				);
			}),
		[virtualizer, messages],
	);

	// Auto-scroll to bottom when new messages arrive
	useEffect(() => {
		if (messages.length > 0) {
			const container = scrollContainerRef.current;
			if (container) {
				const { scrollTop, scrollHeight, clientHeight } = container;
				const isAtBottom =
					Math.abs(scrollHeight - scrollTop - clientHeight) < 100;
				if (isAtBottom) {
					virtualizer.scrollToIndex(messages.length - 1, {
						align: "end",
						behavior: "smooth",
					});
				}
			}
		}
	}, [messages.length, virtualizer]);

	return (
		<div
			ref={scrollContainerRef}
			className="flex-1 overflow-y-auto relative"
			style={{ height: "100%" }}
		>
			<div
				style={{
					height: `${virtualizer.getTotalSize()}px`,
					width: "100%",
					position: "relative",
				}}
			>
				{messageItems}
			</div>
			<div ref={messagesEndRef} />
		</div>
	);
}
