import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface TeamRow {
  name: string;
  role: string;
  github: string;
}

export const EMPTY_TEAM_ROW: TeamRow = { name: "", role: "", github: "" };

/**
 * Repeater for teammates on the intake card. Starts empty, "Add your team"
 * appends a row; the small × removes one. Every field is optional; rows left
 * fully blank are dropped by the caller before persisting.
 */
export function TeamRepeater({
  rows,
  onChange,
}: {
  rows: TeamRow[];
  onChange: (rows: TeamRow[]) => void;
}) {
  const setField = (index: number, field: keyof TeamRow, value: string) => {
    onChange(rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  return (
    <div data-demo-id="intake-team" className="space-y-2">
      {rows.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="grid flex-1 grid-cols-1 gap-2 sm:grid-cols-3">
            <Input
              aria-label={`Teammate ${i + 1} name`}
              placeholder="Name"
              value={row.name}
              onChange={(e) => setField(i, "name", e.target.value)}
            />
            <Input
              aria-label={`Teammate ${i + 1} role`}
              placeholder="Role"
              value={row.role}
              onChange={(e) => setField(i, "role", e.target.value)}
            />
            <Input
              aria-label={`Teammate ${i + 1} GitHub`}
              placeholder="https://github.com/…"
              value={row.github}
              onChange={(e) => setField(i, "github", e.target.value)}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-quiet hover:text-ink"
            aria-label={`Remove teammate ${i + 1}`}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            <X />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="-ml-2 text-quiet hover:text-ink"
        onClick={() => onChange([...rows, { ...EMPTY_TEAM_ROW }])}
      >
        <Plus />
        Add your team
      </Button>
    </div>
  );
}
