import { cn } from "@/lib/utils";

/** Shimmer skeleton on a wash base (transform-only sweep, see .skeleton in index.css). */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton rounded-none", className)} {...props} />;
}

export { Skeleton };
