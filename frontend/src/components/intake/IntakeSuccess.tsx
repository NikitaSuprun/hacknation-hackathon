import { Link } from "react-router-dom";
import { Card } from "@/components/ui/card";

/**
 * Success state — swapped in for the intake card after a send. The electric
 * mono-label is the one accent in this region.
 */
export function IntakeSuccess() {
  return (
    <Card className="animate-fade-up rounded-warm p-7">
      <p className="mono-label text-ink">On the radar</p>
      <h2 className="mt-3 font-display text-h2 text-ink">Done — we'll take it from here.</h2>
      <p className="mt-4 text-body text-quiet">
        Our system will read what you shared and score it against every active thesis. If a fund
        chooses you, you'll get a personal invitation — not a newsletter.
      </p>
      <Link
        to="/"
        className="mt-6 inline-block text-small text-quiet underline underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink"
      >
        Back to start
      </Link>
    </Card>
  );
}
