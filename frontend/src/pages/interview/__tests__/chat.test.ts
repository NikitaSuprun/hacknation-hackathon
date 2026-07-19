/**
 * Node-side smoke of the founder flow's data seam: consent → greeting stream →
 * a founder turn → exhaustion signalled as a bare done event. Exercises the
 * exact call pattern useStreamingChat makes.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { dataSource, _resetDataSourceForTests } from "@/lib/data";
import { setMockLatencyDisabled } from "@/lib/data/MockDataSource";
import { resetDB } from "@/mocks/state";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import type { ChatStreamEvent } from "@/lib/data/DataSource";

async function collect(stream: AsyncIterable<ChatStreamEvent>) {
  let text = "";
  let doneId: string | null = null;
  let tokens = 0;
  const errors: string[] = [];
  for await (const event of stream) {
    if (event.type === "token") {
      text += event.text;
      tokens += 1;
    } else if (event.type === "done") {
      doneId = event.messageId;
    } else {
      errors.push(event.message);
    }
  }
  return { text, doneId, tokens, errors };
}

describe("mock interview stream (founder flow seam)", () => {
  beforeAll(() => {
    _resetDataSourceForTests();
    resetDB();
    setMockLatencyDisabled(true);
  });

  afterAll(() => {
    setMockLatencyDisabled(false);
    resetDB();
    _resetDataSourceForTests();
  });

  it("walks consent, streams two turns, then signals the end with a bare done", async () => {
    const ds = dataSource();
    expect(ds.mode).toBe("mock");

    const bootstrap = await ds.getInterviewSession("demo");
    expect(bootstrap.stage).toBe("pending_consent");
    expect(bootstrap.transcript).toHaveLength(0);

    await ds.submitConsent("demo", { agreed: true, consent_text: "test consent" });
    const consented = await ds.getInterviewSession("demo");
    expect(consented.stage).toBe("consented");

    // Turn 1 — the greeting streams when called with "" on an empty transcript.
    const greeting = await collect(ds.streamInterviewMessage("demo", ""));
    expect(greeting.errors).toHaveLength(0);
    expect(greeting.tokens).toBeGreaterThan(1);
    expect(greeting.text).toBe(INTERVIEW_SCRIPT[0].ai);
    expect(greeting.doneId).toBe("ai-0");

    // Turn 2 — a founder reply streams the next scripted interviewer turn.
    const second = await collect(ds.streamInterviewMessage("demo", "Ready — go ahead."));
    expect(second.errors).toHaveLength(0);
    expect(second.tokens).toBeGreaterThan(1);
    expect(second.text).toBe(INTERVIEW_SCRIPT[1].ai);
    expect(second.doneId).toBe("ai-1");

    // Drain the remaining scripted turns.
    for (let i = 2; i < INTERVIEW_SCRIPT.length; i++) {
      const turn = await collect(ds.streamInterviewMessage("demo", `answer ${i}`));
      expect(turn.text).toBe(INTERVIEW_SCRIPT[i].ai);
      expect(turn.doneId).toBe(`ai-${i}`);
    }

    // Exhausted script — the next call yields only done, no tokens: the
    // signal the UI uses to surface "Finish — complete my candidacy".
    const exhausted = await collect(ds.streamInterviewMessage("demo", "anything else?"));
    expect(exhausted.tokens).toBe(0);
    expect(exhausted.text).toBe("");
    expect(exhausted.doneId).toBe("end-of-script");

    await ds.completeInterview("demo");
    const done = await ds.getInterviewSession("demo");
    expect(done.stage).toBe("completed");
    expect(done.transcript.length).toBeGreaterThan(0);
  });

  it("aborts mid-stream without committing the interviewer turn", async () => {
    resetDB();
    const ds = dataSource();
    const controller = new AbortController();
    let tokens = 0;
    for await (const event of ds.streamInterviewMessage("demo", "", controller.signal)) {
      if (event.type === "token") {
        tokens += 1;
        if (tokens === 2) controller.abort();
      }
      if (event.type === "done") throw new Error("stream should have stopped before done");
    }
    expect(tokens).toBe(2);
    const session = await ds.getInterviewSession("demo");
    expect(session.transcript).toHaveLength(0);
  });

  it("yields an error event for an unknown token", async () => {
    const ds = dataSource();
    const result = await collect(ds.streamInterviewMessage("nope", ""));
    expect(result.errors).toHaveLength(1);
    expect(result.doneId).toBeNull();
  });
});
