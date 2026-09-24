import type { Health, QuizEvent, Snapshot } from "./types";

const ACCESS_KEY = "quizpilot.access";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function storedAccessCode(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(ACCESS_KEY) ?? "";
  } catch {
    return "";
  }
}

export function rememberAccessCode(code: string): void {
  try {
    if (code) window.localStorage.setItem(ACCESS_KEY, code);
    else window.localStorage.removeItem(ACCESS_KEY);
  } catch {
    // A browser with site data blocked simply asks for the code again.
  }
}

function headers(body: boolean): HeadersInit {
  const result: Record<string, string> = {};
  if (body) result["Content-Type"] = "application/json";
  const code = storedAccessCode();
  if (code) result["x-quizpilot-access"] = code;
  return result;
}

async function failure(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // Non-JSON error bodies keep the generic message.
  }
  return new ApiError(detail, response.status);
}

/**
 * Consume a server-sent event stream from a POST.
 *
 * EventSource cannot POST, so the response body is read and split by hand.
 * Lines beginning with a colon are heartbeats that keep a slow live turn
 * alive through proxies; they carry no data.
 */
async function* streamEvents(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<QuizEvent> {
  const response = await fetch(path, {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (!response.ok) throw await failure(response);
  if (!response.body) throw new ApiError("The server sent no response body.", 500);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        yield JSON.parse(line.slice(5).trim()) as QuizEvent;
      }
      split = buffer.indexOf("\n\n");
    }
  }
}

export function createSession(
  options: { mode: string; topic?: string; difficulty: string; maxQuestions: number },
  signal?: AbortSignal,
) {
  return streamEvents("/api/session", options, signal);
}

export function sendReply(
  sessionId: string,
  reply: { kind: "answer" | "hint" | "stop"; text?: string },
  signal?: AbortSignal,
) {
  return streamEvents(`/api/session/${sessionId}/reply`, reply, signal);
}

export function retrySession(sessionId: string, signal?: AbortSignal) {
  return streamEvents(`/api/session/${sessionId}/retry`, {}, signal);
}

export async function fetchSnapshot(sessionId: string): Promise<Snapshot> {
  const response = await fetch(`/api/session/${sessionId}`, { headers: headers(false) });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as Snapshot;
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health", { headers: headers(false) });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as Health;
}
