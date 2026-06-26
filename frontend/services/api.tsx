const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface ChatRequest {
  user_id: string;
  message: string;
  state?: string;
  technique_index?: number;
}

export interface MenuOption {
  id: string;
  label: string;
}

export interface ChatResponse {
  success?: boolean;
  response?: string;
  text?: string;
  menu_options?: string[];
  option_ids?: string[];
  options?: MenuOption[];
  show_menu?: boolean;
  crisis_detected?: boolean;
  detected_emotion?: string;
  state?: string;
  conversation_count?: number;
  hope_capture_mode?: boolean;
  tasks_saved?: number;
  goal_saved?: boolean;
  [key: string]: any;
}

// First message gets longer timeout — model may still be warming up
let _firstMessage = true;

export const api = {
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    // 90s for first message (Ollama warmup), 60s after that
    const timeoutMs = _firstMessage ? 90_000 : 60_000;

    const attemptFetch = async (): Promise<ChatResponse> => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const res = await fetch(`${API_BASE_URL}/api/chat/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        _firstMessage = false;
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Server error ${res.status}`);
        }
        const data: ChatResponse = await res.json();
        if (!data.text && data.response) data.text = data.response;
        if (!data.text) data.text = "I'm here with you. 💜";
        return data;
      } catch (error: any) {
        clearTimeout(timeoutId);
        if (error.name === "AbortError") throw new Error("timeout");
        throw error;
      }
    };

    // Auto-retry once on first-message timeout (Ollama sometimes stalls)
    try {
      return await attemptFetch();
    } catch (err: any) {
      if (err.message === "timeout" && _firstMessage) {
        _firstMessage = false;
        return await attemptFetch();
      }
      throw err;
    }
  },
};
