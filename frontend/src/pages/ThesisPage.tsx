import { useQuery } from "@tanstack/react-query";
import { dataSource } from "@/lib/data";

/** TODO(Track B): full thesis form (sectors, geographies, check size, filters). */
export default function ThesisPage() {
  const ds = dataSource();
  const { data: theses } = useQuery({ queryKey: ["theses"], queryFn: () => ds.listTheses() });
  const thesis = theses?.[0];

  return (
    <div className="py-gutter-lg">
      <p className="mono-label mb-2">Thesis</p>
      <h1 className="font-display text-h1">{thesis?.name ?? "…"}</h1>
      <p className="mt-4 max-w-measure text-body text-quiet">{thesis?.notes}</p>
    </div>
  );
}
