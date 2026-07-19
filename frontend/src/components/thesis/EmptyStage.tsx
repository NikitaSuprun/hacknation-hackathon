/**
 * Stage 1 of thesis intake — the investor's first screen. One card, three
 * ways in: drop a PDF, point at a page, or take the sample. Deliberately
 * spare; the page's single job is to start the extraction.
 */
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const MAX_PDF_BYTES = 20 * 1024 * 1024;

function looksLikeUrl(value: string): boolean {
  return /^https?:\/\/\S+\.\S{2,}/i.test(value.trim());
}

export function EmptyStage({ onSource }: { onSource: (source: string) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [link, setLink] = useState("");

  const takeFile = (picked: File | undefined) => {
    if (!picked) return;
    const isPdf =
      picked.type === "application/pdf" || picked.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setProblem("PDF only, please.");
      return;
    }
    if (picked.size > MAX_PDF_BYTES) {
      setProblem("That file is over 20 MB. A lighter export will do.");
      return;
    }
    setProblem(null);
    onSource(picked.name);
  };

  return (
    <div className="mx-auto max-w-[640px] animate-fade-up">
      <p className="mono-label mb-2">Investment thesis</p>
      <h1 className="font-display text-h1">Start with your thesis.</h1>
      <p className="mt-3 text-body text-quiet">
        Upload the committee's thesis as a PDF or point us at a page that describes it. We
        extract what we can and ask only for the rest.
      </p>

      <Card className="mt-8 p-6">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => {
            takeFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          data-demo-id="thesis-dropzone"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            takeFile(e.dataTransfer.files?.[0]);
          }}
          className={cn(
            "w-full rounded-none border border-dashed px-6 py-10 text-center transition-colors duration-120 ease-swift focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
            dragging
              ? "border-line-strong bg-wash"
              : "border-line hover:border-line-strong hover:bg-wash",
          )}
        >
          <p className="text-body text-ink">Drop your thesis here.</p>
          <p className="mt-1 font-mono text-mono-label text-quiet">PDF, max 20 MB</p>
        </button>
        {problem && <p className="mt-2 text-small text-danger">{problem}</p>}

        <div className="my-6 flex items-center gap-3">
          <Separator className="flex-1" />
          <span className="font-mono text-mono-label text-quiet">or</span>
          <Separator className="flex-1" />
        </div>

        <div className="flex gap-2">
          <Input
            data-demo-id="thesis-link-input"
            type="url"
            placeholder="https://yourfund.com/thesis"
            aria-label="Thesis page URL"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && looksLikeUrl(link)) onSource(link.trim());
            }}
            className="flex-1"
          />
          <Button
            variant="ink"
            data-demo-id="btn-thesis-read"
            disabled={!looksLikeUrl(link)}
            onClick={() => onSource(link.trim())}
          >
            Read this page
          </Button>
        </div>

        <div className="mt-5 text-center">
          <button
            type="button"
            data-demo-id="btn-thesis-sample"
            onClick={() => onSource("sample-thesis.pdf")}
            className="text-small text-quiet underline underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Use the sample thesis
          </button>
        </div>
      </Card>
    </div>
  );
}
