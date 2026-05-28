import { useMemo, useState } from "react";
import { marked } from "marked";
import { sendMessage } from "./api";

export type InitPayload = {
  token: string;
  widgetId: string;
  greeting?: string;
  origin: string;
  apiBaseUrl?: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const containerStyle: React.CSSProperties = {
  position: "fixed",
  bottom: "24px",
  right: "24px",
  width: "360px",
  maxWidth: "90vw",
  height: "520px",
  background: "#0b0d12",
  color: "#f8f7f2",
  borderRadius: "16px",
  boxShadow: "0 18px 45px rgba(0,0,0,0.35)",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
  fontFamily: "\"Space Grotesk\", ui-sans-serif, system-ui",
  zIndex: 9999,
};

const headerStyle: React.CSSProperties = {
  padding: "16px",
  borderBottom: "1px solid rgba(255,255,255,0.08)",
  background: "linear-gradient(120deg, #1c1f2b 0%, #0b0d12 100%)",
};

const messageListStyle: React.CSSProperties = {
  flex: 1,
  padding: "16px",
  overflowY: "auto",
  display: "flex",
  flexDirection: "column",
  gap: "12px",
};

const inputWrapperStyle: React.CSSProperties = {
  padding: "12px 16px 16px",
  borderTop: "1px solid rgba(255,255,255,0.08)",
  display: "flex",
  gap: "8px",
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(255,255,255,0.12)",
  background: "#0f121a",
  color: "#f8f7f2",
  fontSize: "14px",
};

const buttonStyle: React.CSSProperties = {
  padding: "10px 16px",
  borderRadius: "10px",
  border: "none",
  background: "#f25c54",
  color: "#0b0d12",
  fontWeight: 600,
  cursor: "pointer",
};

const bubbleStyle = (role: Message["role"]): React.CSSProperties => ({
  alignSelf: role === "user" ? "flex-end" : "flex-start",
  maxWidth: "80%",
  padding: "10px 12px",
  borderRadius: "14px",
  background: role === "user" ? "#f25c54" : "#1b1f2b",
  color: role === "user" ? "#0b0d12" : "#f8f7f2",
  lineHeight: 1.5,
  fontSize: "14px",
});

const ChatWidget = ({ init }: { init: InitPayload }) => {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (init.greeting) {
      return [
        {
          id: "greeting",
          role: "assistant",
          content: init.greeting,
        },
      ];
    }
    return [];
  });
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [conversationId, setConversationId] = useState("new");

  const sessionId = useMemo(() => `widget-${Date.now().toString(36)}`, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || pending) {
      return;
    }

    const userMessage: Message = {
      id: `${Date.now()}-user`,
      role: "user",
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setPending(true);

    try {
      const response = await sendMessage({
        token: init.token,
        conversation_id: conversationId,
        content: trimmed,
        session_id: sessionId,
        apiBaseUrl: init.apiBaseUrl,
      });
      setConversationId(response.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: response.response,
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-error`,
          role: "assistant",
          content: error instanceof Error ? error.message : "Sorry, something went wrong. Please try again.",
        },
      ]);
    } finally {
      setPending(false);
    }
  };

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <div style={{ fontWeight: 600, fontSize: "15px" }}>Concierge</div>
        <div style={{ fontSize: "12px", opacity: 0.7 }}>Ask us anything</div>
      </div>
      <div style={messageListStyle}>
        {messages.map((message) => (
          <div
            key={message.id}
            style={bubbleStyle(message.role)}
            {...(message.role === "assistant"
              ? { dangerouslySetInnerHTML: { __html: marked.parse(message.content) as string } }
              : { children: message.content }
            )}
          />
        ))}
        {pending && (
          <div style={bubbleStyle("assistant")}>
            <span style={{ opacity: 0.7 }}>Typing...</span>
          </div>
        )}
      </div>
      <form style={inputWrapperStyle} onSubmit={handleSubmit}>
        <input
          style={inputStyle}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type your message"
        />
        <button style={buttonStyle} type="submit" disabled={pending}>
          Send
        </button>
      </form>
    </div>
  );
};

export default ChatWidget;
