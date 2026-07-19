import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/** Outlined mono pills, the status-chip vocabulary. State dots are added by StatusChip. */
const badgeVariants = cva(
  "inline-flex w-fit items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 font-mono text-mono-label uppercase transition-colors duration-180 ease-swift",
  {
    variants: {
      variant: {
        outline: "border-line-strong text-ink",
        quiet: "border-line text-quiet",
        accent: "border-electric text-electric",
        solid: "border-electric bg-electric text-paper",
        danger: "border-danger text-danger",
        dashed: "border-dashed border-line-strong text-quiet",
      },
    },
    defaultVariants: {
      variant: "outline",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
