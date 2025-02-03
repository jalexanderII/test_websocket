import { BaseChatList, type BaseChatListProps } from "./BaseChatList";

type ChatPageListProps = Omit<BaseChatListProps, "onChatSelect"> & {
	onLoadAndJoinChat: (chatId: number) => void;
};

export function ChatPageList(props: ChatPageListProps) {
	const { onLoadAndJoinChat, ...rest } = props;
	return (
		<BaseChatList
			{...rest}
			onChatSelect={onLoadAndJoinChat}
		/>
	);
} 