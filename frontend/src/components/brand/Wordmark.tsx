import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * The VH monogram — a chevron V interlocked with an H, separated by a paper
 * seam where they cross. Paths rather than text so the mark is identical
 * whether or not Clash Display has loaded.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("h-[18px] w-[18px] shrink-0", className)}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M1 4 L11 29 L21 4 L16.5 4 L11 21.5 L5.5 4 Z" fill="currentColor" />
      {/* Stroked in paper first: the seam that reads as the H passing in front. */}
      <path
        d="M15 4 H19 V14 H27 V4 H31 V29 H27 V18 H19 V29 H15 Z"
        stroke="var(--paper)"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path d="M15 4 H19 V14 H27 V4 H31 V29 H27 V18 H19 V29 H15 Z" fill="currentColor" />
    </svg>
  );
}

/**
 * The nav-size brand lockup: monogram + "VENTURE HUNT". Links home unless
 * `asLink` is false, which the landing page uses since it is already home.
 */
export function Wordmark({ className, asLink = true }: { className?: string; asLink?: boolean }) {
  const content = (
    <>
      <BrandMark />
      <span>Venture Hunt</span>
    </>
  );
  const classes = cn(
    "flex items-center gap-2 font-display text-[15px] font-semibold uppercase tracking-[0.08em] text-ink",
    className,
  );
  return asLink ? (
    <Link to="/" className={classes}>
      {content}
    </Link>
  ) : (
    <span className={classes}>{content}</span>
  );
}
