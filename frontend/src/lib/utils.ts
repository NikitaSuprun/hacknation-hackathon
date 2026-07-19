import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * Our theme names both font sizes (text-mono-data) and colors (text-ink) with
 * the `text-` prefix, and tailwind-merge can't tell them apart on its own — it
 * would treat them as one conflicting group and silently drop whichever came
 * first, so `text-small text-paper` would lose its size or its color. Teaching
 * it both vocabularies keeps size and color independent.
 */
const FONT_SIZES = [
  "display-xl",
  "display",
  "h1",
  "h2",
  "h3",
  "h4",
  "body",
  "small",
  "mono-data",
  "mono-label",
];

const TEXT_COLORS = [
  "paper",
  "ink",
  "quiet",
  "line",
  "line-strong",
  "wash",
  "electric",
  "electric-hover",
  "electric-onink",
  "electric-wash",
  "danger",
];

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: FONT_SIZES }],
      "text-color": [{ text: TEXT_COLORS }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatScore(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toFixed(1);
}

export function formatPercent(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${Math.round(n * 100)}%`;
}
