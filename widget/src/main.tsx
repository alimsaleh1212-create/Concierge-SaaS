import { createRoot } from "react-dom/client";
import { useEffect, useMemo, useState } from "react";
import ChatWidget, { type InitPayload } from "./ChatWidget";

type InitMessage = {
  type: "CONCIERGE_INIT";
  token: string;
  widget_id: string;
  greeting?: string;
  api_origin?: string;
};

const App = () => {
  const [payload, setPayload] = useState<InitPayload | null>(null);

  const allowedOrigin = useMemo(() => {
    if (document.referrer) {
      try {
        return new URL(document.referrer).origin;
      } catch {
        return "";
      }
    }
    return "";
  }, []);

  useEffect(() => {
    const onMessage = (event: MessageEvent<InitMessage>) => {
      if (event.data?.type !== "CONCIERGE_INIT") {
        return;
      }
      if (allowedOrigin && event.origin !== allowedOrigin) {
        return;
      }
      setPayload({
        token: event.data.token,
        widgetId: event.data.widget_id,
        greeting: event.data.greeting,
        origin: event.origin,
        apiBaseUrl: event.data.api_origin,
      });
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [allowedOrigin]);

  if (!payload) {
    return null;
  }

  return <ChatWidget init={payload} />;
};

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(<App />);
}
