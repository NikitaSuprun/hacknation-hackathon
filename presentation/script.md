# 60-second script

147 words. At a normal pitch pace (~150 wpm) that lands just under a minute.
Point at the slide only twice: at the sources column, and at the note beside
the Scoring box.

---

**0:00 — what this is** *(5s)*

> VCs meet founders after they raise. We find them before they apply.

**0:05 — sources** *(13s)* — gesture at the left column

> We scrape four public sources: GitHub's newest repos and who actually
> commits to them, arXiv and OpenAlex for papers, and Hack Nation itself —
> our own connector, straight off their API: teams, pitches, CVs. Swiss
> company registry is next.

**0:18 — identity** *(12s)*

> One builder shows up as a GitHub login, a paper author, and a hackathon
> profile. We collapse those into one person_id — deterministic rules first,
> then Splink, then Claude on the pairs that are genuinely ambiguous. Every
> merge is reversible.

**0:30 — how we score** *(22s)* — this is the part that wins it; slow down

> Nine scores per team, all computed inside Databricks, where Claude judges
> things SQL can't — whether a commit history is any good, whether a product
> is actually defensible. We use embeddings for exactly one thing: does this
> person work on that problem? Because an embedding cannot know that MIT
> outranks KTH, or that 8,200 stars dwarf 82. Prestige and scale live in a
> calibrated feature layer instead.

**0:52 — close** *(8s)*

> Move a weight slider and the ranking re-sorts instantly. Every line of
> every memo cites its source.

---

## If you get 90 seconds

Add after identity: *"Facts attach to the per-source identity, never to the
person — so a bad merge is undone without touching a single row of data."*

Add before the close: *"Shortlist someone and it sends a consent-based email;
they answer an AI interview that fills exactly the gaps we flagged, and the
score and memo rewrite themselves."*

## Questions you should expect

- **"Is this GDPR-legal?"** Public sources only, provenance on every fact,
  and erasure enforced inside the write path — a re-scrape cannot resurrect
  someone who asked to be removed.
- **"What did it cost?"** Under $150 for the whole demo. Databricks Free
  Edition, so the LLM calls are essentially the only spend.
- **"Why not just embed the profile?"** That's the note beside Scoring — it's
  the question we designed around, not one we avoided.
