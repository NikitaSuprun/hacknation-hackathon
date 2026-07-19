import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * A textarea that grows with its content instead of scrolling invisibly.
 * Height tracks scrollHeight up to maxRows, then scrolls visibly. The
 * measurement runs on every value change, so programmatic typing (the demo
 * autopilot) resizes it too.
 */
export interface AutoGrowTextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  maxRows?: number;
}

const AutoGrowTextarea = React.forwardRef<HTMLTextAreaElement, AutoGrowTextareaProps>(
  ({ className, maxRows = 5, value, ...props }, forwardedRef) => {
    const innerRef = React.useRef<HTMLTextAreaElement | null>(null);

    const setRefs = (node: HTMLTextAreaElement | null) => {
      innerRef.current = node;
      if (typeof forwardedRef === "function") forwardedRef(node);
      else if (forwardedRef) forwardedRef.current = node;
    };

    React.useLayoutEffect(() => {
      const el = innerRef.current;
      if (!el) return;
      const lineHeight = Number.parseFloat(getComputedStyle(el).lineHeight) || 24;
      const styles = getComputedStyle(el);
      const padding =
        Number.parseFloat(styles.paddingTop) + Number.parseFloat(styles.paddingBottom);
      const max = lineHeight * maxRows + padding;
      el.style.height = "auto";
      const next = Math.min(el.scrollHeight, max);
      el.style.height = `${next}px`;
      el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
    }, [value, maxRows]);

    return (
      <textarea
        ref={setRefs}
        rows={1}
        value={value}
        className={cn(
          "flex w-full resize-none rounded-ctrl border border-input bg-paper px-3 py-2 text-body text-ink transition-colors duration-120 ease-swift placeholder:text-quiet focus-visible:border-electric focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);
AutoGrowTextarea.displayName = "AutoGrowTextarea";

export { AutoGrowTextarea };
