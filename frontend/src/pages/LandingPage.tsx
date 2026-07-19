import { Fragment } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { PosterBackdrop } from "@/components/intake/PosterBackdrop";

/** Tagline words rise one by one — ~90ms stagger, transform/opacity only. */
const TAGLINE: { word: string; tone: "quiet" | "ink" }[] = [
  { word: "You", tone: "quiet" },
  { word: "don't", tone: "quiet" },
  { word: "apply.", tone: "quiet" },
  { word: "You", tone: "ink" },
  { word: "get", tone: "ink" },
  { word: "chosen.", tone: "ink" },
];

const COLUMNS = [
  {
    num: "01",
    title: "Signals",
    body: "We read public work — GitHub, arXiv, the Swiss registry. Nobody fills anything in.",
  },
  {
    num: "02",
    title: "Scored",
    body: "Nine weighted categories. Every claim cited, every gap admitted.",
  },
  {
    num: "03",
    title: "Chosen",
    body: "Partners decide. Founders get a personal invitation — never a form.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      {/* Hero on the paint poster — subtle; the wordmark carries the page. */}
      <section className="relative overflow-hidden">
        <PosterBackdrop subtle />
        <div className="relative mx-auto flex min-h-[85vh] w-full max-w-grid flex-col items-start justify-center px-gutter py-section">
          <p className="mono-label mb-6 animate-fade-in">Maschmeyer's Chosen Portfolio</p>
          <h1 className="font-display text-display-xl text-ink">CHOSEN</h1>
          <p className="mt-6 max-w-measure-narrow text-h3 font-normal">
            {TAGLINE.map(({ word, tone }, i) => (
              <Fragment key={i}>
                <span
                  className={`inline-block animate-fade-up ${tone === "quiet" ? "text-quiet" : "text-ink"}`}
                  style={{ animationDelay: `${120 + i * 90}ms` }}
                >
                  {word}
                </span>
                {i < TAGLINE.length - 1 && " "}
              </Fragment>
            ))}
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Button asChild size="lg">
              <Link to="/login">I'm investing</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link to="/chosen">I was chosen</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Below the fold: how it works, in three 34ch columns. */}
      <section className="hairline-t">
        <div className="mx-auto grid w-full max-w-grid gap-10 px-gutter py-16 md:grid-cols-3">
          {COLUMNS.map(({ num, title, body }) => (
            <div key={num}>
              <p className="mono-label">
                {num} {title}
              </p>
              <p className="mt-3 max-w-measure-narrow text-body text-ink">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="hairline-t mt-auto">
        <div className="mx-auto flex w-full max-w-grid flex-col gap-2 px-gutter py-8 sm:flex-row sm:items-center sm:justify-between">
          <span className="mono-label">Maschmeyer's Chosen Portfolio</span>
          <span className="mono-label">
            Public signals only · ask us to delete anything, any time
          </span>
        </div>
      </footer>
    </div>
  );
}
