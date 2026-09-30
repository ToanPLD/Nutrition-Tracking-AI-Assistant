import { dbQuery, dbQueryOne, dbExecute, dbTransaction } from '../../database/query';
import { NotFoundError } from '../../shared/errors/app-error';
import { profileService } from '../user/services/profile.service';
import { aiProviderService } from './ai-provider.service';
import { SendMessageDto } from './chat.types';

export class ChatService {
  async getSessions(accountId: number) {
    const userId = await profileService.getUserId(accountId);
    const sql = `
      SELECT
        s.session_id,
        s.started_at,
        (
          SELECT message_text
          FROM chatmessages
          WHERE session_id = s.session_id AND sender = 'user'
          ORDER BY message_id ASC
          LIMIT 1
        ) AS title,
        (
          SELECT message_text
          FROM chatmessages
          WHERE session_id = s.session_id
          ORDER BY message_id DESC
          LIMIT 1
        ) AS last_message
      FROM chatsessions s
      WHERE s.user_id = ?
      ORDER BY s.started_at DESC
    `;
    const sessions = await dbQuery<any[]>(sql, [userId]);
    return sessions.map((s) => ({
      sessionId: s.session_id,
      startedAt: s.started_at,
      title: s.title ? (s.title.length > 40 ? s.title.substring(0, 40) + '...' : s.title) : 'New Chat',
      lastMessage: s.last_message || '',
    }));
  }

  async deleteSession(accountId: number, sessionId: number) {
    const userId = await profileService.getUserId(accountId);
    const session = await dbQueryOne<any>(
      'SELECT session_id FROM chatsessions WHERE session_id = ? AND user_id = ? LIMIT 1',
      [sessionId, userId]
    );

    if (!session) {
      throw new NotFoundError('Session not found');
    }

    await dbExecute('DELETE FROM chatsessions WHERE session_id = ?', [sessionId]);
    return { success: true, message: 'Chat session deleted' };
  }

  async getMessages(accountId: number, sessionId: number) {
    const userId = await profileService.getUserId(accountId);
    const session = await dbQueryOne<any>(
      'SELECT session_id FROM chatsessions WHERE session_id = ? AND user_id = ? LIMIT 1',
      [sessionId, userId]
    );

    if (!session) {
      throw new NotFoundError('Session not found');
    }

    const sql = `
      SELECT
        message_id,
        session_id,
        sender,
        message_text,
        image_url,
        image_name,
        thinking_steps,
        food_insight,
        created_at
      FROM chatmessages
      WHERE session_id = ?
      ORDER BY message_id ASC
    `;
    const rows = await dbQuery<any[]>(sql, [sessionId]);
    return rows.map((r) => ({
      messageId: r.message_id,
      sessionId: r.session_id,
      sender: r.sender,
      messageText: r.message_text,
      imageUrl: r.image_url,
      imageName: r.image_name,
      thinkingSteps: typeof r.thinking_steps === 'string' ? JSON.parse(r.thinking_steps) : r.thinking_steps,
      foodInsight: typeof r.food_insight === 'string' ? JSON.parse(r.food_insight) : r.food_insight,
      createdAt: r.created_at,
    }));
  }

  async truncateMessagesAfter(accountId: number, sessionId: number, messageId: number) {
    const userId = await profileService.getUserId(accountId);
    const session = await dbQueryOne<any>(
      'SELECT session_id FROM chatsessions WHERE session_id = ? AND user_id = ? LIMIT 1',
      [sessionId, userId]
    );

    if (!session) {
      throw new NotFoundError('Session not found');
    }

    await dbExecute('DELETE FROM chatmessages WHERE session_id = ? AND message_id >= ?', [
      sessionId,
      messageId,
    ]);
    return { success: true, message: 'Messages truncated' };
  }

  async sendMessage(accountId: number, data: SendMessageDto) {
    const userId = await profileService.getUserId(accountId);

    let sessionId = data.sessionId;
    if (!sessionId) {
      // Create new session
      const sessResult = await dbExecute('INSERT INTO chatsessions (user_id) VALUES (?)', [userId]);
      sessionId = sessResult.insertId;
    } else {
      // Verify session belongs to user
      const existing = await dbQueryOne<any>(
        'SELECT session_id FROM chatsessions WHERE session_id = ? AND user_id = ? LIMIT 1',
        [sessionId, userId]
      );
      if (!existing) {
        const sessResult = await dbExecute('INSERT INTO chatsessions (user_id) VALUES (?)', [userId]);
        sessionId = sessResult.insertId;
      }
    }

    // 1. Save user message
    const userMsgResult = await dbExecute(
      'INSERT INTO chatmessages (session_id, sender, message_text, image_url, image_name) VALUES (?, ?, ?, ?, ?)',
      [sessionId, 'user', data.message, data.imageUrl || null, data.imageName || null]
    );
    const userMessageId = userMsgResult.insertId;

    // 2. Load recent conversation history
    const historyRows = await dbQuery<any[]>(
      'SELECT sender, message_text FROM chatmessages WHERE session_id = ? ORDER BY message_id DESC LIMIT 6',
      [sessionId]
    );
    const history = historyRows
      .reverse()
      .map((r) => ({ sender: r.sender as 'user' | 'ai', text: r.message_text }));

    // 3. User profile context
    const profile = await profileService.getProfile(accountId).catch(() => null);

    // 4. Generate AI response
    const aiResponse = await aiProviderService.generateResponse(data.message, history, profile);

    // 5. Save AI message
    const aiMsgResult = await dbExecute(
      `INSERT INTO chatmessages (session_id, sender, message_text, thinking_steps, food_insight)
       VALUES (?, 'ai', ?, ?, ?)`,
      [
        sessionId,
        aiResponse.text,
        aiResponse.thinkingSteps ? JSON.stringify(aiResponse.thinkingSteps) : null,
        aiResponse.foodInsight ? JSON.stringify(aiResponse.foodInsight) : null,
      ]
    );
    const aiMessageId = aiMsgResult.insertId;

    return {
      sessionId,
      userMessage: {
        messageId: userMessageId,
        sender: 'user',
        text: data.message,
        imageUrl: data.imageUrl,
      },
      aiMessage: {
        messageId: aiMessageId,
        sender: 'ai',
        text: aiResponse.text,
        thinkingSteps: aiResponse.thinkingSteps,
        foodInsight: aiResponse.foodInsight,
      },
    };
  }
}

export const chatService = new ChatService();
