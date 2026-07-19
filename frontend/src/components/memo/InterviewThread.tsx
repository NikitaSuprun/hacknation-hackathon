/**
 * The completed AI interview, replayed on the venture memo for the
 * investment team. Mirrors the founder chat's letter style: interviewer
 * turns flush-left behind a 2px ink rule, founder answers in warm wash
 * bubbles on the right, and investment-team follow-ups flush-left behind a
 * 2px electric-wash rule. The follow-up lane relays a question through the
 * founder's interview link and streams the scripted reply.
 *
 * Renders only in mock mode, for GraspLab, once the interview is completed.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AutoGrowTextarea } from "@/components/ui/auto-grow-textarea";
import { Button } from "@/components/ui/button";
import { dataSource } from "@/lib/data";
import type { ChatMessage } from "@/lib/domain/types";
import { FOLLOW_UP_REPLY } from "@/mocks/fixtures/chatScript";
import { GRASPLAB_ID } from "@/mocks/fixtures/seed";
import { getDB, getVersion, mutate, subscribe } from "@/mocks/state";

function timeOf(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function InterviewerTurn({ message }: { message: ChatMessage }) {
  return (
    <div className="border-l-2 border-ink pl-4">
      <p className="whitespace-pre-wrap text-body text-ink">{message.text}</p>
      <p className="mt-1 font-mono text-mono-label text-quiet">{timeOf(message.at)}</p>
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

function InvestorTurn({ message }: { message: ChatMessage }) {
  return (
    <div className="border-l-2 border-electric-wash pl-4">
      <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
        Investment team
      </p>
      <p className="mt-1 whitespace-pre-wrap text-body text-ink">{message.text}</p>
      <p className="mt-1 font-mono text-mono-label text-quiet">{timeOf(message.at)}</p>
    </div>
  );
}

/** The founder is typing: three pulsing dots inside a warm founder bubble. */
function FounderTypingDots() {
  return (
    <div className="flex justify-end" aria-label="The founder is typing">
      <div className="flex h-[2.625rem] items-center gap-1.5 rounded-warm bg-wash px-4">
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

/** In-flight scripted reply, revealed word by word in a founder bubble. */
function FounderStreamingTurn({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-warm bg-wash px-4 py-3">
        <p className="whitespace-pre-wrap text-body text-ink">
          {text}
          <span className="animate-pulse text-quiet">▍</span>
        </p>
      </div>
    </div>
  );
}

type ReplyPhase = "idle" | "typing" | "streaming";

function InterviewThreadInner({ transcript }: { transcript: ChatMessage[] }) {
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState<ReplyPhase>("idle");
  const [streamText, setStreamText] = useState("");

  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(
    () => () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
    },
    [],
  );

  // Pinned to the newest turn unless the reader scrolls up to reread.
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, [transcript.length, streamText, phase]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  const canSend = draft.trim().length > 0 && phase === "idle";

  const send = () => {
    const text = draft.trim();
    if (!text || phase !== "idle") return;
    mutate((db) => {
      db.interview.transcript.push({
        id: `investor-${Date.now()}`,
        role: "investor",
        text,
        at: new Date().toISOString(),
      });
    });
    setDraft("");
    pinnedRef.current = true;
    setPhase("typing");
    // A short typing pause, then the scripted reply word by word (~25ms).
    timeoutRef.current = setTimeout(() => {
      setPhase("streaming");
      const chunks = FOLLOW_UP_REPLY.split(/(?<=\s)/);
      let revealed = 0;
      intervalRef.current = setInterval(() => {
        revealed += 1;
        setStreamText(chunks.slice(0, revealed).join(""));
        if (revealed >= chunks.length) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          intervalRef.current = null;
          mutate((db) => {
            db.interview.transcript.push({
              id: `founder-followup-${Date.now()}`,
              role: "founder",
              text: FOLLOW_UP_REPLY,
              at: new Date().toISOString(),
            });
          });
          setStreamText("");
          setPhase("idle");
        }
      }, 25);
    }, 600);
  };

  return (
    <section className="mt-14">
      <div className="flex items-baseline justify-between gap-4">
        <p className="mono-label">AI interview · completed</p>
        <span className="font-mono text-mono-label tabular text-quiet">
          {transcript.length} turns
        </span>
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="mt-4 max-h-[480px] space-y-7 overflow-y-auto border-y border-line py-6"
      >
        {transcript.map((message) =>
          message.role === "interviewer" ? (
            <InterviewerTurn key={message.id} message={message} />
          ) : message.role === "investor" ? (
            <InvestorTurn key={message.id} message={message} />
          ) : (
            <FounderTurn key={message.id} message={message} />
          ),
        )}
        {phase === "typing" && <FounderTypingDots />}
        {phase === "streaming" && <FounderStreamingTurn text={streamText} />}
      </div>

      <div className="mt-4">
        <p className="mono-label">Ask a follow-up</p>
        <div className="mt-2 flex items-end gap-3">
          <AutoGrowTextarea
            data-demo-id="followup-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask the founder a follow-up question"
            maxRows={4}
            className="min-h-[44px] flex-1"
          />
          <Button
            variant="ink"
            data-demo-id="btn-followup-send"
            disabled={!canSend}
            onClick={send}
          >
            Send
          </Button>
        </div>
        <p className="mt-2 font-mono text-[11px] text-quiet">
          Replies are relayed through the founder&rsquo;s interview link.
        </p>
      </div>
    </section>
  );
}

/**
 * Gate: mock mode, GraspLab, completed interview. Subscribes to the mock
 * store so follow-up turns land in the transcript as they commit.
 */
export function InterviewThread({ ventureId }: { ventureId: string }) {
  useSyncExternalStore(subscribe, getVersion);
  const db = getDB();
  const eligible =
    dataSource().mode === "mock" &&
    ventureId === GRASPLAB_ID &&
    db.interview.stage === "completed";
  if (!eligible) return null;
  return <InterviewThreadInner transcript={db.interview.transcript} />;
}
