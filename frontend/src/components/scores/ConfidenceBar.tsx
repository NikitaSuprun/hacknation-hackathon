import { cn } from "@/lib/utils";

/** 2px confidence bar beneath the score bar — quiet at 50%, width = confidence%. */
export function ConfidenceBar({
  value,
  className,
}: {
  /** 0–1. */
  value: number;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div className={cn("h-0.5 w-full overflow-hidden bg-wash", className)}>
      <div
        className="h-full w-full origin-left bg-quiet opacity-50 transition-transform duration-240 ease-swift"
        style={{ transform: `scaleX(${clamped})` }}
      />
    </div>
  );
}
