export interface ChatResponse {
  conversation_id: string;
  response: string;
  tool_used?: string | null;
  escalated?: boolean;
  lead_captured?: boolean;
}

export interface SendMessageInput {
  token: string;
  conversation_id: string;
  content: string;
  session_id: string;
  apiBaseUrl?: string;
}

export async function sendMessage(input: SendMessageInput): Promise<ChatResponse> {
  const { token, conversation_id, content, session_id, apiBaseUrl } = input;
  const baseUrl = apiBaseUrl ?? "";
  const response = await fetch(`${baseUrl}/chat/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      conversation_id,
      content,
      session_id,
    }),
  });

  if (!response.ok) {
    try {
      const body = await response.json();
      throw new Error(body.detail || "Failed to send message");
    } catch {
      throw new Error("Failed to send message");
    }
  }

  return (await response.json()) as ChatResponse;
}
