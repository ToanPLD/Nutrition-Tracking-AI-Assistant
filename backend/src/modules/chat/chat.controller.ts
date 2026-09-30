import { Request, Response, NextFunction } from 'express';
import { chatService } from './chat.service';
import { sendSuccess } from '../../shared/responses/api-response';

export const getChatSessions = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await chatService.getSessions(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const deleteChatSession = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = Number(req.params.sessionId);
    const result = await chatService.deleteSession(req.user!.accountId, sessionId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getChatMessages = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = Number(req.params.sessionId);
    const result = await chatService.getMessages(req.user!.accountId, sessionId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const truncateMessagesAfter = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const sessionId = Number(req.params.sessionId);
    const messageId = Number(req.params.messageId);
    const result = await chatService.truncateMessagesAfter(req.user!.accountId, sessionId, messageId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const sendChatMessage = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await chatService.sendMessage(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Message processed');
  } catch (error) {
    next(error);
  }
};
