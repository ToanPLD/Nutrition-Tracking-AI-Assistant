import { Router } from 'express';
import {
  deleteChatSession,
  getChatMessages,
  getChatSessions,
  sendChatMessage,
  truncateMessagesAfter,
} from './chat.controller';

const chatRouter = Router();

chatRouter.get('/sessions', getChatSessions);
chatRouter.get('/sessions/:sessionId/messages', getChatMessages);
chatRouter.delete('/sessions/:sessionId', deleteChatSession);
chatRouter.delete('/sessions/:sessionId/messages/after/:messageId', truncateMessagesAfter);
chatRouter.post('/message', sendChatMessage);

export default chatRouter;
