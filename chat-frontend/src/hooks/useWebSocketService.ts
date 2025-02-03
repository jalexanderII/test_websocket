import { useCallback, useRef } from "react";
import useWebSocket, { ReadyState } from "react-use-websocket";
import { WS_BASE_URL } from "../config/constants";
import type { WebSocketConfig } from "../types/websocket";

export function useWebSocketService(userId: string, config: WebSocketConfig) {
	const wsRef = useRef<WebSocket | null>(null);
	const lastPongRef = useRef<number>(Date.now());

	const { sendMessage, readyState, getWebSocket } = useWebSocket(
		`${WS_BASE_URL}/${userId}`,
		{
			onMessage: (event) => {
				lastPongRef.current = Date.now();
				config.onMessage(event);
			},
			onOpen: () => {
				const ws = getWebSocket();
				if (ws instanceof WebSocket) {
					wsRef.current = ws;
					lastPongRef.current = Date.now();
					config.onOpen?.();
				}
			},
			onClose: config.onClose,
			onError: config.onError,
		},
	);

	const sendPing = useCallback(() => {
		if (wsRef.current?.readyState === WebSocket.OPEN) {
			wsRef.current.send(new Uint8Array([0x9]).buffer);
		}
	}, []);

	return {
		sendMessage,
		readyState,
		getWebSocket,
		sendPing,
		isConnected: readyState === ReadyState.OPEN,
		lastPongTime: lastPongRef.current,
		wsRef: wsRef.current,
	};
}
