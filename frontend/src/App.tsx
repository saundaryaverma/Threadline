import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import * as api from "./api";
import type { Conversation, Message } from "./types";

const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listConversations().then(setConversations).catch((e) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function openConversation(id: number) {
    if (streaming) return;
    setError("");
    setActiveId(id);
    try {
      setMessages(await api.listMessages(id));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function startNewChat() {
    if (streaming) return;
    setActiveId(null);
    setMessages([]);
    setError("");
  }

  async function removeConversation(id: number) {
    try {
      await api.deleteConversation(id);
      setConversations((list) => list.filter((c) => c.id !== id));
      if (id === activeId) startNewChat();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function send() {
    const content = draft.trim();
    if (!content || streaming) return;
    setError("");
    setDraft("");
    setStreaming(true);

    try {
      // Create the conversation on the first message, not when "New chat" is clicked.
      let id: number | null = activeId;
      if (id === null) {
        const created = await api.createConversation();
        id = created.id;
        setActiveId(id);
        setConversations((list) => [created, ...list]);
      }

      setMessages((list) => [
        ...list,
        { role: "user", content },
        { role: "assistant", content: "" },
      ]);
      const chatId = id;

      await api.sendMessage(chatId, content, (chunk) => {
        setMessages((list) => {
          const next = [...list];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + chunk };
          return next;
        });
      });

      // Pick up the title the server gave this chat.
      setConversations(await api.listConversations());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setStreaming(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="brand">Threadline</h1>
        <button className="new-chat" onClick={startNewChat} disabled={streaming}>
          New chat
        </button>
        <nav className="history" aria-label="Past chats">
          {conversations.length === 0 && <p className="history-empty">Your chats will show up here.</p>}
          {conversations.map((c) => (
            <div key={c.id} className={`history-item ${c.id === activeId ? "is-active" : ""}`}>
              <button className="history-open" onClick={() => openConversation(c.id)}>
                {c.title}
              </button>
              <button
                className="history-delete"
                onClick={() => removeConversation(c.id)}
                aria-label={`Delete chat: ${c.title}`}
                disabled={streaming}
              >
                Delete
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <main className="chat">
        <div className="thread" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty">
              <h2>Ask anything to start a chat.</h2>
              <p>Replies stream in as they're written, and every chat is saved so you can come back to it.</p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`message message-${m.role}`}>
                <span className="speaker">{m.role === "user" ? "You" : "Threadline"}</span>
                <p className="body">
                  {m.content || (streaming && i === messages.length - 1 ? "Writing…" : "")}
                </p>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="error" role="alert">{error}</p>}

        <div className="composer">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Threadline (Shift+Enter for a new line)"
            rows={2}
            aria-label="Message"
          />
          <button onClick={send} disabled={streaming || !draft.trim()}>
            {streaming ? "Sending" : "Send"}
          </button>
        </div>
      </main>
    </div>
  );
}
