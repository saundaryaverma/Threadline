// Small wrapper around the Flask API.
async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res;
}

export const listConversations = () =>
  request("/api/conversations").then((r) => r.json());

export const createConversation = () =>
  request("/api/conversations", { method: "POST" }).then((r) => r.json());

export const deleteConversation = (id) =>
  request(`/api/conversations/${id}`, { method: "DELETE" });

export const listMessages = (id) =>
  request(`/api/conversations/${id}/messages`).then((r) => r.json());

// Sends a message and calls onChunk with each piece of the reply as it streams in.
export async function sendMessage(id, content, onChunk) {
  const res = await request(`/api/conversations/${id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}
