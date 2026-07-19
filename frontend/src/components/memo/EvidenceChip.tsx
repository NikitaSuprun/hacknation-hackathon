import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type { Evidence } from "@/lib/domain/types";
import { cn } from "@/lib/utils";

/**
 * "n sources" citation link → in-app citation dialog. Source URLs are
 * fictional and rendered as mono text — never as navigable links.
 */
export function EvidenceChip({
  evidence,
  className,
}: {
  evidence: Evidence[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const n = evidence.length;
  if (n === 0) return null;
  return (
    <>
      <button
        type="button"
        data-demo-id="evidence-chip"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
        className={cn(
          "font-mono text-[11px] text-electric underline-offset-2 transition-colors duration-120 ease-swift hover:underline",
          className,
        )}
      >
        {n} source{n === 1 ? "" : "s"}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Citations</DialogTitle>
            <DialogDescription>
              Every claim carries its source. URLs are recorded, not followed.
            </DialogDescription>
          </DialogHeader>
          <ul className="space-y-4">
            {evidence.map((item, i) => (
              <li key={i} className="hairline-t pt-3 first:border-t-0 first:pt-0">
                <p className="text-small font-medium text-ink">{item.claim}</p>
                {item.snippet && (
                  <p className="mt-1 text-small text-quiet">&ldquo;{item.snippet}&rdquo;</p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {item.source_type && <Badge variant="quiet">{item.source_type}</Badge>}
                  <span className="break-all font-mono text-[11px] text-quiet">
                    {item.source_url}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
