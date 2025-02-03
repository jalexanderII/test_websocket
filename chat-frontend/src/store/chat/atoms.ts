import { atom } from "jotai";
import type { Chat, Message } from "../../types/chat";

export const streamingAtom = atom(false);
export const messagesAtom = atom<Message[]>([]);
export const chatsAtom = atom<Chat[]>([]);
export const selectedChatsAtom = atom<Set<number>>(new Set<number>());
export const currentChatIdAtom = atom<number | null>(null);
