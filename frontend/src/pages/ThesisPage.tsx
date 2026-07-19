/**
 * The investor's first page — thesis intake as a four-stage flow over the
 * mock store's thesisIntake state machine:
 *
 *   empty -> extracting -> review -> confirmed
 *                             ^          |
 *                             +- update -+
 *
 * Live mode skips the intake theater: with a thesis stored it lands on the
 * confirmed card, and "Update thesis" opens a plain review (no red fields).
 */
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmedStage } from "@/components/thesis/ConfirmedStage";
import { EmptyStage } from "@/components/thesis/EmptyStage";
import { ExtractingStage } from "@/components/thesis/ExtractingStage";
import { ReviewStage } from "@/components/thesis/ReviewStage";
import { useThesisIntake } from "@/components/thesis/useThesisIntake";
import { useTheses } from "@/hooks/useInvestorData";
import { dataSource } from "@/lib/data";
import { mutate } from "@/mocks/state";

export default function ThesisPage() {
  const live = dataSource().mode === "live";
  const { data: theses, isLoading, isError, error, refetch } = useTheses();
  const thesis = theses?.[0];
  const intake = useThesisIntake();

  // True when review is a plain edit (reached from the confirmed card, or in
  // live mode) — everything prefills, nothing renders red.
  const [prefilled, setPrefilled] = useState(live);

  const startExtraction = useCallback((source: string) => {
    mutate((db) => {
      db.thesisIntake.stage = "extracting";
      db.thesisIntake.source = source;
    });
  }, []);

  const finishExtraction = useCallback(() => {
    setPrefilled(false);
    mutate((db) => {
      db.thesisIntake.stage = "review";
    });
  }, []);

  const openUpdate = useCallback(() => {
    setPrefilled(true);
    mutate((db) => {
      db.thesisIntake.stage = "review";
    });
  }, []);

  const confirm = useCallback(() => {
    mutate((db) => {
      db.thesisIntake.stage = "confirmed";
    });
  }, []);

  const startOver = useCallback(() => {
    mutate((db) => {
      db.thesisIntake.stage = "empty";
      db.thesisIntake.source = null;
    });
  }, []);

  if (isError) {
    return (
      <div className="max-w-measure-narrow py-gutter-lg">
        <p className="mono-label mb-2">Thesis unavailable</p>
        <p className="text-body text-quiet">
          The thesis query failed{error instanceof Error ? `: ${error.message}` : ""}.
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (isLoading || !thesis) {
    return (
      <div className="py-gutter-lg">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="mt-3 h-10 w-80 max-w-full" />
        <div className="mt-10 max-w-2xl space-y-6">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i}>
              <Skeleton className="h-3 w-32" />
              <Skeleton className="mt-2 h-10 w-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Live mode has no intake theater: confirmed unless the user opened review.
  const stage = live ? (intake.stage === "review" ? "review" : "confirmed") : intake.stage;

  return (
    <div className="py-gutter-lg">
      {stage === "empty" && <EmptyStage onSource={startExtraction} />}

      {stage === "extracting" && (
        <ExtractingStage
          source={intake.source ?? "your thesis"}
          missingFields={intake.missingFields}
          onDone={finishExtraction}
        />
      )}

      {stage === "review" && (
        <ReviewStage
          thesis={thesis}
          missingFields={intake.missingFields}
          prefilled={live || prefilled}
          onConfirmed={confirm}
          onCancel={confirm}
          onStartOver={!live && !prefilled ? startOver : null}
        />
      )}

      {stage === "confirmed" && (
        <ConfirmedStage
          thesis={thesis}
          source={live ? null : intake.source}
          onUpdate={openUpdate}
        />
      )}
    </div>
  );
}
