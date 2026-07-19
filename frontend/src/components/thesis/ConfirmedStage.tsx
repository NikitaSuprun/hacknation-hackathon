/**
 * Stage 4 of thesis intake — the confirmed thesis as a compact fact card.
 * All data reads from the stored thesis (works identically in live mode);
 * the intake source line renders only when the mock intake recorded one.
 */
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { fmtChf } from "@/components/thesis/thesisForm";
import type { Thesis } from "@/lib/domain/types";

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mono-label">{label}</p>
      <p className="mt-1 font-mono text-mono-data tabular text-ink">{value}</p>
    </div>
  );
}

export function ConfirmedStage({
  thesis,
  source,
  onUpdate,
}: {
  thesis: Thesis;
  source: string | null;
  onUpdate: () => void;
}) {
  return (
    <div className="mx-auto max-w-[640px] animate-fade-up">
      <Card className="p-6" data-demo-id="thesis-confirmed">
        <p className="mono-label mb-2">Investment thesis · confirmed</p>
        <h2 className="font-display text-h2">{thesis.name}</h2>

        <div className="mt-6 grid grid-cols-2 gap-x-8 gap-y-4">
          <Fact label="Sectors" value={thesis.sectors.join(", ")} />
          <Fact label="Geographies" value={thesis.geographies.join(", ")} />
          <Fact label="Stages" value={thesis.stages.join(", ")} />
          <Fact
            label="Check size · CHF"
            value={`${fmtChf(thesis.check_size_min_chf)} to ${fmtChf(thesis.check_size_max_chf)}`}
          />
          <Fact label="Team size" value={`${thesis.min_team} to ${thesis.max_team}`} />
          <Fact label="No prior VC" value={thesis.require_no_prior_vc ? "required" : "not required"} />
          <Fact
            label="Corporate OSS"
            value={thesis.exclude_corporate_oss ? "excluded" : "allowed"}
          />
        </div>

        <div className="hairline-t mt-6 pt-4 font-mono text-mono-label text-quiet">
          {source && <p>Read from {source}</p>}
          <p className={source ? "mt-0.5" : undefined}>
            updated {thesis.updated_at.slice(0, 10)}
          </p>
        </div>

        <div className="mt-6 flex items-center justify-between gap-4">
          <Button variant="outline" data-demo-id="btn-thesis-update" onClick={onUpdate}>
            Update thesis
          </Button>
          <Button asChild data-demo-id="btn-thesis-ranking">
            <Link to={`/t/${thesis.thesis_id}/ranking`}>Go to ranking</Link>
          </Button>
        </div>
      </Card>
    </div>
  );
}
