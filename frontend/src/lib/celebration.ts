/**
 * Tiny event bus for the signature "candidacy sent" moment. The send mutation
 * fires it on success; CandidacySentOverlay (mounted once in AppShell)
 * listens and plays. The demo engine fires the same event — one code path.
 */

export interface CandidacySentEvent {
  ventureId: string;
  ventureName: string;
  founderName?: string;
  /** Viewport coordinates of the triggering button — the paint burst origin. */
  origin?: { x: number; y: number };
}

type Handler = (e: CandidacySentEvent) => void;

const handlers = new Set<Handler>();

export function onCelebrate(handler: Handler): () => void {
  handlers.add(handler);
  return () => handlers.delete(handler);
}

export function celebrate(event: CandidacySentEvent): void {
  for (const handler of handlers) handler(event);
}
