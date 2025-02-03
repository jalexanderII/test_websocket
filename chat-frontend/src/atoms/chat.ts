import type { Message } from "@/types/chat";
import { atom } from "jotai";

export const initialMessageAtom = atom<string | null>(null);
export const pendingMessageAtom = atom<Message | null>(null);
export const isCreatingNewChatAtom = atom<boolean>(false);
