import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { dataSource } from "@/lib/data";

/**
 * TODO(Track B): full memo detail — 9 category bars, evidence citation cards,
 * missing-data list, team, outreach/rescore actions, before/after toggle.
 */
export default function VenturePage() {
  const { ventureId = "", thesisId = "" } = useParams();
  const ds = dataSource();
  const { data: ranking } = useQuery({
    queryKey: ["ranking", thesisId],
    queryFn: () => ds.getRanking(thesisId),
  });
  const venture = ranking?.find((v) => v.venture_id === ventureId);

  return (
    <div className="py-gutter-lg">
      <p className="mono-label mb-2">Venture</p>
      <h1 className="font-display text-h1">{venture?.name ?? "…"}</h1>
      <p className="mt-2 text-body text-quiet">{venture?.one_liner}</p>
    </div>
  );
}
