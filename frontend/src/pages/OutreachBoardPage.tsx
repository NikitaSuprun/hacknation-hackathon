import { useParams } from "react-router-dom";
import { OutreachBoard } from "@/components/outreach/OutreachBoard";

/** Kanban over the outreach state machine — advances via status changes only. */
export default function OutreachBoardPage() {
  const { thesisId = "" } = useParams();
  return (
    <div className="py-gutter-lg">
      <p className="mono-label mb-2">Outreach</p>
      <h1 className="font-display text-h1">Outreach board</h1>
      <OutreachBoard thesisId={thesisId} />
    </div>
  );
}
