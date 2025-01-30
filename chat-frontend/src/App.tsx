import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Send, History, Trash2, X, Plus, Loader2 } from "lucide-react"
import { atom, useAtom } from 'jotai'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Checkbox } from "@/components/ui/checkbox"
import useWebSocket, { ReadyState } from 'react-use-websocket'

// API Types (matching backend)
interface APIMessage {
  id: number;
  user_id: string;
  content: string;
  is_ai: boolean;
  timestamp: string;
  task_id?: string;
}

interface APIChat {
  id: number;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: APIMessage[];
}

// UI Types
interface Message {
  id: number;
  text: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  task_id?: string;
  structured?: JsonValue;
}

interface Chat {
  id: number;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

// Type for handling any JSON value
type JsonValue = 
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

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

function App() {
  const [messages, setMessages] = useAtom(messagesAtom);
  const [chats, setChats] = useAtom(chatsAtom);
  const [selectedChats, setSelectedChats] = useAtom(selectedChatsAtom);
  const [inputMessage, setInputMessage] = useState('');
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  const [isStreaming, setIsStreaming] = useAtom(streamingAtom);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [connectionHealth, setConnectionHealth] = useState<'healthy' | 'unhealthy'>('healthy');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastPongRef = useRef<number>(Date.now());
  const wsRef = useRef<WebSocket | null>(null);

  const { sendMessage: sendWebSocketMessage, readyState, getWebSocket } = useWebSocket('ws://localhost:8005/ws/1', {
    onMessage: (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message received:', data);

      switch (data.type) {
        case 'chat_created':
          console.log('Chat created with ID:', data.chat_id);
          setCurrentChatId(data.chat_id);
          fetchChatHistory();
          break;
        case 'message': {
          console.log('Message received:', data.message);
          if (data.message.is_ai && !isStreaming) {
            setIsStreaming(true);
          }
          const newMessage: Message = {
            id: data.message.id,
            text: data.message.content,
            sender: data.message.is_ai ? 'assistant' : 'user',
            timestamp: data.message.timestamp,
            task_id: data.message.task_id
          };
          setMessages(prev => [...prev, newMessage]);
          break;
        }
        case 'structured_token': {
          if (!isStreaming) {
            setIsStreaming(true);
          }
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant' && lastMessage.task_id === data.task_id) {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                ...lastMessage,
                structured: data.data
              };
              return newMessages;
            }
            const timestamp = new Date().toISOString();
            return [...prev, {
              id: Date.now(),
              text: '',
              sender: 'assistant',
              timestamp,
              task_id: data.task_id,
              structured: data.data
            }];
          });
          break;
        }
        case 'token': {
          if (!isStreaming) {
            setIsStreaming(true);
          }
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant' && lastMessage.task_id === data.task_id) {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                ...lastMessage,
                text: lastMessage.text + data.token
              };
              return newMessages;
            }
            const timestamp = new Date().toISOString();
            return [...prev, {
              id: Date.now(),
              text: data.token,
              sender: 'assistant',
              timestamp,
              task_id: data.task_id
            }];
          });
          break;
        }
        case 'error':
          console.error('WebSocket error:', data.message);
          setIsStreaming(false);
          break;
        case 'generation_complete':
          console.log('Generation completed for task:', data.task_id);
          setIsStreaming(false);
          fetchChatHistory();
          break;
        default:
          console.log('Unknown message type:', data.type);
      }
    },
    onOpen: () => {
      const ws = getWebSocket();
      if (ws instanceof WebSocket) {
        wsRef.current = ws;
        lastPongRef.current = Date.now();
        setConnectionHealth('healthy');
      }
    },
    onClose: () => {
      setConnectionHealth('unhealthy');
    },
    onError: () => {
      setConnectionHealth('unhealthy');
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
      const response = await fetch('http://localhost:8005/api/users/1/chats');
      if (!response.ok) throw new Error('Failed to fetch chat history');
      const chats = await response.json();
      // Sort chats by creation date, newest first
      const sortedChats = [...chats].sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setChats(sortedChats);
    } catch (error) {
      console.error('Error fetching chat history:', error);
    }
  }, [setChats]);

  
  const loadChat = useCallback(async (chatId: number) => {
    try {
      const response = await fetch(`http://localhost:8005/api/chats/${chatId}`);
      if (!response.ok) throw new Error('Failed to fetch chat');
      const chat: APIChat = await response.json();
      
      const formattedMessages: Message[] = chat.messages.map(msg => ({
        id: msg.id,
        text: msg.content,
        sender: msg.is_ai ? 'assistant' : 'user',
        timestamp: msg.timestamp,
        task_id: msg.task_id
      }));
      
      setMessages(formattedMessages);
      setIsHistoryOpen(false);

      // Join the chat via WebSocket
      if (connected) {
        sendWebSocketMessage(JSON.stringify({
          action: 'join_chat',
          chat_id: chatId
        }));
        setCurrentChatId(chatId);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  }, [setMessages, connected, sendWebSocketMessage]);

  // Check URL for chat ID on load
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlChatId = params.get('chat');
    if (urlChatId) {
      const chatId = Number.parseInt(urlChatId, 10);
      if (!Number.isNaN(chatId)) {
        loadChat(chatId);
      }
    }
  }, [loadChat]);

  // Create new chat when connected if no chat ID in URL
  useEffect(() => {
    if (connected) {
      const params = new URLSearchParams(window.location.search);
      const urlChatId = params.get('chat');
      if (!urlChatId) {
        sendWebSocketMessage(JSON.stringify({
          action: 'create_chat'
        }));
      }
    }
  }, [connected, sendWebSocketMessage]);

  // Update URL when chat changes
  useEffect(() => {
    if (currentChatId) {
      const newUrl = `${window.location.pathname}?chat=${currentChatId}`;
      window.history.pushState({ chatId: currentChatId }, '', newUrl);
    } else {
      window.history.pushState({}, '', window.location.pathname);
    }
  }, [currentChatId]);

  // Handle browser back/forward
  useEffect(() => {
    const handlePopState = (event: PopStateEvent) => {
      const chatId = event.state?.chatId;
      if (chatId) {
        loadChat(chatId);
      } else {
        // No chat ID in history state, create new chat
        if (connected) {
          sendWebSocketMessage(JSON.stringify({ action: 'create_chat' }));
        }
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [loadChat, connected, sendWebSocketMessage]);

  const startNewChat = useCallback(() => {
    if (connected) {
      setMessages([]);
      sendWebSocketMessage(JSON.stringify({ action: 'create_chat' }));
      setIsHistoryOpen(false);
    }
  }, [setMessages, connected, sendWebSocketMessage]);

  const sendMessage = () => {
    if (inputMessage.trim() && connected && currentChatId) {
      console.log('Sending message to chat:', currentChatId);
      const messageObj = {
        action: 'send_message',
        chat_id: currentChatId,
        content: inputMessage,
      };
      sendWebSocketMessage(JSON.stringify(messageObj));
      setInputMessage('');
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

      // Remove deleted chats from the UI
      setChats(prev => prev.filter(chat => !selectedChats.has(chat.id)));
      
      // If current chat was deleted, clear it
      if (currentChatId && selectedChats.has(currentChatId)) {
        setCurrentChatId(null);
        setMessages([]);
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
          // Refresh chat history if any chats were deleted
          fetchChatHistory();
        }
      }
    } catch (error) {
      console.error('Error cleaning up empty chats:', error);
    }
  }, [fetchChatHistory]);

  // Call cleanup when component mounts and when websocket disconnects
  useEffect(() => {
    cleanupEmptyChats();
  }, [cleanupEmptyChats]);

  useEffect(() => {
    if (!connected) {
      cleanupEmptyChats();
    }
  }, [connected, cleanupEmptyChats]);

  // Setup ping/pong interval
  useEffect(() => {
    if (connected) {
      const pingInterval = setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          // Send ping frame
          wsRef.current.send(new Uint8Array([0x9]).buffer);
          
          // Check if we haven't received a pong in more than 30 seconds
          if (Date.now() - lastPongRef.current > 30000) {
            setConnectionHealth('unhealthy');
          }
        }
      }, 15000);

      // Handle pong responses
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
  }, [connected]);

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <Card className="mx-auto max-w-4xl h-[90vh] flex flex-col">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CardTitle className="text-2xl">Chat Interface</CardTitle>
              <Button variant="outline" size="icon" onClick={startNewChat}>
                <Plus className="h-4 w-4" />
              </Button>
              <Sheet open={isHistoryOpen} onOpenChange={setIsHistoryOpen}>
                <SheetTrigger asChild>
                  <Button variant="outline" size="icon">
                    <History className="h-4 w-4" />
                  </Button>
                </SheetTrigger>
                <SheetContent>
                  <SheetHeader className="flex justify-between items-center">
                    <SheetTitle>Chat History</SheetTitle>
                    <div className="flex items-center gap-2">
                      {selectMode ? (
                        <>
                          <Button variant="outline" size="sm" onClick={selectAllChats}>
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
                        </>
                      ) : (
                        <Button 
                          variant="outline" 
                          size="sm" 
                          onClick={() => setSelectMode(true)}
                        >
                          Select
                        </Button>
                      )}
                    </div>
                  </SheetHeader>
                  <div className="mt-4 space-y-2 pr-4 h-[calc(100vh-8rem)] overflow-y-auto">
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
                </SheetContent>
              </Sheet>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {isStreaming && (
                <>
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    Streaming
                  </div>
                  <span className="text-sm text-muted-foreground">•</span>
                </>
              )}
              <div className={`w-2 h-2 rounded-full ${connected && connectionHealth === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`} />
              {connected ? (connectionHealth === 'healthy' ? 'Connected' : 'Connection Issues') : 'Disconnected'}
              {currentChatId && <span className="text-sm text-muted-foreground">• Chat #{currentChatId}</span>}
            </div>
          </div>
          <Separator />
        </CardHeader>
        
        <CardContent className="flex-1 flex flex-col gap-4 h-full overflow-hidden relative">
          <div 
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto pr-4"
          >
            <div className="space-y-4 pb-4">
              {messages.map((message, index) => (
                <div
                  key={`${message.id || index}-${message.timestamp || Date.now()}`}
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
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="flex gap-2">
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
        </CardContent>
      </Card>
    </div>
  );
}

export default App
