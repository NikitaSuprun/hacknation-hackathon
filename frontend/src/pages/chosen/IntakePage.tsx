import { useState } from "react";
import { Link } from "react-router-dom";
import { IntakeForm } from "@/components/intake/IntakeForm";
import { IntakeSuccess } from "@/components/intake/IntakeSuccess";
import { PosterBackdrop } from "@/components/intake/PosterBackdrop";
import type { IntakeSubmission } from "@/lib/intake";

/**
 * Track H: the inbound "I was chosen" intake, standalone page at /chosen,
 * no investor shell. The fund evaluates PUBLIC work; the founder is only
 * telling us where to look.
 */
export default function IntakePage() {
  const [submission, setSubmission] = useState<IntakeSubmission | null>(null);

  return (
    <div className="min-h-screen bg-paper">
      {/* Compact hero on the paint poster. */}
      <header className="hairline-b relative overflow-hidden">
        <PosterBackdrop mono />
        <div className="relative mx-auto w-full max-w-grid px-gutter pb-12 pt-10">
          <Link
            to="/"
            className="mono-label inline-block transition-colors duration-120 ease-swift hover:text-ink"
          >
            Venture Hunt
          </Link>
          <h1 className="mt-10 font-display text-h1 text-ink">Put yourself on the radar.</h1>
          <p className="mt-4 max-w-measure-narrow text-body text-quiet">
            There is no pitch process here. That's the point. Our system reads public work: repositories,
            papers, registries. If you want to be found faster, tell us where to look.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-grid px-gutter py-12">
        <div className="mx-auto w-full max-w-[640px]">
          <p className="text-small text-quiet">
            Already have an invitation link? Open it from your email, it looks like{" "}
            <span className="font-mono text-mono-data text-ink">/interview/…</span>
          </p>
          <div className="mt-5">
            {submission ? <IntakeSuccess /> : <IntakeForm onDone={setSubmission} />}
          </div>
        </div>
      </main>
    </div>
  );
}
