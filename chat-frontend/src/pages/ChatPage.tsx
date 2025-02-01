import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { CardTitle } from "@/components/ui/card"
import { Send, Trash2, X, Plus, Loader2, Home } from "lucide-react"
import { atom, useAtom } from 'jotai'
import { Checkbox } from "@/components/ui/checkbox"
import useWebSocket, { ReadyState } from 'react-use-websocket'
import { useNavigate, useSearchParams, useParams } from 'react-router-dom'
import type { 
  Message, 
  Chat, 
  APIChat, 
  JsonValue
} from '@/types'

const streamingAtom = atom(false)
const messagesAtom = atom<Message[]>([])
const chatsAtom = atom<Chat[]>([])
const selectedChatsAtom = atom<Set<number>>(new Set<number>())

// Helper function to render structured data
const renderStructuredData = (data: JsonValue): React.ReactNode => {
  if (typeof data !== 'object' || data === null) {
    return String(data);
  }

  if (Array.isArray(data)) {
    return (
      <div className="space-y-1">
        {data.map((item, index) => (
          <div key={`array-item-${index}-${JSON.stringify(item).slice(0, 20)}`} className="pl-2">
            {renderStructuredData(item)}
          </div>
        ))}
      </div>
    );
  }

  return Object.entries(data).map(([key, value]) => (
    <div key={key} className="space-y-1">
      <div className="font-medium capitalize">{key}:</div>
      <div className="pl-2">
        {renderStructuredData(value)}
      </div>
    </div>
  ));
};

