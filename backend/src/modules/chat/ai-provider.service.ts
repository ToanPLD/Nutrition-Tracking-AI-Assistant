import { ENV } from '../../config/env';

export interface AiResponsePayload {
  text: string;
  thinkingSteps?: string[];
  foodInsight?: {
    foodName?: string;
    calories?: number;
    protein?: number;
    carbs?: number;
    fat?: number;
  };
}

export class AiProviderService {
  /**
   * Generates response trying CalAI -> Ollama -> Local Nutrition Assistant fallback
   */
  async generateResponse(
    userMessage: string,
    history: { sender: 'user' | 'ai'; text: string }[] = [],
    userProfile?: any
  ): Promise<AiResponsePayload> {
    // 1. Try CalAI Python Agent
    try {
      const calAiResult = await this.callCalAiAgent(userMessage, history, userProfile);
      if (calAiResult && calAiResult.text) {
        return calAiResult;
      }
    } catch {
      // Fallback to Ollama
    }

    // 2. Try Ollama LLM
    try {
      const ollamaResult = await this.callOllama(userMessage, history);
      if (ollamaResult && ollamaResult.text) {
        return ollamaResult;
      }
    } catch {
      // Fallback to Local Nutrition Assistant
    }

    // 3. Fallback Local Assistant
    return this.generateLocalFallback(userMessage, userProfile);
  }

  private async callCalAiAgent(
    query: string,
    history: any[],
    userProfile?: any
  ): Promise<AiResponsePayload | null> {
    const res = await fetch(`${ENV.CAL_AI_BASE_URL}/api/agent/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        history,
        user_profile: userProfile,
      }),
      signal: AbortSignal.timeout(ENV.CAL_AI_QUERY_TIMEOUT_MS),
    });

    if (!res.ok) return null;
    const data = (await res.json()) as any;
    return {
      text: data.response || data.text || data.answer || data.message || '',
      thinkingSteps: data.thinking_steps || (data.trace ? data.trace.map((t: any) => t.title || t.action || '') : ['Queried vector knowledge base', 'Formulated personalized meal advice']),
      foodInsight: data.food_insight || data.foodInsight,
    };
  }

  async *streamCalAiAgent(
    query: string,
    history: any[] = [],
    userProfile?: any
  ): AsyncGenerator<string, { fullText: string; thinkingSteps?: string[]; foodInsight?: any }, unknown> {
    const res = await fetch(`${ENV.CAL_AI_BASE_URL}/api/agent/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        history,
        user_profile: userProfile,
      }),
      signal: AbortSignal.timeout(ENV.CAL_AI_QUERY_TIMEOUT_MS),
    });

    if (!res.ok || !res.body) {
      throw new Error(`CalAI stream request failed with status ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;
        const dataStr = trimmed.slice(5).trim();
        if (dataStr === '[DONE]') {
          return {
            fullText,
            thinkingSteps: ['Vector Search & FlashRank', 'GPT-4o-mini generation'],
          };
        }
        try {
          const parsed = JSON.parse(dataStr);
          if (parsed.chunk) {
            fullText += parsed.chunk;
            yield parsed.chunk;
          } else if (parsed.error) {
            throw new Error(parsed.error);
          }
        } catch (e: any) {
          if (e.message && !e.message.includes('JSON')) {
            throw e;
          }
        }
      }
    }

    return {
      fullText,
      thinkingSteps: ['Vector Search & FlashRank', 'GPT-4o-mini generation'],
    };
  }

  private async callOllama(
    prompt: string,
    history: { sender: 'user' | 'ai'; text: string }[]
  ): Promise<AiResponsePayload | null> {
    const systemPrompt = `You are CalAI, an expert AI nutritionist and meal planning assistant. Provide actionable, concise, friendly, and science-backed nutritional guidance. Suggest specific calorie and macronutrient breakdowns when asked about meals.`;

    const res = await fetch(`${ENV.OLLAMA_BASE_URL}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: ENV.OLLAMA_MODEL,
        prompt: `${systemPrompt}\n\nUser: ${prompt}\nAssistant:`,
        stream: false,
      }),
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) return null;
    const data = (await res.json()) as any;
    return {
      text: data.response?.trim() || '',
      thinkingSteps: ['Processed user query with Ollama LLM', 'Generated contextual response'],
    };
  }

  private generateLocalFallback(query: string, userProfile?: any): AiResponsePayload {
    const q = query.toLowerCase();

    if (q.includes('calo') || q.includes('calorie') || q.includes('năng lượng')) {
      return {
        text: `Để quản lý lượng calo hiệu quả, bạn nên xác định chỉ số TDEE (tổng năng lượng tiêu thụ hàng ngày). Trung bình người trưởng thành cần từ 1,800 - 2,500 kcal mỗi ngày tùy thuộc vào cân nặng, chiều cao và mức độ vận động. Bạn có thể kiểm tra mục "Goals" để xem mục tiêu calo chi tiết của mình!`,
        thinkingSteps: ['Phân tích câu hỏi về calo', 'Tính toán nhu cầu dinh dưỡng cơ bản'],
        foodInsight: {
          foodName: 'Bữa ăn cân bằng khuyến nghị',
          calories: 550,
          protein: 35,
          carbs: 55,
          fat: 18,
        },
      };
    }

    if (q.includes('protein') || q.includes('đạm') || q.includes('tập gym') || q.includes('cơ')) {
      return {
        text: `Protein là dưỡng chất quan trọng giúp phục hồi và phát triển cơ bắp. Nhu cầu khuyến nghị là 1.6 - 2.2g protein trên mỗi kg trọng lượng cơ thể nếu bạn có tập luyện. Các nguồn protein dồi dào bao gồm ức gà, trứng, cá hồi, đậu hũ và thịt bò nạc.`,
        thinkingSteps: ['Nhận diện nhu cầu tăng cơ/protein', 'Tra cứu thực phẩm giàu đạm'],
        foodInsight: {
          foodName: 'Ức gà áp chảo (150g)',
          calories: 247,
          protein: 46,
          carbs: 0,
          fat: 5,
        },
      };
    }

    if (q.includes('giảm cân') || q.includes('lose weight') || q.includes('diet')) {
      return {
        text: `Nguyên tắc cốt lõi của giảm cân là thâm hụt calo (Caloric Deficit) an toàn: giảm khoảng 300 - 500 kcal so với TDEE mỗi ngày để giảm 0.5kg mỡ mỗi tuần mà không làm mất cơ bắp. Hãy ưu tiên bổ sung rau xanh, uống đủ nước và duy trì vận động đều đặn.`,
        thinkingSteps: ['Lập chiến lược giảm cân an toàn', 'Đề xuất tỷ lệ thâm hụt calo'],
      };
    }

    return {
      text: `Xin chào! Tôi là CalAI Assistant. Tôi có thể hỗ trợ bạn tính toán lượng calo, gợi ý thực đơn lành mạnh, phân tích bữa ăn và giải đáp các thắc mắc về dinh dưỡng. Bạn muốn tìm hiểu thông tin gì hôm nay?`,
      thinkingSteps: ['Khởi tạo phiên trò chuyện', 'Sẵn sàng hỗ trợ dinh dưỡng'],
    };
  }
}

export const aiProviderService = new AiProviderService();
