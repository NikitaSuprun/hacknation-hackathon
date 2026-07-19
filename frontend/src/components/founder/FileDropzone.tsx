/**
 * Founder-side PDF dropzone (CV / pitch). Drop or click to pick a file;
 * the upload runs through the data seam while a transform-only progress bar
 * sweeps for a set duration; then the stored file row with a delete action.
 * Ink-only, the page's single accent belongs to the primary CTA.
 */
import { useEffect, useRef, useState } from "react";
import { FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UploadedFileRef } from "@/lib/domain/types";

interface FileDropzoneProps {
  demoId: string;
  /** Main line inside the empty drop area. */
  prompt: string;
  /** Optional quiet second line inside the empty drop area. */
  note?: string;
  maxBytes: number;
  /** How long the progress sweep takes (the upload awaits it too). */
  durationMs: number;
  file: UploadedFileRef | null;
  onUpload: (file: File) => Promise<UploadedFileRef>;
  onDone: (ref: UploadedFileRef) => void;
  onClear: () => void;
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Transform-only progress sweep, scaleX from ~0 to 1 over durationMs. */
function ProgressBar({ durationMs }: { durationMs: number }) {
  const [go, setGo] = useState(false);
  useEffect(() => {
    // Double rAF so the initial scaleX(0.02) paints before the transition starts.
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setGo(true));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, []);
  return (
    <div className="h-[3px] w-full overflow-hidden rounded-full bg-wash">
      <div
        className="h-full w-full origin-left bg-ink transition-transform ease-travel"
        style={{
          transform: go ? "scaleX(1)" : "scaleX(0.02)",
          transitionDuration: `${durationMs}ms`,
        }}
      />
    </div>
  );
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export function FileDropzone({
  demoId,
  prompt,
  note,
  maxBytes,
  durationMs,
  file,
  onUpload,
  onDone,
  onClear,
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);
  const [dragging, setDragging] = useState(false);
  const [uploadingName, setUploadingName] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const takeFile = async (picked: File | undefined) => {
    if (!picked || uploadingName) return;
    setProblem(null);
    const isPdf =
      picked.type === "application/pdf" || picked.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setProblem("PDF only, please.");
      return;
    }
    if (picked.size > maxBytes) {
      setProblem(
        `That file is over ${Math.round(maxBytes / (1024 * 1024))} MB, a lighter export will do.`,
      );
      return;
    }
    setUploadingName(picked.name);
    try {
      const [ref] = await Promise.all([onUpload(picked), sleep(durationMs)]);
      if (!mountedRef.current) return;
      onDone(ref);
    } catch {
      if (!mountedRef.current) return;
      setProblem("That didn't go through, try again.");
    } finally {
      if (mountedRef.current) setUploadingName(null);
    }
  };

  if (file) {
    return (
      <div
        data-demo-id={demoId}
        className="flex items-center gap-3 rounded-warm border border-line bg-wash px-4 py-3"
      >
        <FileText className="h-4 w-4 shrink-0 text-quiet" strokeWidth={1.75} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-small font-medium text-ink">{file.name}</p>
          <p className="font-mono text-mono-label text-quiet">
            {formatSize(file.size_bytes)} · stored for this review only · delete anytime
          </p>
        </div>
        <button
          type="button"
          aria-label={`Delete ${file.name}`}
          onClick={() => {
            if (file.url?.startsWith("blob:")) URL.revokeObjectURL(file.url);
            onClear();
          }}
          className="rounded-ctrl p-1.5 text-quiet transition-colors duration-120 ease-swift hover:bg-wash hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-4 w-4" strokeWidth={1.75} />
        </button>
      </div>
    );
  }

  if (uploadingName) {
    return (
      <div
        data-demo-id={demoId}
        className="rounded-warm border border-line px-4 py-4"
        aria-live="polite"
      >
        <p className="mb-3 truncate text-small text-ink">{uploadingName}</p>
        <ProgressBar durationMs={durationMs} />
      </div>
    );
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          void takeFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        data-demo-id={demoId}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void takeFile(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "w-full rounded-warm border border-dashed px-4 py-6 text-center transition-colors duration-120 ease-swift focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
          dragging
            ? "border-line-strong bg-wash"
            : "border-line hover:border-line-strong hover:bg-wash",
        )}
      >
        <p className="text-small text-ink">{prompt}</p>
        {note ? <p className="mt-1 text-small text-quiet">{note}</p> : null}
      </button>
      {problem ? <p className="mt-2 text-small text-danger">{problem}</p> : null}
    </div>
  );
}
