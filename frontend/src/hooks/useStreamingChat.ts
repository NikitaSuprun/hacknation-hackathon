/**
 * useStreamingChat — owns the founder-side interview conversation.
 *
 * Local state is the source of truth during the session: messages seed once
 * from the bootstrap transcript, every later turn is appended here (reconciled
 * by message id so a store-side refetch can never duplicate a turn). The
 * interviewer's words arrive token-by-token into `streamingText`; on the
 * stream's done event the buffer moves into `messages` under the server's id.
 *
 * End detection: a stream that closes with done and zero tokens means the
 * interviewer has nothing left to say (mock: script exhausted; live: server
 * closed the interview) — `ended` flips and the UI surfaces the finish action.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { dataSource } from "@/lib/data";
import type { ChatMessage } from "@/lib/domain/types";

export interface StreamingChat {
  /** Completed turns, oldest first. */
  messages: ChatMessage[];
  /** The interviewer's in-flight turn, growing token by token ("" when idle). */
  streamingText: string;
  /** True from send until the stream settles (drives the typing indicator). */
  isStreaming: boolean;
  /** The interviewer is done — surface the finish action. */
  ended: boolean;
  error: string | null;
  send: (text: string) => void;
  /** Sends the literal word "skip". */
  skip: () => void;
}

export function useStreamingChat(
  token: string,
  initialTranscript: ChatMessage[],
): StreamingChat {
  const ds = dataSource();
  const [messages, setMessages] = useState<ChatMessage[]>(() => [...initialTranscript]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [ended, setEnded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busyRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  /** Defensive counter — one empty stream ends the interview, two can never loop. */
  const emptyStreamsRef = useRef(0);

  const run = useCallback(
    async (raw: string) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setError(null);

      const text = raw.trim();
      if (text) {
        setMessages((prev) => [
          ...prev,
          {
            id: `founder-local-${Date.now()}`,
            role: "founder",
            text,
            at: new Date().toISOString(),
          },
        ]);
      }

      const controller = new AbortController();
      controllerRef.current = controller;
      setIsStreaming(true);
      setStreamingText("");

      let buffer = "";
      let doneId: string | null = null;
      let failed = false;
      try {
        for await (const event of ds.streamInterviewMessage(token, raw, controller.signal)) {
          if (controller.signal.aborted) break;
          if (event.type === "token") {
            buffer += event.text;
            setStreamingText(buffer);
          } else if (event.type === "done") {
            doneId = event.messageId;
          } else {
            failed = true;
            setError(event.message);
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          failed = true;
          setError(err instanceof Error ? err.message : "The connection dropped — try again.");
        }
      }

      if (controller.signal.aborted) {
        busyRef.current = false;
        return;
      }

      if (doneId && buffer) {
        // Move the buffer into messages under the server's id (dedup by id —
        // a refetch-reconciled transcript can never double this turn).
        const id = doneId;
        const finished: ChatMessage = {
          id,
          role: "interviewer",
          text: buffer,
          at: new Date().toISOString(),
        };
        setMessages((prev) => (prev.some((m) => m.id === id) ? prev : [...prev, finished]));
        emptyStreamsRef.current = 0;
      } else if (doneId && !failed) {
        emptyStreamsRef.current += 1;
        setEnded(true);
      }

      setStreamingText("");
      setIsStreaming(false);
      busyRef.current = false;
    },
    [ds, token],
  );

  const send = useCallback((text: string) => void run(text), [run]);
  const skip = useCallback(() => void run("skip"), [run]);

  // On mount with an empty transcript, stream the interviewer's greeting.
  const kickedRef = useRef(false);
  useEffect(() => {
    if (kickedRef.current) return;
    kickedRef.current = true;
    if (initialTranscript.length === 0) void run("");
  }, [initialTranscript.length, run]);

  // Abort any in-flight stream when the chat unmounts.
  useEffect(() => () => controllerRef.current?.abort(), []);

  return { messages, streamingText, isStreaming, ended, error, send, skip };
}
