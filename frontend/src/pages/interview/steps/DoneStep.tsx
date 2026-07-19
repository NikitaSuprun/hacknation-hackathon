/**
 * Step 4, the calm close. The candidacy is complete; a partner reviews the
 * update this week and the founder hears either way. Data rights stay in
 * mono smallprint, and in demo mode a collapsed transcript recap sits below.
 */
import { dataSource } from "@/lib/data";
import type { InterviewBootstrap } from "@/lib/domain/types";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export function DoneStep({ session }: { session: InterviewBootstrap }) {
  const ds = dataSource();

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-gutter py-16">
      <div className="w-full max-w-[560px]">
        <Card className="animate-fade-up rounded-warm border-line p-7 shadow-lift">
          <p className="mono-label mb-4">{session.fund_name}</p>
          <h1 className="font-display text-h2 text-ink">
            Thank you. Your candidacy is complete.
          </h1>
          <p className="mt-4 text-body text-quiet">
            A partner reviews the update this week. You'll hear directly from{" "}
            {session.fund_name} either way.
          </p>
          <Separator className="my-6" />
          <p className="font-mono text-mono-label text-quiet">
            Your data, your call: view · delete · {session.fund_contact_email}
          </p>
        </Card>

        {ds.mode === "mock" && session.transcript.length > 0 ? (
          <details className="mt-5 animate-fade-up rounded-warm border border-line px-5 py-4">
            <summary className="mono-label cursor-pointer list-none select-none">
              Transcript recap, {session.transcript.length} turns
            </summary>
            <div className="mt-4 space-y-4">
              {session.transcript.map((message) => (
                <div key={message.id}>
                  <p className="font-mono text-mono-label text-quiet">
                    {message.role === "interviewer" ? "interviewer" : "you"}
                  </p>
                  <p className="mt-0.5 whitespace-pre-wrap text-small text-ink">{message.text}</p>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}
