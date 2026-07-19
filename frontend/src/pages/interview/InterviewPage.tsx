/**
 * The founder flow — a single route (/interview/:token) that walks a step
 * machine derived from the server's stage plus minimal local progression:
 *
 *   invalid | expired          → InvalidStep
 *   pending_consent            → HeroConsentStep  (decline handled inside)
 *   consented (no asks yet)    → CandidacyStep    (skip → local jump to chat)
 *   consented (asks saved)     → ChatStep
 *   in_progress                → ChatStep
 *   completed                  → DoneStep
 *
 * Server truth carries the flow forward: consent and the structured asks each
 * invalidate ["interview", token], and the refetched stage/structured fields
 * advance the step. The only local bits are the decline state (inside the
 * consent step) and the candidacy skip.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { dataSource } from "@/lib/data";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { HeroConsentStep } from "@/pages/interview/steps/HeroConsentStep";
import { CandidacyStep } from "@/pages/interview/steps/CandidacyStep";
import { ChatStep } from "@/pages/interview/steps/ChatStep";
import { DoneStep } from "@/pages/interview/steps/DoneStep";
import { InvalidStep } from "@/pages/interview/steps/InvalidStep";

export default function InterviewPage() {
  const { token = "" } = useParams();
  const ds = dataSource();
  const queryClient = useQueryClient();
  const [skippedCandidacy, setSkippedCandidacy] = useState(false);

  const {
    data: session,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["interview", token],
    queryFn: () => ds.getInterviewSession(token),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["interview", token] });
  };

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper px-gutter">
        <div className="w-full max-w-[560px] space-y-4">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-40 w-full rounded-warm" />
        </div>
      </div>
    );
  }

  if (isError || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper px-gutter">
        <div className="w-full max-w-[480px]">
          <p className="mono-label">Private invitation</p>
          <h1 className="mt-4 font-display text-h2 text-ink">
            We couldn't open your invitation.
          </h1>
          <p className="mt-3 text-body text-quiet">
            The connection hiccuped — nothing is lost.
          </p>
          <Button variant="outline" className="mt-6" onClick={() => void refetch()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  switch (session.stage) {
    case "invalid":
      return <InvalidStep variant="invalid" contactEmail={session.fund_contact_email} />;
    case "expired":
      return <InvalidStep variant="expired" contactEmail={session.fund_contact_email} />;
    case "pending_consent":
      return <HeroConsentStep session={session} refresh={refresh} />;
    case "consented":
      if (session.structured || skippedCandidacy) {
        return <ChatStep session={session} refresh={refresh} />;
      }
      return (
        <CandidacyStep
          session={session}
          refresh={refresh}
          onSkip={() => setSkippedCandidacy(true)}
        />
      );
    case "in_progress":
      return <ChatStep session={session} refresh={refresh} />;
    case "completed":
      return <DoneStep session={session} />;
  }
}
