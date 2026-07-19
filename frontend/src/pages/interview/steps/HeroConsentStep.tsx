/**
 * Step 1, the letter opens. Full-viewport hero on the paint poster:
 * "You've been chosen." with a per-word rise, then the consent card -
 * why you, what we hold, the consent text (server-verbatim when present),
 * data rights, and the one decision on the page. Declining is one click
 * and ends politely; no guilt.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { dataSource } from "@/lib/data";
import type { InterviewBootstrap } from "@/lib/domain/types";
import { PaintPoster } from "@/components/founder/PaintPoster";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

const HEADLINE_WORDS = ["You've", "been", "chosen."];

function standardConsentText(fundName: string): string {
  return `I agree to share what I tell this interview with ${fundName} for the purpose of this review. I can view or delete everything at any time.`;
}

export function HeroConsentStep({
  session,
  refresh,
}: {
  session: InterviewBootstrap;
  refresh: () => Promise<void>;
}) {
  const ds = dataSource();
  const [agreed, setAgreed] = useState(false);
  const [declined, setDeclined] = useState(false);

  const consentText = session.consent_prompt?.trim() || standardConsentText(session.fund_name);

  const consent = useMutation({
    mutationFn: async () => {
      await ds.submitConsent(session.token, { agreed: true, consent_text: consentText });
      await refresh();
    },
  });

  const decline = useMutation({
    mutationFn: () =>
      ds.submitConsent(session.token, { agreed: false, consent_text: consentText }),
    onSettled: () => setDeclined(true),
  });

  if (declined) {
    return (
      <div className="relative min-h-screen overflow-hidden bg-paper">
        <PaintPoster />
        <main className="relative z-10 flex min-h-screen items-center justify-center px-gutter py-section">
          <Card className="w-full max-w-[560px] animate-fade-up rounded-warm border-line p-7 shadow-lift">
            <p className="mono-label mb-4">{session.fund_name}</p>
            <h1 className="font-display text-h2 text-ink">Understood.</h1>
            <p className="mt-3 text-body text-quiet">
              We won't contact you again. We'll delete your data on request:{" "}
              <span className="font-mono text-mono-data">{session.fund_contact_email}</span>.
            </p>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-paper">
      <PaintPoster />
      <main className="relative z-10 mx-auto flex min-h-screen w-full max-w-grid flex-col items-center justify-center px-gutter py-12">
        <div className="text-center">
          <p className="mono-label animate-fade-in">A message from {session.fund_name}</p>
          {/* Sized so the consent decision stays above the fold on a laptop. */}
          <h1 className="mt-5 font-display text-[clamp(2.75rem,6vw,4.5rem)] font-medium leading-[1.02] tracking-[-0.02em] text-ink">
            {HEADLINE_WORDS.map((word, i) => (
              <span
                key={word}
                className="inline-block animate-fade-up"
                style={{ animationDelay: `${120 + i * 90}ms` }}
              >
                {word}
                {i < HEADLINE_WORDS.length - 1 ? " " : ""}
              </span>
            ))}
          </h1>
          <p
            className="mx-auto mt-5 max-w-measure animate-fade-up text-h4 font-normal text-quiet"
            style={{ animationDelay: "420ms" }}
          >
            {session.fund_name} reviewed your public work on {session.venture_name}. You were
            already selected. This is a chance to fill in the gaps.
          </p>
        </div>

        <Card
          className="mt-8 w-full max-w-[560px] animate-fade-up rounded-warm border-line bg-paper p-7 text-left shadow-lift"
          style={{ animationDelay: "560ms" }}
        >
          <section>
            <p className="mono-label mb-2">Why you</p>
            <p className="text-body text-ink">{session.why_contacted}</p>
          </section>

          {session.data_sources.length > 0 ? (
            <section className="mt-6">
              <p className="mono-label mb-2">What we hold</p>
              <ul className="space-y-2">
                {session.data_sources.map((source) => (
                  <li key={source.url} className="text-small text-ink">
                    {source.label}
                    <span className="mt-0.5 block font-mono text-mono-label normal-case text-quiet">
                      {source.url}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <Separator className="my-6" />

          <p className="text-small text-ink">{consentText}</p>
          <p className="mt-3 font-mono text-mono-label text-quiet">
            Your data, your call: view · delete · {session.fund_contact_email}
          </p>

          <div className="mt-6 flex items-start gap-3">
            <Checkbox
              id="consent-agree"
              data-demo-id="consent-agree"
              checked={agreed}
              onCheckedChange={(value) => setAgreed(value === true)}
              className="mt-0.5"
            />
            <Label htmlFor="consent-agree" className="cursor-pointer text-small leading-snug">
              I've read the above and I agree.
            </Label>
          </div>

          <div className="mt-6 flex items-center justify-between gap-4">
            <Button
              data-demo-id="btn-consent-continue"
              disabled={!agreed || consent.isPending}
              onClick={() => consent.mutate()}
            >
              {consent.isPending ? "One moment…" : "Agree and continue"}
            </Button>
            <button
              type="button"
              onClick={() => decline.mutate()}
              disabled={decline.isPending || consent.isPending}
              className="text-small text-quiet underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Not interested
            </button>
          </div>
          {consent.isError ? (
            <p className="mt-3 text-small text-danger">
              That didn't go through, try again in a moment.
            </p>
          ) : null}
        </Card>
      </main>
    </div>
  );
}
