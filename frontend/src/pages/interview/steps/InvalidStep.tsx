/**
 * Invalid / expired invitation, quiet, no branding fireworks. One line of
 * fact, one line of help.
 */
export function InvalidStep({
  variant,
  contactEmail,
}: {
  variant: "invalid" | "expired";
  contactEmail: string;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-gutter">
      <div className="w-full max-w-[480px] animate-fade-up">
        <p className="mono-label">Private invitation</p>
        <h1 className="mt-4 font-display text-h2 text-ink">
          {variant === "expired"
            ? "This invitation has expired."
            : "This invitation link isn't valid."}
        </h1>
        <p className="mt-3 text-body text-quiet">
          If you were expecting to find something here, write to{" "}
          <span className="font-mono text-mono-data">{contactEmail}</span> and they'll sort it
          out.
        </p>
      </div>
    </div>
  );
}
