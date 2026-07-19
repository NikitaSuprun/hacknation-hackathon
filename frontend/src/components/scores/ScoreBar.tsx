import { cn } from "@/lib/utils";

/**
 * 4px score bar: ink fill on a wash track, width = score%. Fill animates via
 * transform only; `flash` turns the fill electric for the rank-change beat.
 */
export function ScoreBar({
  value,
  flash = false,
  className,
}: {
  /** 0–100. */
  value: number;
  flash?: boolean;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-1 w-full overflow-hidden bg-wash", className)}>
      <div
        className={cn(
          "h-full w-full origin-left transition-[transform,background-color] duration-240 ease-swift",
          flash ? "bg-electric" : "bg-ink",
        )}
        style={{ transform: `scaleX(${clamped / 100})` }}
      />
    </div>
  );
}
