/**
 * HTTP client for communicating with the Python backend API.
 * Supports SSE streaming for real-time AI responses.
 */

const DEFAULT_BASE_URL = 'http://127.0.0.1:9876';
const CONNECTION_TIMEOUT_MS = 10000;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

export interface ApiConfig {
  baseUrl?: string;
  apiKey?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_call_id?: string;
  name?: string;
}

export interface ChatCompletionRequest {
  content: string;
  session_id?: string;
  model?: string;
}

export interface SessionInfo {
  id: string;
  name: string;
  created_at: string;
  message_count: number;
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  uptime_seconds: number;
}

class ApiClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(config: ApiConfig = {}) {
    this.baseUrl = config.baseUrl || DEFAULT_BASE_URL;
    this.apiKey = config.apiKey || '';
  }

  updateConfig(config: ApiConfig) {
    if (config.baseUrl) this.baseUrl = config.baseUrl;
    if (config.apiKey !== undefined) this.apiKey = config.apiKey;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }

  /**
   * Fetch with retry logic and connection timeout.
   */
  private async fetchWithRetry(
    url: string,
    options: RequestInit = {},
    retries = MAX_RETRIES
  ): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONNECTION_TIMEOUT_MS);

    // If caller provided an external signal, propagate its abort
    const externalSignal = options.signal as AbortSignal | undefined;
    let externalAbortHandler: (() => void) | undefined;
    if (externalSignal) {
      if (externalSignal.aborted) {
        clearTimeout(timeoutId);
        controller.abort();
      } else {
        externalAbortHandler = () => controller.abort();
        externalSignal.addEventListener('abort', externalAbortHandler);
      }
    }

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return response;
    } catch (err: any) {
      clearTimeout(timeoutId);

      // Don't retry aborts (user-initiated or timeout)
      if (err.name === 'AbortError') throw err;

      if (retries > 0) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        return this.fetchWithRetry(url, options, retries - 1);
      }
      throw err;
    } finally {
      if (externalAbortHandler && externalSignal) {
        externalSignal.removeEventListener('abort', externalAbortHandler);
      }
    }
  }

  /** Health check */
  async healthCheck(): Promise<SystemStatus> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/health`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
  }

  /**
   * Streaming chat completion via SSE.
   * Python backend sends:
   *   event: token
   *   data: <character>
   *
   *   event: done
   *   data: (empty)
   */
  async *chatCompletionStream(
    request: ChatCompletionRequest,
    signal?: AbortSignal
  ): AsyncGenerator<string> {
    const res = await this.fetchWithRetry(
      `${this.baseUrl}/api/chat`,
      {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify({
          content: request.content,
          session_id: request.session_id,
          model: request.model,
        }),
        signal,
      }
    );

    if (!res.ok) {
      throw new Error(`Chat request failed: ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            // Empty line = end of SSE event block
            currentEvent = '';
            continue;
          }

          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim();
            continue;
          }

          if (trimmed.startsWith('data:')) {
            const data = trimmed.slice(5).trim();

            if (currentEvent === 'done') {
              // Stream is finished
              return;
            }

            if (currentEvent === 'token') {
              // Yield the raw text content
              yield data;
            }
            // Skip unknown events
            continue;
          }

          // Fallback: plain text lines without SSE prefix (some backends emit raw text)
          // Skip SSE comment lines (starting with ':') — these are keepalives
          if (!trimmed.startsWith('event:') && !trimmed.startsWith('data:') && !trimmed.startsWith(':')) {
            yield trimmed;
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  /** List all sessions */
  async listSessions(): Promise<SessionInfo[]> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/sessions`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`List sessions failed: ${res.status}`);
    return res.json();
  }

  /** Create a new session */
  async createSession(name?: string): Promise<SessionInfo> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/sessions`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error(`Create session failed: ${res.status}`);
    return res.json();
  }

  /** Delete a session */
  async deleteSession(sessionId: string): Promise<void> {
    const res = await this.fetchWithRetry(
      `${this.baseUrl}/api/sessions/${sessionId}`,
      {
        method: 'DELETE',
        headers: this.getHeaders(),
      }
    );
    if (!res.ok) throw new Error(`Delete session failed: ${res.status}`);
  }
}

export const apiClient = new ApiClient();
export default apiClient;
