import type { ChatStreamEvent } from "@/lib/data/DataSource";

/**
 * Parses a text/event-stream Response into ChatStreamEvents. Used by
 * LiveDataSource against the interview edge function; MockDataSource yields
 * the same events from the canned script, the chat UI can't tell them apart.
 */
export async function* parseSSE(
  response: Response,
  signal?: AbortSignal,
): AsyncIterable<ChatStreamEvent> {
  const reader = response.body?.getReader();
  if (!reader) {
    yield { type: "error", message: "The interview stream could not be opened." };
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      if (signal?.aborted) return;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = rawEvent
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim())
          .join("\n");
        if (!data) continue;
        if (data === "[DONE]") {
          yield { type: "done", messageId: "" };
          return;
        }
        try {
          yield JSON.parse(data) as ChatStreamEvent;
        } catch {
          yield { type: "token", text: data };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
