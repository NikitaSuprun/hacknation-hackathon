/**
 * Step 2, "Complete your candidacy". The research is already done; these
 * fields close the gaps: LinkedIn, GitHub (mock-prefilled with a confirm
 * tick), CV + pitch dropzones, and a traction note. Everything is optional;
 * the CTA arms once anything is touched, and a quiet skip goes straight to
 * the interview.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { dataSource } from "@/lib/data";
import type { InterviewBootstrap, StructuredAsks, UploadedFileRef } from "@/lib/domain/types";
import { FileDropzone } from "@/components/founder/FileDropzone";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const MOCK_GITHUB_PREFILL = "https://github.com/lenafischer";
const TRACTION_LIMIT = 600;

export function CandidacyStep({
  session,
  refresh,
  onSkip,
}: {
  session: InterviewBootstrap;
  refresh: () => Promise<void>;
  onSkip: () => void;
}) {
  const ds = dataSource();
  const isMock = ds.mode === "mock";

  const [linkedin, setLinkedin] = useState(session.structured?.linkedin_url ?? "");
  const [github, setGithub] = useState(
    session.structured?.github_url ?? (isMock ? MOCK_GITHUB_PREFILL : ""),
  );
  const [githubConfirmed, setGithubConfirmed] = useState(false);
  const [cv, setCv] = useState<UploadedFileRef | null>(session.structured?.cv_file ?? null);
  const [pitch, setPitch] = useState<UploadedFileRef | null>(
    session.structured?.pitch_file ?? null,
  );
  const [traction, setTraction] = useState(session.structured?.traction_notes ?? "");

  const linkedinLooksOff =
    linkedin.trim().length > 0 && !linkedin.toLowerCase().includes("linkedin.com/in/");
  const githubIsPrefill = isMock && github === MOCK_GITHUB_PREFILL;
  const touched =
    linkedin.trim().length > 0 ||
    githubConfirmed ||
    (github.trim().length > 0 && !githubIsPrefill) ||
    cv !== null ||
    pitch !== null ||
    traction.trim().length > 0;

  const save = useMutation({
    mutationFn: async () => {
      const asks: StructuredAsks = {
        linkedin_url: linkedin.trim() || null,
        github_url: github.trim() || null,
        cv_file: cv,
        pitch_file: pitch,
        traction_notes: traction.trim() || null,
      };
      await ds.submitStructuredAsks(session.token, asks);
      await refresh();
    },
  });

  return (
    <div className="min-h-screen bg-paper">
      <main className="mx-auto w-full max-w-[720px] px-gutter py-16">
        <header className="animate-fade-up">
          <p className="mono-label">
            {session.fund_name} · {session.venture_name}
          </p>
          <h1 className="mt-4 font-display text-h1 text-ink">Complete your candidacy</h1>
          <p className="mt-3 text-body text-quiet">
            The research is already done. Help us fill in the gaps.
          </p>
        </header>

        <div className="mt-10 space-y-5">
          <Card
            className="animate-fade-up rounded-warm border-line p-6"
            style={{ animationDelay: "80ms" }}
          >
            <div className="mb-3 flex items-baseline justify-between">
              <Label htmlFor="candidacy-linkedin">LinkedIn</Label>
              <span className="mono-label">recommended</span>
            </div>
            <Input
              id="candidacy-linkedin"
              data-demo-id="candidacy-linkedin"
              type="url"
              inputMode="url"
              placeholder="https://www.linkedin.com/in/…"
              value={linkedin}
              onChange={(e) => setLinkedin(e.target.value)}
            />
            {linkedinLooksOff ? (
              <p className="mt-2 text-small text-danger">
                That doesn't look like a linkedin.com/in/ profile link.
              </p>
            ) : null}
          </Card>

          <Card
            className="animate-fade-up rounded-warm border-line p-6"
            style={{ animationDelay: "140ms" }}
          >
            <div className="mb-3 flex items-baseline justify-between">
              <Label htmlFor="candidacy-github">GitHub</Label>
              <span className="mono-label">optional</span>
            </div>
            <Input
              id="candidacy-github"
              data-demo-id="candidacy-github"
              type="url"
              inputMode="url"
              placeholder="https://github.com/…"
              value={github}
              onChange={(e) => {
                setGithub(e.target.value);
                setGithubConfirmed(false);
              }}
            />
            {githubIsPrefill ? (
              githubConfirmed ? (
                <p className="mt-2 flex items-center gap-1.5 font-mono text-mono-label text-quiet">
                  <Check className="h-3.5 w-3.5 text-ink" strokeWidth={2.5} />
                  confirmed, thanks
                </p>
              ) : (
                <div className="mt-2 flex items-center justify-between gap-3">
                  <p className="font-mono text-mono-label text-quiet">
                    we found this, confirm it's you
                  </p>
                  <button
                    type="button"
                    onClick={() => setGithubConfirmed(true)}
                    className="inline-flex items-center gap-1.5 rounded-ctrl border border-line-strong px-2.5 py-1 font-mono text-mono-label uppercase text-ink transition-colors duration-120 ease-swift hover:bg-wash focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
                    that's me
                  </button>
                </div>
              )
            ) : null}
          </Card>

          <Card
            className="animate-fade-up rounded-warm border-line p-6"
            style={{ animationDelay: "200ms" }}
          >
            <div className="mb-3 flex items-baseline justify-between">
              <Label>CV</Label>
              <span className="mono-label">optional</span>
            </div>
            <FileDropzone
              demoId="candidacy-cv-drop"
              prompt="Drop your CV here, PDF, max 10 MB"
              maxBytes={10 * 1024 * 1024}
              durationMs={1400}
              file={cv}
              onUpload={(file) => ds.uploadInterviewFile(session.token, "cv", file)}
              onDone={setCv}
              onClear={() => setCv(null)}
            />
          </Card>

          <Card
            className="animate-fade-up rounded-warm border-line p-6"
            style={{ animationDelay: "260ms" }}
          >
            <div className="mb-3 flex items-baseline justify-between">
              <Label>Pitch deck</Label>
              <span className="mono-label">optional</span>
            </div>
            <FileDropzone
              demoId="candidacy-pitch-drop"
              prompt="Drop your pitch here, PDF"
              note="Optional. Only if you have one handy. We don't judge slides. We judge signals."
              maxBytes={25 * 1024 * 1024}
              durationMs={2200}
              file={pitch}
              onUpload={(file) => ds.uploadInterviewFile(session.token, "pitch", file)}
              onDone={setPitch}
              onClear={() => setPitch(null)}
            />
          </Card>

          <Card
            className="animate-fade-up rounded-warm border-line p-6"
            style={{ animationDelay: "320ms" }}
          >
            <div className="mb-3 flex items-baseline justify-between gap-4">
              <Label htmlFor="candidacy-traction">Anything the public record misses?</Label>
              <span className="shrink-0 font-mono text-mono-label text-quiet">
                {traction.length} / {TRACTION_LIMIT}
              </span>
            </div>
            <Textarea
              id="candidacy-traction"
              data-demo-id="candidacy-traction"
              placeholder="Pilots, revenue, waitlists, LOIs, numbers welcome"
              maxLength={TRACTION_LIMIT}
              rows={4}
              value={traction}
              onChange={(e) => setTraction(e.target.value)}
            />
          </Card>
        </div>

        <footer className="mt-10 animate-fade-up" style={{ animationDelay: "380ms" }}>
          {isMock ? (
            <p className="mb-4 font-mono text-mono-label text-quiet">
              Demo, nothing is uploaded, files stay in your browser.
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-5">
            <Button
              data-demo-id="btn-continue-interview"
              size="lg"
              disabled={!touched || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? "Saving…" : "Continue to interview"}
            </Button>
            <button
              type="button"
              onClick={onSkip}
              disabled={save.isPending}
              className="text-small text-quiet underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Skip for now, go to the interview
            </button>
          </div>
          {save.isError ? (
            <p className="mt-3 text-small text-danger">
              That didn't save, try again in a moment.
            </p>
          ) : null}
        </footer>
      </main>
    </div>
  );
}
