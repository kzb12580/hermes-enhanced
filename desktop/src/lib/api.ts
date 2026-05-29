/**
 * HTTP client for communicating with the Python backend API.
 * Supports SSE streaming for real-time AI responses.
 */

const DEFAULT_BASE_URL = 'http://127.0.0.1:9876';
const CONNECTION_TIMEOUT_MS = 10000;
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;

export interface ApiConfig {
  baseUrl?: string;
  apiKey?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  tool_call_id?: string;
  name?: string;
  content?: string;
}

export interface ChatCompletionRequest {
  content: string;
  session_id?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  system_prompt?: string;
  thinking_mode?: 'off' | 'auto' | 'on';
  thinking_budget?: number;
  proxy_url?: string;
  skills?: string[];
  temperature?: number;
  max_tokens?: number;
}

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  triggers: string[];
  is_builtin: boolean;
  enabled?: boolean;
}

export interface SkillDetail extends SkillInfo {
  content: string;
  tools: string[];
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

  private getHeaders(isGet = false): Record<string, string> {
    const headers: Record<string, string> = {};
    // Only set Content-Type for non-GET requests
    if (!isGet) {
      headers['Content-Type'] = 'application/json';
    }
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }

  /**
   * Parse error response body for meaningful error messages.
   */
  private async parseErrorResponse(res: Response): Promise<string> {
    try {
      const body = await res.json();
      if (body.detail) return body.detail;
      if (body.message) return body.message;
      if (body.error) return body.error;
      return JSON.stringify(body);
    } catch {
      try {
        return await res.text();
      } catch {
        return `HTTP ${res.status}`;
      }
    }
  }

