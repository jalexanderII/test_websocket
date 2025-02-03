import type { Message } from "@/types";
import { atom } from "jotai";

export const initialMessageAtom = atom<string | null>(null);
export const pendingMessageAtom = atom<Message | null>(null); 