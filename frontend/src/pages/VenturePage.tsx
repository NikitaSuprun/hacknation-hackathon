import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { CategoryBreakdown } from "@/components/scores/CategoryBreakdown";
import { FundingBadge } from "@/components/scores/FundingBadge";
import { QualityChip } from "@/components/scores/QualityChip";
import { StatusChip } from "@/components/scores/StatusChip";
import { InterviewThread } from "@/components/memo/InterviewThread";
import { MemoSectionView } from "@/components/memo/MemoSectionView";
import { MissingDataPanel } from "@/components/memo/MissingDataPanel";
import {
  COLD_START_HINT,
  categoryScoresOfSnapshot,
  useColdStartHint,
  useVenture,
  useVentureGaps,
  useVentureMemo,
  useVentureScores,
  useVentureTeam,
  useWeights,
} from "@/hooks/useInvestorData";
import { celebrate } from "@/lib/celebration";
import { dataSource } from "@/lib/data";
import type {
  OutreachRequest,
  RankedVenture,
  VentureTeamMember,
} from "@/lib/domain/types";
import { MEMO_SECTION_KEYS } from "@/lib/domain/types";
import { categoryScoresOf, computeFinalScore } from "@/lib/ranking/rerank";
import { FUND_EMAIL, FUND_NAME, getDB, getVersion, mutate, subscribe } from "@/mocks/state";
import { cn, formatPercent, formatScore } from "@/lib/utils";

/** ASCII-fold a name into an email-safe token: "Léna Fischer" → "lena.fischer". */
function emailToken(value: string, separator: string): string {
  return (
    value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, separator)
      .replace(new RegExp(`^\\${separator}+|\\${separator}+$`, "g"), "") || "founder"
  );
}

/** Mock prefill only — a plausible, clearly fictional public contact. */
function founderContact(venture: RankedVenture, founder?: VentureTeamMember): string {
  if (venture.name === "GraspLab") return "lena.fischer@ethz.ch";
  const person = emailToken(founder?.full_name ?? "founder", ".");
  const domain = emailToken(venture.name, "");
  return `${person}@${domain}.example`;
}

function composeDraft(venture: RankedVenture, founder?: VentureTeamMember): OutreachRequest {
  const firstName = founder?.full_name?.split(/\s+/)[0] ?? "there";
  const provenance = founder?.github_login
    ? `your repository ${founder.github_login}/* and your public research`
    : "your public work and shipped research";
  return {
    to_email: founderContact(venture, founder),
    subject: `Your work on ${venture.name}`,
    body: [
      `Hi ${firstName},`,
      "",
      `We came across ${provenance} behind ${venture.name} — ${venture.one_liner}`,
      "",
      `This is why you: the pace of what you have shipped, the evidence trail behind it, and the fit with our current thesis at ${FUND_NAME}.`,
      "",
      "Nothing here is an application — you were selected. A one-click opt-out link is included.",
      "",
      `— ${FUND_NAME} · ${FUND_EMAIL}`,
    ].join("\n"),
  };
}