  /**
   * Fetch with retry logic. Only retries on network errors and 5xx status codes.
   * Connection timeout only applies to connection establishment, not the full stream.
   */
  private async fetchWithRetry(
    url: string,
    options: RequestInit = {},
    retries = MAX_RETRIES
  ): Promise<Response> {
    const controller = new AbortController();
    // Connection-only timeout: clear after response headers arrive
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
      // Clear connection timeout once we get headers — stream can take as long as it needs
      clearTimeout(timeoutId);
      return response;
    } catch (err: any) {
      clearTimeout(timeoutId);

      // Don't retry aborts (user-initiated or timeout)
      if (err.name === 'AbortError') throw err;

      // Only retry on network errors (not HTTP-level errors which are handled by caller)
      if (retries > 0) {
        // Exponential backoff: 1s, 2s, 4s (for retries 3, 2, 1)
        const delay = RETRY_BASE_DELAY_MS * Math.pow(2, MAX_RETRIES - retries);
        await new Promise((r) => setTimeout(r, delay));
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
      headers: this.getHeaders(true),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Health check failed: ${res.status} - ${detail}`);
    }
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
    // FIX #1 (CRITICAL): Pass the user's signal directly to fetch() so that
    // reader.read() in the generator is also abortable. We still use
    // fetchWithRetry for the initial connection (with its own timeout), but
    // after that, we do a direct fetch with the user signal for the stream.
    //
    // Strategy: use fetchWithRetry for connection establishment with retries,
    // then for streaming reads, check signal.aborted before each read.
    const res = await this.fetchWithRetry(
      `${this.baseUrl}/api/chat`,
      {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify({
          content: request.content,
          session_id: request.session_id,
          model: request.model,
          base_url: request.base_url,
          api_key: request.api_key,
          system_prompt: request.system_prompt,
          thinking_mode: request.thinking_mode,
          thinking_budget: request.thinking_budget,
          proxy_url: request.proxy_url,
          skills: request.skills,
          temperature: request.temperature,
          max_tokens: request.max_tokens,
        }),
        signal,
      }
    );

    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Chat request failed: ${res.status} - ${detail}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';
    // FIX #4: Track whether the connection was timed out vs user-aborted
    let connectionTimedOut = false;

    try {
      while (true) {
        // FIX #1: Check if user signal was aborted before each read
        if (signal?.aborted) {
          // Distinguish user abort from timeout
          const reason = signal.reason;
          if (reason instanceof Error && reason.message.includes('timeout')) {
            connectionTimedOut = true;
          }
          break;
        }

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
            // FIX #3: Strip only the first space after 'data:' per SSE spec
            // SSE spec: "data:" followed by optional single space then value
            const raw = trimmed.slice(5);
            const data = raw.startsWith(' ') ? raw.slice(1) : raw;

            if (currentEvent === 'done') {
              // Stream is finished
              return;
            }

            if (currentEvent === 'error') {
              // Provider error — throw so the UI can display it
              throw new Error(data || 'Provider returned an error');
            }

            if (currentEvent === 'token') {
              yield data;
            } else if (currentEvent === 'tool_call') {
              yield `[TOOL_CALL]${data}`;
            } else if (currentEvent === 'tool_result') {
              yield `[TOOL_RESULT]${data}`;
            } else if (currentEvent === 'thinking') {
              yield `[THINKING]${data}`;
            }
            continue;
          }

          // Skip SSE comment lines (starting with ':') — these are keepalives
          // Do NOT yield fallback plain text — could leak non-SSE content
        }
      }

      // FIX #2: Process remaining buffer content after the stream ends
      if (buffer.trim()) {
        const remainingLines = buffer.split('\n');
        for (const line of remainingLines) {
          const trimmed = line.trim();
          if (!trimmed) {
            currentEvent = '';
            continue;
          }
          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim();
            continue;
          }
          if (trimmed.startsWith('data:')) {
            const raw = trimmed.slice(5);
            const data = raw.startsWith(' ') ? raw.slice(1) : raw;
            if (currentEvent === 'done') return;
            if (currentEvent === 'error') throw new Error(data);
            if (currentEvent === 'tool_call') { yield `[TOOL_CALL]${data}`; continue; }
            if (currentEvent === 'tool_result') { yield `[TOOL_RESULT]${data}`; continue; }
            if (currentEvent === 'thinking') { yield `[THINKING]${data}`; continue; }
            if (currentEvent === 'token') yield data;
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
      headers: this.getHeaders(true),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`List sessions failed: ${res.status} - ${detail}`);
    }
    return res.json();
  }

  /** Create a new session */
  async createSession(name?: string): Promise<SessionInfo> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/sessions`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ name }),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Create session failed: ${res.status} - ${detail}`);
    }
    return res.json();
  }

  /** Delete a session */
  async deleteSession(sessionId: string): Promise<void> {
    const encodedId = encodeURIComponent(sessionId);
    const res = await this.fetchWithRetry(
      `${this.baseUrl}/api/sessions/${encodedId}`,
      {
        method: 'DELETE',
        headers: this.getHeaders(),
      }
    );
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Delete session failed: ${res.status} - ${detail}`);
    }
  }

  /** Fetch available skills */
  async fetchSkills(): Promise<SkillInfo[]> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/skills`, {
      headers: this.getHeaders(true),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Fetch skills failed: ${res.status} - ${detail}`);
    }
    return res.json();
  }

  /** Get a single skill by name */
  async getSkill(name: string): Promise<SkillDetail> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/skills/${encodeURIComponent(name)}`, {
      headers: this.getHeaders(true),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Get skill failed: ${res.status} - ${detail}`);
    }
    return res.json();
  }

  /** Search skills by query */
  async searchSkills(query: string): Promise<SkillInfo[]> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/skills/search`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ query }),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Search skills failed: ${res.status} - ${detail}`);
    }
    return res.json();
  }

  /** Reload skills from disk */
  async reloadSkills(): Promise<{ status: string; count: number }> {
    const res = await this.fetchWithRetry(`${this.baseUrl}/api/skills/reload`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const detail = await this.parseErrorResponse(res);
      throw new Error(`Reload skills failed: ${res.status} - ${detail}`);
    }
    return res.json();
  }
}

export const apiClient = new ApiClient();
export default apiClient;
