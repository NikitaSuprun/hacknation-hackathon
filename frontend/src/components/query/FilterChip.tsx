/**
 * The one chip vocabulary the query bar uses: outline when idle, electric
 * border + text when active. Keyboard-operable by construction (real button).
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export interface FilterChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active: boolean;
}

export const FilterChip = React.forwardRef<HTMLButtonElement, FilterChipProps>(
  ({ active, className, children, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-mono-label uppercase",
        "transition-[color,border-color,background-color,transform] duration-180 ease-swift active:scale-[0.98]",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-paper",
        active
          ? "border-electric text-electric"
          : "border-line-strong text-quiet hover:border-line-strong hover:text-ink",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  ),
);
FilterChip.displayName = "FilterChip";
