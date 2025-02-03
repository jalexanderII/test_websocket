import { BaseChatList, type BaseChatListProps } from "./BaseChatList";

type HomeChatListProps = Omit<
	BaseChatListProps,
	"currentChatId" | "onChatSelect"
> & {
	onNavigateToChat: (chatId: number) => void;
};

export function HomeChatList(props: HomeChatListProps) {
	const { onNavigateToChat, ...rest } = props;
	return (
		<BaseChatList
			{...rest}
			currentChatId={null}
			onChatSelect={onNavigateToChat}
			showNewChatButton={false}
		/>
	);
}