function ComposeDialog({
  venture,
  founder,
  open,
  onOpenChange,
}: {
  venture: RankedVenture;
  founder?: VentureTeamMember;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const ds = dataSource();
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [toEmail, setToEmail] = useState("");
  const confirmRef = useRef<HTMLButtonElement>(null);
  const originRef = useRef<{ x: number; y: number } | undefined>(undefined);

  useEffect(() => {
    if (!open) return;
    const draft = composeDraft(venture, founder);
    setToEmail(draft.to_email);
    setSubject(draft.subject);
    setBody(draft.body);
  }, [open, venture, founder]);

  const send = useMutation({
    mutationFn: (request: OutreachRequest) => ds.sendOutreach(venture.venture_id, request),
    onSuccess: () => {
      celebrate({
        ventureId: venture.venture_id,
        ventureName: venture.name,
        founderName: founder?.full_name,
        origin: originRef.current,
      });
      toast(`Invitation sent. ${venture.name} has been chosen.`);
      queryClient.invalidateQueries({ queryKey: ["ranking"] });
      queryClient.invalidateQueries({ queryKey: ["outreach"] });
      onOpenChange(false);
    },
    onError: (error) =>
      toast.error(
        `Send failed${error instanceof Error ? ` — ${error.message}` : ""}. Try again.`,
      ),
  });

  const confirm = () => {
    const rect = confirmRef.current?.getBoundingClientRect();
    originRef.current = rect
      ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
      : undefined;
    send.mutate({ to_email: toEmail, subject, body });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Schedule the AI interview with {venture.name}</DialogTitle>
          <DialogDescription>
            Provenance-first email to the founder&rsquo;s public contact.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="mono-label">Founder&rsquo;s public contact</Label>
            <p className="mt-1.5 font-mono text-mono-data text-ink">{toEmail}</p>
          </div>
          <div>
            <Label htmlFor="outreach-subject" className="mono-label">
              Subject
            </Label>
            <Input
              id="outreach-subject"
              className="mt-1.5"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="outreach-body" className="mono-label">
              Body
            </Label>
            <Textarea
              id="outreach-body"
              className="mt-1.5 min-h-[220px] text-small"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          <p className="font-mono text-[11px] text-quiet">
            Source disclosure and opt-out are required and included automatically.
          </p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={send.isPending}>
            Cancel
          </Button>
          <Button
            ref={confirmRef}
            data-demo-id="btn-confirm-send"
            onClick={confirm}
            disabled={send.isPending || toEmail.length === 0}
          >
            {send.isPending ? "Sending…" : "Send invitation"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TeamSection({ members }: { members: VentureTeamMember[] }) {
  if (members.length === 0) {
    return <p className="mt-2 text-small text-quiet">No team members resolved yet.</p>;
  }
  return (
    <div className="mt-2">
      {members.map((member) => (
        <div key={member.person_id} className="hairline-b py-2.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-small font-medium text-ink">
              {member.full_name}
              {member.is_founder_guess && (
                <span className="ml-2 font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                  founder?
                </span>
              )}
            </span>
            {member.role_hint && (
              <span className="shrink-0 rounded-full border border-line px-2 py-0.5 font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                {member.role_hint}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-baseline gap-x-3 font-mono text-[11px] text-quiet">
            {member.github_login && <span>gh:{member.github_login}</span>}
            {member.orcid && <span>orcid:{member.orcid}</span>}
            {member.affiliation && <span>{member.affiliation}</span>}
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <div className="h-0.5 w-full max-w-[10rem] overflow-hidden bg-wash">
              <div
                className="h-full w-full origin-left bg-ink"
                style={{ transform: `scaleX(${Math.max(0, Math.min(1, member.weight))})` }}
              />
            </div>
            <span className="font-mono text-[11px] tabular text-quiet">
              {member.weight.toFixed(2)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * The venture memo detail: score header with the post-interview delta banner,
 * 9-category breakdown, evidence-cited memo, the completed-interview thread,
 * missing-data panel, team, and the action rail — schedule the AI interview
 * (the page's single accent) and start the investment process.
 */
export default function VenturePage() {
  const { ventureId = "", thesisId = "" } = useParams();
  const ds = dataSource();
  const queryClient = useQueryClient();
  const { venture, isLoading: rankingLoading } = useVenture(thesisId, ventureId);
  const scoresQuery = useVentureScores(ventureId);
  const memoQuery = useVentureMemo(ventureId);
  const teamQuery = useVentureTeam(ventureId);
  const gapsQuery = useVentureGaps(ventureId);
  const weightsQuery = useWeights(thesisId);
  const coldStart = useColdStartHint(rankingLoading);

  const [versionIndex, setVersionIndex] = useState<0 | 1>(0);
  const [composeOpen, setComposeOpen] = useState(false);

  const weights = weightsQuery.data;
  const snapshots = scoresQuery.data ?? [];
  const hasHistory = snapshots.length >= 2;
  const selectedSnapshot = snapshots[hasHistory ? versionIndex : 0];

  // Finals computed over each snapshot's categories with CURRENT weights, so
  // the numbers here match the ranked list to the decimal.
  const snapshotFinals = useMemo(() => {
    if (!weights) return [];
    return snapshots.map((s) => computeFinalScore(categoryScoresOfSnapshot(s), weights));
  }, [snapshots, weights]);

  const displayScores = useMemo(() => {
    if (selectedSnapshot) return categoryScoresOfSnapshot(selectedSnapshot);
    if (venture) return categoryScoresOf(venture);
    return null;
  }, [selectedSnapshot, venture]);

  const displayFinal =
    selectedSnapshot && weights
      ? snapshotFinals[hasHistory ? versionIndex : 0]
      : venture?.final_score;
  const displayConfidence = selectedSnapshot?.confidence ?? venture?.confidence;
  const displayBreakdown = selectedSnapshot?.breakdown ?? venture?.breakdown;

  const rescore = useMutation({
    mutationFn: () => ds.rescoreVenture(ventureId),
    onSuccess: () => {
      toast("Rescore queued — a new snapshot lands when the run completes.");
      queryClient.invalidateQueries({ queryKey: ["scores", ventureId] });
      queryClient.invalidateQueries({ queryKey: ["ranking"] });
    },
    onError: (error) =>
      toast.error(`Rescore failed${error instanceof Error ? ` — ${error.message}` : ""}.`),
  });

  const founder = teamQuery.data?.find((m) => m.is_founder_guess) ?? teamQuery.data?.[0];
  const needsMore = venture?.quality_tier === "needs_more_data";

  // Mock-store subscription: "in process" state renders live after the click.
  useSyncExternalStore(subscribe, getVersion);
  const inProcess = getDB().investmentProcess.includes(ventureId);

  const startInvestment = () => {
    if (!venture || inProcess) return;
    mutate((db) => {
      if (!db.investmentProcess.includes(venture.venture_id)) {
        db.investmentProcess.push(venture.venture_id);
      }
    });
    toast(`Investment process started for ${venture.name}.`);
  };

  if (rankingLoading) {
    return (
      <div className="py-gutter-lg">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-3 h-10 w-72" />
        <Skeleton className="mt-3 h-4 w-96 max-w-full" />
        <div className="mt-6 flex gap-2">
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
        <div className="mt-10 space-y-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
        {coldStart && (
          <p className="mt-6 font-mono text-mono-data text-quiet">{COLD_START_HINT}</p>
        )}
      </div>
    );
  }

  if (!venture) {
    return (
      <div className="max-w-measure-narrow py-gutter-lg">
        <p className="mono-label mb-2">Not found</p>
        <p className="text-body text-quiet">This venture is not in the ranked pool.</p>
        <Button asChild variant="outline" size="sm" className="mt-4">
          <Link to={`/t/${thesisId}/ranking`}>Back to ranking</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="py-gutter-lg">
      <Link
        to={`/t/${thesisId}/ranking`}
        className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet transition-colors duration-120 ease-swift hover:text-ink"
      >
        ← Ranking
      </Link>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-x-8 gap-y-6">
        <div className="min-w-0">
          <p className="mono-label mb-2">Venture memo</p>
          <h1 className="font-display text-h1">{venture.name}</h1>
          <p className="mt-2 max-w-measure text-body text-quiet">{venture.one_liner}</p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <StatusChip status={venture.status} />
            <QualityChip tier={venture.quality_tier} />
            <FundingBadge signal={venture.funding_signal} dense={false} />
            {inProcess && (
              <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                in process
              </span>
            )}
          </div>
        </div>
        <div className="text-right">
          <p className="mono-label">Final score</p>
          <p className="mt-1 font-mono text-[3.25rem] leading-none tabular text-ink">
            {formatScore(displayFinal)}
          </p>
          <p className="mt-2 font-mono text-mono-data tabular text-quiet">
            confidence {formatPercent(displayConfidence)}
          </p>
        </div>
      </div>

      {hasHistory && weights && (
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-y border-line py-3">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="mono-label">Re-scored after interview</span>
            <span className="font-mono text-mono-data tabular text-ink">
              {formatScore(snapshotFinals[1])} → {formatScore(snapshotFinals[0])}
            </span>
            <span className="font-mono text-mono-data tabular text-quiet">
              confidence {formatPercent(snapshots[1].confidence)} →{" "}
              {formatPercent(snapshots[0].confidence)}
            </span>
          </div>
          <div
            data-demo-id="memo-version-toggle"
            className="inline-flex rounded-ctrl border border-line-strong p-0.5"
          >
            {(
              [
                [0, "current"],
                [1, "pre-interview"],
              ] as const
            ).map(([idx, label]) => (
              <button
                key={idx}
                type="button"
                onClick={() => setVersionIndex(idx)}
                className={cn(
                  "rounded-[3px] px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.06em] transition-colors duration-120 ease-swift",
                  versionIndex === idx ? "bg-ink text-paper" : "text-quiet hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-10 grid gap-x-gutter-lg gap-y-gutter lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0">
          <section>
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-h2">Category breakdown</h2>
              {versionIndex === 1 && (
                <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                  viewing pre-interview snapshot
                </span>
              )}
            </div>
            {displayScores ? (
              <CategoryBreakdown
                scores={displayScores}
                breakdown={displayBreakdown}
                className="mt-4"
              />
            ) : (
              <div className="mt-4 space-y-2">
                {Array.from({ length: 9 }, (_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            )}
          </section>

          <section className="mt-14">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <h2 className="font-display text-h2">Memo</h2>
              {memoQuery.data && (
                <span className="font-mono text-[11px] text-quiet">
                  {memoQuery.data.model_version} ·{" "}
                  {memoQuery.data.generated_at.slice(0, 10)}
                </span>
              )}
            </div>
            {memoQuery.isLoading && (
              <div className="mt-4 space-y-6">
                {Array.from({ length: 4 }, (_, i) => (
                  <div key={i}>
                    <Skeleton className="h-3 w-40" />
                    <Skeleton className="mt-2 h-4 w-full max-w-measure" />
                    <Skeleton className="mt-1.5 h-4 w-4/5 max-w-measure" />
                  </div>
                ))}
              </div>
            )}
            {memoQuery.isError && (
              <div className="mt-4 max-w-measure-narrow">
                <p className="mono-label mb-2">No memo yet</p>
                <p className="text-body text-quiet">
                  This venture hasn&rsquo;t been deep-dived.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={() => rescore.mutate()}
                  disabled={rescore.isPending}
                >
                  Queue a deep dive
                </Button>
              </div>
            )}
            {memoQuery.data && (
              <div className="mt-4 space-y-8">
                {MEMO_SECTION_KEYS.map((key) => (
                  <MemoSectionView
                    key={key}
                    sectionKey={key}
                    section={memoQuery.data.sections[key]}
                  />
                ))}
              </div>
            )}
          </section>

          <InterviewThread ventureId={ventureId} />
        </div>

        <aside className="space-y-10">
          <div className="flex flex-col items-end gap-2">
            <Button
              data-demo-id="btn-send-outreach"
              onClick={() => setComposeOpen(true)}
              disabled={needsMore}
            >
              Schedule AI interview
            </Button>
            <Button
              variant="ink"
              data-demo-id="btn-start-investment"
              onClick={startInvestment}
              disabled={needsMore || inProcess}
            >
              {inProcess ? "In investment process" : "Start investment process"}
            </Button>
            {needsMore && (
              <p className="max-w-[16rem] text-right font-mono text-[11px] leading-relaxed text-quiet">
                Not enough signal to choose. Close the gaps below, then rescore.
              </p>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => rescore.mutate()}
              disabled={rescore.isPending}
            >
              {rescore.isPending ? "Queuing…" : "Rescore"}
            </Button>
          </div>

          <MissingDataPanel gaps={gapsQuery.data ?? []} memo={memoQuery.data ?? null} />

          <div>
            <p className="mono-label">Team</p>
            {teamQuery.isLoading ? (
              <div className="mt-2 space-y-2">
                {Array.from({ length: 3 }, (_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : (
              <TeamSection members={teamQuery.data ?? []} />
            )}
          </div>
        </aside>
      </div>

      <ComposeDialog
        venture={venture}
        founder={founder}
        open={composeOpen}
        onOpenChange={setComposeOpen}
      />
    </div>
  );
}
