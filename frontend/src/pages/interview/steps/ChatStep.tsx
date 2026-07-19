/**
 * Step 3 — the conversation. Letter-style: the interviewer speaks flush-left
 * behind a 2px ink rule (no bubble); the founder answers in warm wash bubbles
 * on the right. Tokens stream in live; three pulsing dots while the
 * interviewer thinks; the scroll stays pinned to the bottom unless the
 * founder scrolls up to reread. When the interviewer has nothing left to
 * ask, a gentle end card offers the finish action.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { dataSource } from "@/lib/data";
import type { ChatMessage, InterviewBootstrap } from "@/lib/domain/types";
import { useStreamingChat } from "@/hooks/useStreamingChat";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

function timeOf(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function InterviewerTurn({ text, at, live }: { text: string; at?: string; live?: boolean }) {
  return (
    <div className="border-l-2 border-ink pl-4">
      <p className="whitespace-pre-wrap text-body text-ink">
        {text}
        {live ? <span className="animate-pulse text-quiet">▍</span> : null}
      </p>
      {at ? <p className="mt-1 font-mono text-mono-label text-quiet">{timeOf(at)}</p> : null}
    </div>
  );
}

function FounderTurn({ message }: { message: ChatMessage }) {
  return (
    <div className="flex flex-col items-end">
      <div className="max-w-[85%] rounded-warm bg-wash px-4 py-3">
        <p className="whitespace-pre-wrap text-body text-ink">{message.text}</p>
      </div>
      <p className="mt-1 font-mono text-mono-label text-quiet">{timeOf(message.at)}</p>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="border-l-2 border-ink pl-4" aria-label="The interviewer is typing">
      <div className="flex h-[1.625rem] items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-pulse rounded-full bg-quiet"
            style={{ animationDelay: `${i * 160}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export function ChatStep({
  session,
  refresh,
}: {
  session: InterviewBootstrap;
  refresh: () => Promise<void>;
}) {
  const ds = dataSource();
  const chat = useStreamingChat(session.token, session.transcript);
  const [draft, setDraft] = useState("");

  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  // Auto-scroll pinned to the bottom; a user scroll upward releases the pin
  // until they return to the bottom themselves.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [chat.messages, chat.streamingText, chat.ended]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  const finish = useMutation({
    mutationFn: async () => {
      await ds.completeInterview(session.token);
      await refresh();
    },
  });

  const canSend = draft.trim().length > 0 && !chat.isStreaming;
  const handleSend = () => {
    if (!canSend) return;
    chat.send(draft);
    setDraft("");
    pinnedRef.current = true;
  };

  // Mini progress: questions asked so far (interviewer turns beyond the
  // greeting) over the planned count — omitted until it's derivable.
  const planned = session.question_plan.length;
  const interviewerTurns = chat.messages.filter((m) => m.role === "interviewer").length;
  const asked = Math.min(Math.max(interviewerTurns - 1, 0), planned);
  const showProgress = planned > 0 && asked >= 1;

  const showTyping = chat.isStreaming && chat.streamingText.length === 0;

  return (
    <div className="flex h-[100dvh] flex-col bg-paper">
      <header className="hairline-b shrink-0 px-gutter py-4">
        <div className="mx-auto flex w-full max-w-[680px] items-baseline justify-between gap-4">
          <p className="mono-label">
            {session.fund_name} · in conversation with {session.founder_name}
          </p>
          {showProgress ? (
            <p className="shrink-0 font-mono text-mono-label text-quiet">
              question {asked} of {planned || "—"}
            </p>
          ) : null}
        </div>
      </header>

      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[680px] space-y-7 px-gutter py-10">
          <p className="font-mono text-mono-label text-quiet">
            About 15 minutes, conversational. Skip anything.
          </p>
          {chat.messages.map((message) =>
            message.role === "interviewer" ? (
              <InterviewerTurn key={message.id} text={message.text} at={message.at} />
            ) : (
              <FounderTurn key={message.id} message={message} />
            ),
          )}
          {chat.streamingText ? <InterviewerTurn text={chat.streamingText} live /> : null}
          {showTyping ? <TypingDots /> : null}
          {chat.error ? <p className="text-small text-danger">{chat.error}</p> : null}
          {chat.ended ? (
            <Card className="animate-fade-up rounded-warm border-line bg-paper p-6 shadow-lift">
              <p className="mono-label mb-2">That's everything</p>
              <p className="text-body text-ink">
                Nothing more to ask — your answers are saved to your candidacy.
              </p>
              <Button
                data-demo-id="btn-interview-done"
                className="mt-5"
                disabled={finish.isPending}
                onClick={() => finish.mutate()}
              >
                {finish.isPending ? "One moment…" : "Finish — complete my candidacy"}
              </Button>
              {finish.isError ? (
                <p className="mt-3 text-small text-danger">
                  That didn't go through — try again in a moment.
                </p>
              ) : null}
            </Card>
          ) : null}
        </div>
      </div>

      {!chat.ended ? (
        <footer className="hairline-t shrink-0 px-gutter py-4">
          <div className="mx-auto flex w-full max-w-[680px] items-end gap-3">
            <Textarea
              data-demo-id="chat-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Write your answer — Enter to send, Shift+Enter for a new line"
              rows={1}
              className="min-h-[44px] max-h-40 flex-1 resize-none rounded-warm"
            />
            <Button data-demo-id="btn-chat-send" disabled={!canSend} onClick={handleSend}>
              Send
            </Button>
            <button
              type="button"
              data-demo-id="btn-chat-skip"
              disabled={chat.isStreaming}
              onClick={() => {
                chat.skip();
                pinnedRef.current = true;
              }}
              className={cn(
                "h-10 shrink-0 px-1 text-small text-quiet underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                chat.isStreaming && "pointer-events-none opacity-50",
              )}
            >
              skip
            </button>
          </div>
        </footer>
      ) : null}
    </div>
  );
}
