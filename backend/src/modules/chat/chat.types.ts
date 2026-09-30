export interface ChatSession {
  sessionId: number;
  startedAt: string;
  title?: string;
  lastMessage?: string;
}

export interface ChatMessage {
  messageId: number;
  sessionId: number;
  sender: 'user' | 'ai';
  messageText: string;
  imageUrl?: string | null;
  imageName?: string | null;
  thinkingSteps?: string[] | null;
  foodInsight?: any | null;
  createdAt: string;
}

export interface SendMessageDto {
  sessionId?: number;
  message: string;
  imageUrl?: string;
  imageName?: string;
}
