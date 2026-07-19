import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { IDEA_MAX_CHARS, submitIntake, type IntakeSubmission } from "@/lib/intake";
import { TeamRepeater, type TeamRow } from "./TeamRepeater";

const GITHUB_RE = /^https?:\/\/(www\.)?github\.com\/.+/i;
const LINKEDIN_RE = /^https?:\/\/(www\.)?linkedin\.com\/.+/i;
const URLISH_RE = /^(https?:\/\/)?[^\s]+\.[^\s]+$/i;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FieldErrors = Partial<
  Record<"work" | "github" | "linkedin" | "website" | "email", string>
>;

function FieldHead({ htmlFor, children }: { htmlFor: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between">
      <Label htmlFor={htmlFor}>{children}</Label>
      <span className="font-mono text-mono-label text-quiet">optional</span>
    </div>
  );
}

function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="text-small text-danger">
      {children}
    </p>
  );
}

/**
 * The intake card. Everything is individually optional — the only rule is
 * that at least one of GitHub / LinkedIn / website is present, because the
 * system evaluates public work and needs somewhere to look.
 */
export function IntakeForm({ onDone }: { onDone: (record: IntakeSubmission) => void }) {
  const [github, setGithub] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [website, setWebsite] = useState("");
  const [projectName, setProjectName] = useState("");
  const [idea, setIdea] = useState("");
  const [team, setTeam] = useState<TeamRow[]>([]);
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [pending, setPending] = useState(false);

  const clearError = (...keys: (keyof FieldErrors)[]) => {
    setErrors((prev) => {
      const next = { ...prev };
      for (const key of keys) delete next[key];
      return next;
    });
  };

  const handleSend = async () => {
    const g = github.trim();
    const l = linkedin.trim();
    const w = website.trim();
    const mail = email.trim();

    const errs: FieldErrors = {};
    if (!g && !l && !w) errs.work = "Point us at least one place your work lives.";
    if (g && !GITHUB_RE.test(g))
      errs.github = "That doesn't look like a GitHub link — it should start with https://github.com/";
    if (l && !LINKEDIN_RE.test(l))
      errs.linkedin = "That doesn't look like a LinkedIn link — it should start with https://linkedin.com/";
    if (w && !URLISH_RE.test(w)) errs.website = "That doesn't look like a link.";
    if (mail && !EMAIL_RE.test(mail)) errs.email = "That doesn't look like an email address.";
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setPending(true);
    try {
      const record = await submitIntake({
        github_url: g || null,
        linkedin_url: l || null,
        website_url: w || null,
        project_name: projectName.trim() || null,
        project_idea: idea.trim() || null,
        team: team
          .map((row) => ({
            name: row.name.trim(),
            role: row.role.trim() || null,
            github_url: row.github.trim() || null,
          }))
          .filter((row) => row.name || row.role || row.github_url),
        contact_email: mail || null,
      });
      toast.success("You're on the radar.", {
        description: "We'll read what you shared and take it from there.",
      });
      onDone(record);
    } finally {
      setPending(false);
    }
  };

  return (
    <Card className="rounded-warm p-7">
      {/* Where the work lives — the one thing we actually need. */}
      <div className="space-y-5">
        <div className="space-y-2">
          <FieldHead htmlFor="intake-github">GitHub</FieldHead>
          <Input
            id="intake-github"
            data-demo-id="intake-github"
            type="url"
            inputMode="url"
            placeholder="https://github.com/…"
            value={github}
            onChange={(e) => {
              setGithub(e.target.value);
              clearError("github", "work");
            }}
            aria-invalid={Boolean(errors.github || errors.work)}
            aria-describedby={errors.github ? "intake-github-error" : undefined}
          />
          {errors.github ? (
            <FieldError id="intake-github-error">{errors.github}</FieldError>
          ) : (
            <p className="font-mono text-mono-label text-quiet">the strongest signal</p>
          )}
        </div>

        <div className="space-y-2">
          <FieldHead htmlFor="intake-linkedin">LinkedIn</FieldHead>
          <Input
            id="intake-linkedin"
            data-demo-id="intake-linkedin"
            type="url"
            inputMode="url"
            placeholder="https://linkedin.com/in/…"
            value={linkedin}
            onChange={(e) => {
              setLinkedin(e.target.value);
              clearError("linkedin", "work");
            }}
            aria-invalid={Boolean(errors.linkedin || errors.work)}
            aria-describedby={errors.linkedin ? "intake-linkedin-error" : undefined}
          />
          {errors.linkedin && <FieldError id="intake-linkedin-error">{errors.linkedin}</FieldError>}
        </div>

        <div className="space-y-2">
          <FieldHead htmlFor="intake-website">Website or other link</FieldHead>
          <Input
            id="intake-website"
            type="url"
            inputMode="url"
            placeholder="https://…"
            value={website}
            onChange={(e) => {
              setWebsite(e.target.value);
              clearError("website", "work");
            }}
            aria-invalid={Boolean(errors.website || errors.work)}
            aria-describedby={errors.website ? "intake-website-error" : undefined}
          />
          {errors.website && <FieldError id="intake-website-error">{errors.website}</FieldError>}
        </div>

        {errors.work && <FieldError id="intake-work-error">{errors.work}</FieldError>}
      </div>

      {/* The project, in the founder's own words. */}
      <div className="hairline-t mt-6 space-y-5 pt-6">
        <div className="space-y-2">
          <FieldHead htmlFor="intake-project-name">Project name</FieldHead>
          <Input
            id="intake-project-name"
            data-demo-id="intake-project-name"
            placeholder="What do you call it?"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <FieldHead htmlFor="intake-idea">What are you building?</FieldHead>
          <Textarea
            id="intake-idea"
            data-demo-id="intake-idea"
            className="min-h-[120px]"
            maxLength={IDEA_MAX_CHARS}
            placeholder="One paragraph. What it does, who it's for, what's live today."
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
          />
          <p className="tabular text-right font-mono text-mono-label text-quiet">
            {idea.length} / {IDEA_MAX_CHARS}
          </p>
        </div>
      </div>

      {/* Team + contact. */}
      <div className="hairline-t mt-6 space-y-5 pt-6">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <Label>Team</Label>
            <span className="font-mono text-mono-label text-quiet">optional</span>
          </div>
          <TeamRepeater rows={team} onChange={setTeam} />
        </div>

        <div className="space-y-2">
          <FieldHead htmlFor="intake-email">Contact email</FieldHead>
          <Input
            id="intake-email"
            data-demo-id="intake-email"
            type="email"
            inputMode="email"
            placeholder="you@…"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              clearError("email");
            }}
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "intake-email-error" : undefined}
          />
          {errors.email ? (
            <FieldError id="intake-email-error">{errors.email}</FieldError>
          ) : (
            <p className="font-mono text-mono-label text-quiet">only used if you're chosen</p>
          )}
        </div>
      </div>

      <div className="mt-7">
        {/* Ink, not electric: the accent is reserved for the fund choosing
            someone. Raising your hand is a different act. */}
        <Button
          type="button"
          variant="ink"
          size="lg"
          className="w-full"
          data-demo-id="btn-intake-submit"
          disabled={pending}
          onClick={handleSend}
        >
          {pending ? "Putting you on the radar…" : "Point us at your work"}
        </Button>
        <p className="mt-4 font-mono text-mono-label text-quiet">
          We'll evaluate public signals around what you share. No account is created. Ask us to
          delete anything, any time.
        </p>
      </div>
    </Card>
  );
}
