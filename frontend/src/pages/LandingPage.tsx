import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

/**
 * TODO(Phase 2): full hero — CHOSEN at display-xl with the paint swirl
 * (option A: swirl inside letterforms; option B: full-bleed behind veil),
 * 01 Signals / 02 Scored / 03 Chosen columns, footer.
 */
export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <main className="mx-auto flex w-full max-w-grid flex-1 flex-col items-start justify-center px-gutter py-section">
        <p className="mono-label mb-6">Maschmeyer's Chosen Portfolio</p>
        <h1 className="font-display text-display-xl text-ink">CHOSEN</h1>
        <p className="mt-6 max-w-measure-narrow text-h3 font-normal">
          <span className="text-quiet">You don't apply.</span>{" "}
          <span className="text-ink">You get chosen.</span>
        </p>
        <div className="mt-10 flex gap-4">
          <Button asChild size="lg">
            <Link to="/login">I'm investing</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link to="/interview/demo">I was chosen</Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
