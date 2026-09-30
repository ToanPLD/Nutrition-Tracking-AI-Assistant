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

export const streamChatMessage = async (req: Request, res: Response, next: NextFunction) => {
  try {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders?.();

    const result = await chatService.sendMessageStream(
      req.user!.accountId,
      req.body,
      (chunk: string) => {
        res.write(`data: ${JSON.stringify({ chunk })}\n\n`);
      }
    );

    res.write(
      `data: ${JSON.stringify({
        done: true,
        sessionId: result.sessionId,
        userMessage: result.userMessage,
        aiMessage: result.aiMessage,
      })}\n\n`
    );
    res.write('data: [DONE]\n\n');
    res.end();
  } catch (error) {
    if (!res.headersSent) {
      next(error);
    } else {
      res.write(`data: ${JSON.stringify({ error: (error as any)?.message || 'Stream error' })}\n\n`);
      res.write('data: [DONE]\n\n');
      res.end();
    }
  }
};
