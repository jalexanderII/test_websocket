import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Square, Send } from "lucide-react"

interface Message {
  text: string;
  sender: 'user' | 'assistant';
  id?: string;
  timestamp?: string;
  task_id?: string;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [connected, setConnected] = useState(false);
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      scrollToBottom();
    }
  }, [messages.length, scrollToBottom]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8005/ws/1');

    ws.onopen = () => {
      console.log('Connected to WebSocket');
      setConnected(true);
      ws.send(JSON.stringify({
        action: 'create_chat'
      }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('Received WebSocket message:', data);

      switch (data.type) {
        case 'chat_created':
          console.log('Chat created with ID:', data.chat_id);
          setCurrentChatId(data.chat_id);
          break;
        case 'message':
          console.log('Received message:', data.message);
          if (data.message.is_ai) {
            console.log('AI message detected, setting generation state. Task ID:', data.message.task_id);
            setCurrentTaskId(data.message.task_id);
            setIsGenerating(true);
          }
          setMessages(prev => [...prev, {
            text: data.message.content,
            sender: data.message.is_ai ? 'assistant' : 'user',
            id: data.message.id,
            timestamp: data.message.timestamp,
            task_id: data.message.task_id
          }]);
          break;
        case 'token':
          console.log('Received token, isGenerating:', isGenerating);
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.sender === 'assistant') {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1] = {
                ...lastMessage,
                text: lastMessage.text + data.token
              };
              return newMessages;
            }
            return [...prev, {
              text: data.token,
              sender: 'assistant'
            }];
          });
          break;
        case 'generation_complete':
          console.log('Generation complete, resetting state. Task ID:', data.task_id);
          setIsGenerating(false);
          setCurrentTaskId(null);
          break;
        case 'aborted':
          console.log('Generation aborted, resetting state. Task ID:', data.task_id);
          setIsGenerating(false);
          setCurrentTaskId(null);
          break;
        case 'error':
          console.error('WebSocket error:', data.message);
          console.log('Error occurred, resetting generation state');
          setIsGenerating(false);
          setCurrentTaskId(null);
          break;
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected, resetting all states');
      setConnected(false);
      setCurrentChatId(null);
      setIsGenerating(false);
      setCurrentTaskId(null);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, []);

  const sendMessage = () => {
    if (inputMessage.trim() && wsRef.current?.readyState === WebSocket.OPEN && currentChatId) {
      console.log('Sending message to chat:', currentChatId);
      const messageObj = {
        action: 'send_message',
        chat_id: currentChatId,
        content: inputMessage
      };
      wsRef.current.send(JSON.stringify(messageObj));
      setInputMessage('');
    }
  };

  const abortGeneration = () => {
    console.log('Attempting to abort generation. Current task ID:', currentTaskId);
    if (wsRef.current?.readyState === WebSocket.OPEN && currentTaskId) {
      console.log('Sending abort request for task:', currentTaskId);
      const abortObj = {
        action: 'abort',
        task_id: currentTaskId
      };
      wsRef.current.send(JSON.stringify(abortObj));
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Add a log when isGenerating changes
  useEffect(() => {
    console.log('Generation state changed:', { isGenerating, currentTaskId });
  }, [isGenerating, currentTaskId]);

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <Card className="mx-auto max-w-4xl h-[90vh] flex flex-col">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <CardTitle className="text-2xl">Chat Interface</CardTitle>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
              {connected ? 'Connected' : 'Disconnected'}
              {currentChatId && <span className="text-sm text-muted-foreground">• Chat #{currentChatId}</span>}
            </div>
          </div>
          <Separator />
        </CardHeader>
        
        <CardContent className="flex-1 flex flex-col gap-4">
          <ScrollArea className="flex-1 pr-4">
            <div className="space-y-4">
              {messages.map((message, index) => (
                <div
                  key={`${message.id || index}-${message.timestamp || Date.now()}`}
                  className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`
                      max-w-[80%] rounded-lg px-4 py-2
                      ${message.sender === 'user' 
                        ? 'bg-primary text-primary-foreground' 
                        : 'bg-muted'
                      }
                    `}
                  >
                    {message.text}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>

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
              onClick={isGenerating ? abortGeneration : sendMessage}
              disabled={!connected || !currentChatId || (!isGenerating && !inputMessage.trim())}
              variant={isGenerating ? "destructive" : "default"}
              className="px-8 min-w-[100px]"
            >
              {isGenerating ? (
                <Square className="h-4 w-4" />
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  Send
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default App