export default function ChatPage() {
  const [messages, setMessages] = useAtom(messagesAtom);
  const [chats, setChats] = useAtom(chatsAtom);
  const [selectedChats, setSelectedChats] = useAtom(selectedChatsAtom);
  const [inputMessage, setInputMessage] = useState('');
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  const [isStreaming, setIsStreaming] = useAtom(streamingAtom);
  const [selectMode, setSelectMode] = useState(false);
  const [connectionHealth, setConnectionHealth] = useState<'healthy' | 'unhealthy'>('healthy');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { userId } = useParams();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastPongRef = useRef<number>(Date.now());
  const wsRef = useRef<WebSocket | null>(null);

  const { sendMessage: sendWebSocketMessage, readyState, getWebSocket } = useWebSocket(`ws://localhost:8005/api/ws/${userId}`, {
    onMessage: (event) => {
      setConnectionHealth('healthy');
      lastPongRef.current = Date.now();

      const data = JSON.parse(event.data);
      console.log('[WebSocket] Message received:', data);

      switch (data.type) {
        case 'chat_created': {
          console.log('[WebSocket] Chat created with ID:', data.chat_id);
          setCurrentChatId(data.chat_id);
          const newUrl = new URL(window.location.href);
          newUrl.searchParams.delete('message');
          newUrl.searchParams.set('chat', data.chat_id.toString());
          window.history.replaceState({}, '', newUrl.toString());
          fetchChatHistory();
          break;
        }
        case 'chat_joined': {
          console.log('[WebSocket] Successfully joined chat:', data.chat_id);
          setCurrentChatId(data.chat_id);
          break;
        }
        case 'message': {
          console.log('[WebSocket] Message received:', data.message);
          if (data.message.is_ai && !isStreaming) {
            setIsStreaming(true);
          }
          const newMessage: Message = {
            id: data.message.id,
            chat_id: data.message.chat_id,
            text: data.message.content,
            sender: data.message.is_ai ? 'assistant' : 'user' as const,
            timestamp: data.message.timestamp,
            task_id: data.message.task_id?.toString()
          };
          console.log('[WebSocket] Adding new message to state:', newMessage);
          setMessages(prev => {
            if (prev.some(msg => msg.id === newMessage.id)) {
              console.log('[WebSocket] Message already exists, skipping');
              return prev;
            }
            return [...prev, newMessage];
          });
          break;
        }
        case 'token': {
          console.log('Token received:', data.content);
          if (!isStreaming) {
            setIsStreaming(true);
          }
          if (typeof data.content !== 'string') {
            console.error('Received invalid token type:', typeof data.content, data.content);
            break;
          }
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && 
                lastMessage.sender === 'assistant' && 
                lastMessage.task_id === data.task_id?.toString() &&
                !lastMessage.structured  // Don't append to structured messages
            ) {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                ...lastMessage,
                text: lastMessage.text + data.content
              };
              return newMessages;
            }
            // Create a new streaming message
            return [...prev, {
              id: Date.now(),
              chat_id: data.chat_id,
              text: data.content,
              sender: 'assistant' as const,
              timestamp: new Date().toISOString(),
              task_id: data.task_id?.toString()
            }];
          });
          break;
        }
        case 'structured_response': {
          console.log('Structured response received:', {
            content: data.content,
            metadata: data.metadata,
            task_id: data.task_id
          });
          if (!isStreaming) {
            setIsStreaming(true);
          }
          try {
            const structuredData = JSON.parse(data.content);
            const structuredId = data.metadata?.structured_id;
            console.log('Parsed structured data:', {
              data: structuredData,
              id: structuredId
            });
            
            setMessages(prev => {
              // If we have a structured_id and an existing message with this ID, update it
              if (structuredId) {
                const existingMessageIndex = prev.findIndex(
                  msg => msg.structured && msg.metadata?.structured_id === structuredId
                );
                
                if (existingMessageIndex !== -1) {
                  console.log('Updating existing structured message at index:', existingMessageIndex);
                  const newMessages = [...prev];
                  newMessages[existingMessageIndex] = {
                    ...newMessages[existingMessageIndex],
                    structured: structuredData
                  };
                  return newMessages;
                }
              }
              
              // Otherwise create a new message
              console.log('Creating new structured message');
              const timestamp = new Date().toISOString();
              const newMessage: Message = {
                id: Date.now(),
                chat_id: data.chat_id,
                text: '',
                sender: 'assistant' as const,
                timestamp,
                task_id: data.task_id?.toString(),
                structured: structuredData,
                metadata: data.metadata
              };
              return [...prev, newMessage];
            });
          } catch (error) {
            console.error('Error parsing structured response:', error);
          }
          break;
        }
        case 'task_completed': {
          console.log('Task completed:', data.task_id);
          // If this was an AI response task, stop streaming
          if (data.result && typeof data.result.content === 'string') {
            setIsStreaming(false);
            fetchChatHistory();
          }
          break;
        }
        case 'task_failed': {
          console.error('[WebSocket] Task failed:', data.error);
          setIsStreaming(false);
          // Show error in UI
          setMessages(prev => [...prev, {
            id: Date.now(),
            chat_id: currentChatId || 0,
            text: `Error: ${data.error}`,
            sender: 'assistant',
            timestamp: new Date().toISOString(),
            error: true
          }]);
          break;
        }
        case 'error': {
          console.error('[WebSocket] Error received:', data.message);
          // Show error in UI
          setMessages(prev => [...prev, {
            id: Date.now(),
            chat_id: currentChatId || 0,
            text: `Error: ${data.message}`,
            sender: 'assistant',
            timestamp: new Date().toISOString(),
            error: true
          }]);
          break;
        }
        case 'generation_complete': {
          console.log('Generation completed for task:', data.task_id);
          setIsStreaming(false);
          break;
        }
        default:
          console.warn('Unknown message type:', data.type);
      }
    },
    onOpen: () => {
      console.log('WebSocket connected');
      const ws = getWebSocket();
      if (ws instanceof WebSocket) {
        wsRef.current = ws;
        lastPongRef.current = Date.now();
        setConnectionHealth('healthy');
      }
    },
    onClose: () => {
      console.log('WebSocket disconnected');
      setConnectionHealth('unhealthy');
    },
    onError: (error) => {
      console.error('WebSocket error:', error);
      if (Date.now() - lastPongRef.current > 30000) {
        setConnectionHealth('unhealthy');
      }
    }
  });

  const connected = readyState === ReadyState.OPEN;

  const scrollToBottom = useCallback(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      const container = scrollContainerRef.current;
      if (container) {
        const { scrollTop, scrollHeight, clientHeight } = container;
        const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 100;
        if (isAtBottom) {
          scrollToBottom();
        }
      }
    }
  }, [messages.length, scrollToBottom]);

  const fetchChatHistory = useCallback(async () => {
    try {
      const response = await fetch(`http://localhost:8005/api/users/${userId}/chats`);
      if (!response.ok) throw new Error('Failed to fetch chat history');
      const chats = await response.json();
      const sortedChats = [...chats].sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setChats(sortedChats);
    } catch (error) {
      console.error('Error fetching chat history:', error);
    }
  }, [setChats, userId]);

  const loadChat = useCallback(async (chatId: number) => {
    try {
      console.log('[Chat] Loading chat:', chatId);
      const response = await fetch(`http://localhost:8005/api/chats/${chatId}`);
      if (!response.ok) throw new Error('Failed to fetch chat');
      const chat: APIChat = await response.json();
      console.log('[Chat] Fetched chat data:', chat);
      console.log('[Chat] Raw messages from API:', chat.messages);
      
      // Process messages, ensuring proper content handling
      const formattedMessages: Message[] = chat.messages.map(msg => {
        console.log('[Chat] Processing message:', {
          id: msg.id,
          is_ai: msg.is_ai,
          content_length: msg.content.length,
          content_preview: msg.content.slice(0, 100),
          task_id: msg.task_id
        });
        
        // For AI messages, ensure content is properly handled as a single message
        const content = msg.content;
        
        // If it's a structured response, try to parse it
        if (msg.is_ai && msg.content.startsWith('{') && msg.content.endsWith('}')) {
          try {
            const structured = JSON.parse(msg.content);
            console.log('[Chat] Parsed structured content:', structured);
            return {
              id: msg.id,
              chat_id: msg.chat_id,
              text: '',
              sender: 'assistant',
              timestamp: msg.timestamp,
              task_id: msg.task_id,
              structured
            };
          } catch (e) {
            console.warn('[Chat] Failed to parse structured content:', e);
          }
        }
        
        const message = {
          id: msg.id,
          chat_id: msg.chat_id,
          text: content,
          sender: msg.is_ai ? 'assistant' : 'user' as const,
          timestamp: msg.timestamp,
          task_id: msg.task_id
        };
        console.log('[Chat] Created formatted message:', message);
        return message;
      });
      
      console.log('[Chat] All formatted messages:', formattedMessages);
      setMessages(formattedMessages);
      setCurrentChatId(chatId);

      // Only join the chat if we're connected
      if (connected) {
        console.log('[WebSocket] Sending join_chat message for chat:', chatId);
        sendWebSocketMessage(JSON.stringify({
          action: 'join_chat',
          chat_id: chatId
        }));
      } else {
        console.warn('[WebSocket] Not connected, cannot join chat');
        // Retry joining chat when connection is established
        const retryInterval = setInterval(() => {
          if (connected) {
            console.log('[WebSocket] Connection established, retrying join chat');
            sendWebSocketMessage(JSON.stringify({
              action: 'join_chat',
              chat_id: chatId
            }));
            clearInterval(retryInterval);
          }
        }, 1000);
        // Clear interval after 10 seconds to prevent infinite retries
        setTimeout(() => clearInterval(retryInterval), 10000);
      }
    } catch (error) {
      console.error('[Chat] Error loading chat:', error);
    }
  }, [setMessages, connected, sendWebSocketMessage]);

  // Add logging to message rendering
  const renderMessage = useCallback((message: Message) => {
    console.log('[Chat] Rendering message:', {
      id: message.id,
      sender: message.sender,
      text_length: message.text.length,
      text_preview: message.text.slice(0, 100),
      task_id: message.task_id,
      has_structured: !!message.structured
    });
    
    return (
      <div
        key={`${message.id}-${message.timestamp || Date.now()}`}
        className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
      >
        <div
          className={`
            max-w-[80%] rounded-lg px-4 py-2 break-words relative
            ${message.sender === 'user' 
              ? 'bg-primary text-primary-foreground' 
              : 'bg-muted'
            }
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
  }, []);

  useEffect(() => {
    const chatId = searchParams.get('chat');
    const initialMessage = searchParams.get('message');

    if (initialMessage) {
      if (connected) {
        sendWebSocketMessage(JSON.stringify({ 
          action: 'create_chat',
          user_id: Number(userId),
          initial_message: initialMessage,
          // TODO: Remove
          // pipeline_type: 'planning'
        }));
      }
    } else if (chatId) {
      const parsedChatId = Number.parseInt(chatId, 10);
      if (!Number.isNaN(parsedChatId)) {
        loadChat(parsedChatId);
      }
    }
  }, [connected, loadChat, searchParams, sendWebSocketMessage, userId]);

  const startNewChat = useCallback(() => {
    if (connected) {
      setMessages([]);
      sendWebSocketMessage(JSON.stringify({ 
        action: 'create_chat',
        user_id: Number(userId)
      }));
    }
  }, [setMessages, connected, sendWebSocketMessage, userId]);

  const sendMessage = () => {
    console.log('[Chat] Attempting to send message. Connected:', connected, 'CurrentChatId:', currentChatId);
    if (inputMessage.trim() && connected && currentChatId) {
      console.log('[WebSocket] Sending message to chat:', currentChatId);
      const messageObj = {
        action: 'send_message',
        chat_id: currentChatId,
        content: inputMessage,
        // TODO: Remove
        // pipeline_type: 'planning'
      };
      console.log('[WebSocket] Message object:', messageObj);
      try {
        sendWebSocketMessage(JSON.stringify(messageObj));
        setInputMessage('');
      } catch (error) {
        console.error('[WebSocket] Error sending message:', error);
        setMessages(prev => [...prev, {
          id: Date.now(),
          chat_id: currentChatId,
          text: `Error sending message: ${error}`,
          sender: 'assistant',
          timestamp: new Date().toISOString(),
          error: true
        }]);
      }
    } else if (!currentChatId) {
      console.warn('[Chat] Attempted to send message without active chat');
    } else if (!connected) {
      console.warn('[Chat] Attempted to send message while disconnected');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  useEffect(() => {
    fetchChatHistory();
  }, [fetchChatHistory]);

  const toggleChatSelection = (chatId: number) => {
    setSelectedChats((prev: Set<number>) => {
      const newSet = new Set(prev);
      if (newSet.has(chatId)) {
        newSet.delete(chatId);
      } else {
        newSet.add(chatId);
      }
      return newSet;
    });
  };

  const selectAllChats = () => {
    setSelectedChats(new Set(chats.map(chat => chat.id)));
  };

  const clearSelection = () => {
    setSelectedChats(new Set());
    setSelectMode(false);
  };

  const deleteSelectedChats = async () => {
    try {
      const response = await fetch('http://localhost:8005/api/chats/batch-delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chat_ids: Array.from(selectedChats)
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete chats');
      }

      setChats(prev => prev.filter(chat => !selectedChats.has(chat.id)));
      
      if (currentChatId && selectedChats.has(currentChatId)) {
        setCurrentChatId(null);
        setMessages([]);
        navigate('/');
      }

      clearSelection();
      
      await fetchChatHistory();
    } catch (error) {
      console.error('Error deleting chats:', error);
    }
  };

  const cleanupEmptyChats = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:8005/api/users/1/chats/empty', {
        method: 'DELETE',
      });
      if (response.ok) {
        const result = await response.json();
        if (result.deleted_count > 0) {
          fetchChatHistory();
        }
      }
    } catch (error) {
      console.error('Error cleaning up empty chats:', error);
    }
  }, [fetchChatHistory]);

  useEffect(() => {
    cleanupEmptyChats();
  }, [cleanupEmptyChats]);

  useEffect(() => {
    if (!connected) {
      cleanupEmptyChats();
    }
  }, [connected, cleanupEmptyChats]);

  useEffect(() => {
    if (connected) {
      const pingInterval = setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(new Uint8Array([0x9]).buffer);
          
          const timeSinceLastPong = Date.now() - lastPongRef.current;
          if (timeSinceLastPong > 30000) {
            console.warn(`No messages received in ${Math.round(timeSinceLastPong / 1000)}s, marking connection as unhealthy`);
            setConnectionHealth('unhealthy');
          } else if (connectionHealth === 'unhealthy' && timeSinceLastPong < 30000) {
            setConnectionHealth('healthy');
          }
        }
      }, 15000);

      const handlePong = () => {
        lastPongRef.current = Date.now();
        setConnectionHealth('healthy');
      };

      wsRef.current?.addEventListener('pong', handlePong);

      return () => {
        clearInterval(pingInterval);
        wsRef.current?.removeEventListener('pong', handlePong);
      };
    }
  }, [connected, connectionHealth]);

  return (
    <div className="min-h-screen bg-background flex">
      <div className="w-80 border-r bg-card flex flex-col h-screen">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => navigate('/')}
              >
                <Home className="h-4 w-4" />
              </Button>
              <h2 className="font-semibold text-lg">Chats</h2>
            </div>
            {!selectMode && (
              <Button variant="outline" size="icon" onClick={startNewChat}>
                <Plus className="h-4 w-4" />
              </Button>
            )}
          </div>
          {selectMode && (
            <div className="flex items-center gap-2 mt-2">
              <Button variant="outline" size="sm" className="flex-1" onClick={selectAllChats}>
                Select All
              </Button>
              <Button variant="outline" size="sm" onClick={clearSelection}>
                <X className="h-4 w-4" />
              </Button>
              <Button 
                variant="destructive" 
                size="sm"
                onClick={deleteSelectedChats}
                disabled={selectedChats.size === 0}
              >
                Delete ({selectedChats.size})
              </Button>
            </div>
          )}
          {!selectMode && (
            <Button 
              variant="outline" 
              size="sm"
              className="w-full mt-2"
              onClick={() => setSelectMode(true)}
            >
              Select Chats
            </Button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {chats.map((chat) => (
            <div key={chat.id} className="flex items-center gap-2">
              {selectMode && (
                <Checkbox
                  checked={selectedChats.has(chat.id)}
                  onCheckedChange={() => toggleChatSelection(chat.id)}
                />
              )}
              <Button
                variant={chat.id === currentChatId ? "default" : "outline"}
                className="w-full justify-start"
                onClick={() => !selectMode && loadChat(chat.id)}
              >
                Chat #{chat.id}
                <span className="ml-2 text-xs text-muted-foreground">
                  {new Date(chat.created_at).toLocaleDateString()}
                </span>
              </Button>
              {!selectMode && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleChatSelection(chat.id);
                    setSelectMode(true);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col h-screen">
        <div className="border-b p-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-2xl">Chat Interface</CardTitle>
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
              <div className={`w-2 h-2 rounded-full ${
                !connected ? 'bg-red-500' : 
                connectionHealth === 'healthy' ? 'bg-green-500' : 
                'bg-yellow-400'
              }`} />
              {!connected ? 'Disconnected' : 
               connectionHealth === 'healthy' ? 'Connected' : 
               'Inactive'
              }
              {currentChatId && <span>• Chat #{currentChatId}</span>}
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col p-4 overflow-hidden">
          <div 
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto space-y-4"
          >
            {messages.map(message => renderMessage(message))}
            <div ref={messagesEndRef} />
          </div>

          <div className="mt-4 flex gap-2">
            <Textarea
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder={currentChatId ? "Type your message..." : "Connecting..."}
              disabled={!currentChatId}
              className="min-h-[80px]"
            />
            <Button 
              onClick={sendMessage}
              disabled={!connected || !currentChatId || !inputMessage.trim()}
              variant="default"
              className="px-8 min-w-[100px]"
            >
              <Send className="h-4 w-4 mr-2" />
              Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
} 