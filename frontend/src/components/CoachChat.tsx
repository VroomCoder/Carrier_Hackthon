import { useEffect, useMemo, useRef, useState } from "react";
import { Send } from "lucide-react";
import { apiFetch } from "../hooks/api";
import type { AuthUser, ChatMessage, Employee, ToastType } from "../types";
import { COACH_QUICK_PROMPTS } from "../data/seedData";

interface Props {
  selfEmployee: Employee | null;
  user: AuthUser;
  addToast: (message: string, type?: ToastType) => void;
}

function isPolicyCitation(text: string): boolean {
  return /policy|per the|according to/i.test(text);
}

function MessageContent({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <>
      {lines.map((line, i) =>
        isPolicyCitation(line) ? (
          <div key={i} className="border-l-2 border-brand-400 pl-3 my-1 text-gray-700">
            {line}
          </div>
        ) : (
          <span key={i}>
            {line}
            {i < lines.length - 1 && <br />}
          </span>
        )
      )}
    </>
  );
}

export default function CoachChat({ selfEmployee, user, addToast }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [contextLoading, setContextLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const sessionId = useMemo(
    () =>
      selfEmployee?.employee_id
        ? `coach_${user.user_id}_${selfEmployee.employee_id}`
        : `coach_${user.user_id}_general`,
    [selfEmployee?.employee_id, user.user_id]
  );

  useEffect(() => {
    if (user.role !== "admin" && !selfEmployee?.employee_id) {
      setContextLoading(false);
      return;
    }
    setContextLoading(true);
    const params = selfEmployee?.employee_id
      ? `?employee_id=${encodeURIComponent(selfEmployee.employee_id)}`
      : "";
    apiFetch(`/api/chat/context${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const greeting =
          data?.greeting ??
          `Hi ${selfEmployee?.name?.split(" ")[0] ?? "there"} — I'm your Growth Coach. How can I help?`;
        setMessages([{ role: "assistant", content: greeting }]);
      })
      .catch(() => {
        setMessages([
          {
            role: "assistant",
            content: `Hi ${selfEmployee?.name?.split(" ")[0] ?? "there"} — I'm your Growth Coach. How can I help?`,
          },
        ]);
      })
      .finally(() => setContextLoading(false));
  }, [selfEmployee?.employee_id, selfEmployee?.name, user.role]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || streaming || contextLoading) return;

    if (user.role !== "admin" && !selfEmployee?.employee_id) {
      addToast("No employee profile linked to your account", "error");
      return;
    }

    const userMsg: ChatMessage = { role: "user", content: text };
    const newMessages = [...messages, userMsg];
    const apiMessages = newMessages.slice(1);
    setMessages(newMessages);
    setInput("");
    setStreaming(true);

    try {
      const res = await apiFetch("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          messages: apiMessages,
          employee_id: selfEmployee?.employee_id ?? null,
          session_id: sessionId,
        }),
      });

      if (res.status === 403) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "Access denied", "error");
        setStreaming(false);
        return;
      }

      if (res.status === 503) {
        const err = await res.json().catch(() => ({}));
        addToast(typeof err.detail === "string" ? err.detail : "AI service unavailable", "error");
        setStreaming(false);
        return;
      }

      if (!res.ok || !res.body) {
        addToast("Chat request failed", "error");
        setStreaming(false);
        return;
      }

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = { ...last, content: last.content + chunk };
          }
          return updated;
        });
      }
    } catch {
      addToast("Failed to connect to backend", "error");
    } finally {
      setStreaming(false);
    }
  };

  if (user.role !== "admin" && !selfEmployee) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>Growth Coach requires an employee profile on your account.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="page-title mb-1">Growth Coach</h1>
      <p className="text-sm text-gray-500 mb-4">
        Personal coaching grounded in your goals, OKRs, feedback, and cycle health.
        {user.is_manager && " Use Team health and feedback tools to support your direct reports."}
      </p>

      {contextLoading && (
        <p className="text-xs text-gray-400 mb-2">Loading your context…</p>
      )}

      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-brand-400 text-white"
                  : "bg-white border border-gray-200 text-gray-800"
              }`}
            >
              {msg.role === "assistant" ? (
                <MessageContent content={msg.content} />
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}
        {streaming && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-xl px-4 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.1s" }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {COACH_QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => sendMessage(prompt)}
            disabled={streaming || contextLoading}
            className="text-xs bg-gray-100 text-gray-600 px-3 py-1.5 rounded-full hover:bg-gray-200 disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage(input)}
          placeholder="Ask your growth coach..."
          disabled={streaming || contextLoading}
          className="flex-1 border border-gray-200 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-brand-400 focus:outline-none"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={streaming || contextLoading || !input.trim()}
          className="bg-brand-400 text-white p-2 rounded-lg hover:bg-brand-600 disabled:opacity-50"
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
