// Typed wrapper around the Flask API.
import type { Conversation, Message } from "./types";

async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body: { error?: string } = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res;
}

export const listConversations = (): Promise<Conversation[]> =>
  request("/api/conversations").then((r) => r.json());

export const createConversation = (): Promise<Conversation> =>
  request("/api/conversations", { method: "POST" }).then((r) => r.json());

export const deleteConversation = (id: number): Promise<Response> =>
  request(`/api/conversations/${id}`, { method: "DELETE" });

export const listMessages = (id: number): Promise<Message[]> =>
  request(`/api/conversations/${id}/messages`).then((r) => r.json());

// Sends a message and calls onChunk with each piece of the reply as it streams in.
export async function sendMessage(
  id: number,
  content: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await request(`/api/conversations/${id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  if (!res.body) throw new Error("The server sent an empty response");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}
