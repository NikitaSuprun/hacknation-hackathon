/**
 * The right-hand provenance panel for the people graph. Person selection
 * shows everything we hold, joined across silver + gold + the live store,
 * with a source label on every fact. Venture selection shows a lighter
 * summary whose members click through to their person nodes.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { cn, formatScore } from "@/lib/utils";
import {
  arr,
  buildPersonDossier,
  fmtConfidence,
  fmtDate,
  getDB,
  num,
  str,
  type PersonDossier,
  type Raw,
  type SourceRecordEntry,
} from "./data";

export type GraphSelection = { kind: "person" | "venture"; id: string } | null;

interface DetailPanelProps {
  selection: GraphSelection;
  version: number;
  onSelectPerson: (personId: string) => void;
}

// --- shared bits ------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="mono-label mb-2 mt-6 first:mt-0">{children}</p>;
}

function SourceTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-quiet">
      {children}
    </span>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.04em] text-quiet">
        {label}
      </span>
      <span className="min-w-0 truncate text-right font-mono text-mono-data text-ink" title={value}>
        {value}
      </span>
    </div>
  );
}

function QualityBar({ value }: { value: number | null }) {
  if (value == null) return null;
  return (
    <div className="mt-3">
      <div className="flex items-baseline justify-between">
        <span className="mono-label">data quality</span>
        <span className="font-mono text-mono-data tabular text-ink">{value.toFixed(2)}</span>
      </div>
      <div className="mt-1 h-1 w-full bg-wash">
        <div className="h-1 bg-ink" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  );
}

// --- source records ---------------------------------------------------------

const RECORD_FIELDS: [string, string][] = [
  ["full_name", "name"],
  ["affiliation_raw", "affiliation"],
  ["location_raw", "location"],
  ["github_login", "github"],
  ["orcid", "orcid"],
  ["linkedin_url", "linkedin"],
  ["bio", "bio"],
];

function SourceRecordCard({ entry }: { entry: SourceRecordEntry }) {
  const { link, record } = entry;
  const retracted = str(link.status) === "retracted";
  return (
    <div className={cn("border border-line p-3", retracted && "border-dashed")}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-mono-data text-ink">
          {str(record?.source_key) ?? str(link.source_record_id)?.slice(0, 8) ?? "—"}
        </span>
        <span className="font-mono text-[11px] tabular text-quiet">
          {str(link.match_method) ?? "—"} · {fmtConfidence(link.match_confidence)}
        </span>
      </div>
      {record && (
        <div className="mt-1.5">
          {RECORD_FIELDS.map(([key, label]) => (
            <Fact key={key} label={label} value={str(record[key])} />
          ))}
          {arr(record.emails).length > 0 && (
            <Fact label="emails" value={arr(record.emails).map(String).join(", ")} />
          )}
          {arr(record.keywords).length > 0 && (
            <Fact label="keywords" value={arr(record.keywords).map(String).join(", ")} />
          )}
          <Fact label="bronze ref" value={str(record.bronze_ref)} />
        </div>
      )}
      {retracted && (
        <p className="mt-2 font-mono text-[11px] leading-4 text-danger">
          retracted · {str(link.retracted_reason) ?? "no reason recorded"}
        </p>
      )}
    </div>
  );
}

// --- person panel -----------------------------------------------------------

function PersonPanel({
  dossier,
  onSelectPerson,
}: {
  dossier: PersonDossier;
  onSelectPerson: (id: string) => void;
}) {
  const db = getDB();
  const thesisId = db.thesis.thesis_id;
  const p = dossier.person;
  const [avatarFailed, setAvatarFailed] = useState(false);
  const avatarUrl = str(p.avatar_url);
  const name = str(p.full_name) ?? "Unknown";
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const sourceCount = dossier.activeBySource.reduce((n, g) => n + g.entries.length, 0);

  return (
    <div>
      {/* identity */}
      <div className="flex items-start gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center bg-ink font-mono text-mono-data text-paper">
          {avatarUrl && !avatarFailed ? (
            <img
              src={avatarUrl}
              alt=""
              className="h-12 w-12 object-cover"
              onError={() => setAvatarFailed(true)}
            />
          ) : (
            initials
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-display text-h4 leading-tight text-ink">{name}</h3>
            <Badge variant={str(p.status) === "active" ? "outline" : "quiet"}>
              {str(p.status) ?? "unknown"}
            </Badge>
          </div>
          {str(p.headline) && <p className="mt-1 text-small text-quiet">{str(p.headline)}</p>}
        </div>
      </div>

      <div className="mt-3">
        <Fact label="person_id" value={String(p.person_id)} />
        <Fact label="affiliation" value={str(p.affiliation)} />
        <Fact
          label="location"
          value={[str(p.location), str(p.country_code)].filter(Boolean).join(" · ") || null}
        />
        <Fact label="github" value={str(p.github_login)} />
        <Fact label="orcid" value={str(p.orcid)} />
        <Fact label="email" value={str(p.primary_email)} />
        <Fact label="linkedin" value={str(p.linkedin_url)} />
        <Fact label="cv" value={str(p.cv_url)} />
      </div>
      <QualityBar value={dossier.quality} />

      {/* sources */}
      <SectionLabel>
        Sources · {sourceCount} active record{sourceCount === 1 ? "" : "s"}
      </SectionLabel>
      <div className="space-y-4">
        {dossier.activeBySource.map((group) => (
          <div key={group.source}>
            <SourceTag>{group.source}</SourceTag>
            <div className="mt-1 space-y-2">
              {group.entries.map((entry) => (
                <SourceRecordCard key={String(entry.link.link_id)} entry={entry} />
              ))}
            </div>
          </div>
        ))}
        {dossier.activeBySource.length === 0 && (
          <p className="text-small text-quiet">No active source links.</p>
        )}
        {dossier.retracted.length > 0 && (
          <div>
            <SourceTag>retracted</SourceTag>
            <div className="mt-1 space-y-2">
              {dossier.retracted.map((entry) => (
                <SourceRecordCard key={String(entry.link.link_id)} entry={entry} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* signals */}
      {(dossier.code.length > 0 || dossier.research.length > 0 || dossier.companies.length > 0) && (
        <SectionLabel>Signals</SectionLabel>
      )}
      <div className="space-y-2">
        {dossier.code.map(({ contribution, project }) => (
          <div key={String(contribution.contribution_id)} className="border border-line p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate font-mono text-mono-data text-ink">
                {str(project?.full_name) ?? "unknown repo"}
              </span>
              <SourceTag>github</SourceTag>
            </div>
            <div className="mt-1">
              <Fact label="commits" value={String(num(contribution.commit_count) ?? "—")} />
              <Fact
                label="share"
                value={
                  num(contribution.contribution_share) != null
                    ? `${Math.round((num(contribution.contribution_share) ?? 0) * 100)}%`
                    : null
                }
              />
              <Fact
                label="stars"
                value={num(project?.stars) != null ? String(num(project?.stars)) : null}
              />
              <Fact
                label="window"
                value={`${fmtDate(contribution.first_commit_at)} → ${fmtDate(contribution.last_commit_at)}`}
              />
              <Fact label="languages" value={arr(contribution.languages).map(String).join(", ") || null} />
            </div>
          </div>
        ))}
        {dossier.research.map(({ authorship, publication }) => (
          <div key={String(authorship.authorship_id)} className="border border-line p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate font-mono text-mono-data text-ink">
                {str(publication?.title) ?? "unknown publication"}
              </span>
              <SourceTag>{str(publication?.primary_source) ?? "openalex"}</SourceTag>
            </div>
            <div className="mt-1">
              <Fact label="venue" value={str(publication?.venue)} />
              <Fact
                label="position"
                value={
                  num(authorship.author_position) != null
                    ? `author ${num(authorship.author_position)}${authorship.is_last_author === true ? " · last" : ""}`
                    : null
                }
              />
              <Fact
                label="citations"
                value={num(publication?.citation_count) != null ? String(num(publication?.citation_count)) : null}
              />
              <Fact label="confidence" value={fmtConfidence(authorship.confidence)} />
            </div>
          </div>
        ))}
        {dossier.companies.map(({ officer, company }) => (
          <div key={String(officer.officer_id)} className="border border-line p-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate font-mono text-mono-data text-ink">
                {str(company?.name) ?? "unknown company"}
              </span>
              <SourceTag>zefix</SourceTag>
            </div>
            <div className="mt-1">
              <Fact label="role" value={str(officer.role_norm) ?? str(officer.role)} />
              <Fact label="registered" value={fmtDate(officer.registered_at)} />
              <Fact label="signing" value={str(officer.signing_authority)} />
              <Fact label="uid" value={str(company?.uid)} />
            </div>
          </div>
        ))}
      </div>

      {/* connections */}
      {dossier.connections.length > 0 && (
        <>
          <SectionLabel>Connections · {dossier.connections.length}</SectionLabel>
          <div className="space-y-1">
            {dossier.connections.map((c) => (
              <button
                key={c.otherId}
                type="button"
                onClick={() => onSelectPerson(c.otherId)}
                className="flex w-full items-baseline justify-between gap-2 border border-line px-3 py-1.5 text-left transition-colors duration-120 ease-swift hover:bg-wash"
              >
                <span className="truncate font-mono text-mono-data text-ink">{c.otherName}</span>
                <span className="shrink-0 font-mono text-[11px] tabular text-quiet">
                  {c.types.join(" + ")} · w {c.weight}
                </span>
              </button>
            ))}
          </div>
        </>
      )}

      {/* ventures */}
      {dossier.memberships.length > 0 && (
        <>
          <SectionLabel>Ventures</SectionLabel>
          <div className="space-y-2">
            {dossier.memberships.map((m) => (
              <Link
                key={m.ventureId}
                to={`/t/${thesisId}/venture/${m.ventureId}`}
                className="block border border-line p-3 transition-colors duration-120 ease-swift hover:bg-wash"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-mono text-mono-data text-ink">{m.name}</span>
                  <span className="shrink-0 font-mono text-mono-data tabular text-ink">
                    {formatScore(m.finalScore)}
                  </span>
                </div>
                <div className="mt-0.5 flex items-baseline justify-between gap-2">
                  <span className="font-mono text-[11px] text-quiet">
                    {m.roleHint ?? "member"}
                    {m.isFounderGuess ? " · founder guess" : ""}
                  </span>
                  <span className="font-mono text-[11px] uppercase text-quiet">{m.status}</span>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      {/* outreach + interview */}
      {(dossier.outreach.length > 0 || dossier.interviews.length > 0) && (
        <>
          <SectionLabel>Outreach & interview</SectionLabel>
          <div className="space-y-2">
            {dossier.outreach.map((o) => (
              <div key={o.outreach_id} className="border border-line p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-mono text-mono-data text-ink">{o.subject}</span>
                  <Badge variant="quiet">{o.status}</Badge>
                </div>
                <div className="mt-1">
                  <Fact label="to" value={o.to_email} />
                  <Fact label="sent" value={o.sent_at ? o.sent_at.slice(0, 10) : null} />
                  <Fact label="consent" value={o.consent_at ? o.consent_at.slice(0, 10) : null} />
                </div>
              </div>
            ))}
            {dossier.liveInterviewStage && (
              <div className="flex items-baseline justify-between border border-line px-3 py-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.04em] text-quiet">
                  interview stage
                </span>
                <span className="font-mono text-mono-data text-ink">
                  {dossier.liveInterviewStage.replace(/_/g, " ")}
                </span>
              </div>
            )}
            {dossier.interviews.map((i) => (
              <div key={String(i.interview_id)} className="border border-line p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-mono-data text-ink">gold.interview</span>
                  <SourceTag>fixture</SourceTag>
                </div>
                <div className="mt-1">
                  <Fact label="started" value={fmtDate(i.started_at)} />
                  <Fact label="completed" value={fmtDate(i.completed_at)} />
                  <Fact
                    label="consent"
                    value={i.consent_confirmed === true ? "confirmed" : "not confirmed"}
                  />
                  <Fact
                    label="turns"
                    value={arr(i.transcript).length > 0 ? String(arr(i.transcript).length) : null}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* features */}
      {dossier.features && Object.keys(dossier.features).length > 0 && (
        <>
          <SectionLabel>Features</SectionLabel>
          <div className="border border-line p-3">
            {Object.entries(dossier.features).map(([k, v]) => (
              <Fact key={k} label={k} value={String(v)} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// --- venture panel ----------------------------------------------------------

function VenturePanel({
  ventureId,
  onSelectPerson,
}: {
  ventureId: string;
  onSelectPerson: (id: string) => void;
}) {
  const db = getDB();
  const venture = db.ventures.find((v) => v.venture_id === ventureId);
  if (!venture) {
    return <p className="text-small text-quiet">Venture not found in the live store.</p>;
  }
  const members = db.team[ventureId] ?? [];
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-display text-h4 leading-tight text-ink">{venture.name}</h3>
        <Badge variant="quiet">{venture.status}</Badge>
      </div>
      <p className="mt-1 text-small text-quiet">{venture.one_liner}</p>
      <div className="mt-3 flex items-baseline justify-between">
        <span className="mono-label">final score</span>
        <span className="font-mono text-h3 tabular text-ink">{formatScore(venture.final_score)}</span>
      </div>
      <div className="mt-2">
        <Fact label="venture_id" value={venture.venture_id} />
        <Fact label="confidence" value={venture.confidence.toFixed(2)} />
        <Fact label="tags" value={venture.market_tags.join(", ") || null} />
      </div>

      <SectionLabel>Members · {members.length}</SectionLabel>
      <div className="space-y-1">
        {members.map((m) => (
          <button
            key={m.person_id}
            type="button"
            onClick={() => onSelectPerson(m.person_id)}
            className="flex w-full items-baseline justify-between gap-2 border border-line px-3 py-1.5 text-left transition-colors duration-120 ease-swift hover:bg-wash"
          >
            <span className="truncate font-mono text-mono-data text-ink">{m.full_name}</span>
            <span className="shrink-0 font-mono text-[11px] text-quiet">
              {m.role_hint ?? "member"}
            </span>
          </button>
        ))}
        {members.length === 0 && <p className="text-small text-quiet">No members on record.</p>}
      </div>

      <SectionLabel>Open</SectionLabel>
      <Link
        to={`/t/${db.thesis.thesis_id}/venture/${venture.venture_id}`}
        className="font-mono text-mono-data text-electric underline-offset-4 hover:underline"
      >
        /t/…/venture/{venture.venture_id.slice(0, 8)}
      </Link>
    </div>
  );
}

// --- panel shell ------------------------------------------------------------

export function DetailPanel({ selection, version, onSelectPerson }: DetailPanelProps) {
  const dossier = useMemo(
    () =>
      selection?.kind === "person" ? buildPersonDossier(selection.id, getDB()) : null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selection, version],
  );

  return (
    <aside
      data-demo-id="admin-detail"
      aria-live="polite"
      className="h-full w-[380px] shrink-0 overflow-y-auto border-l border-line bg-paper p-4"
    >
      {!selection && (
        <div className="flex h-full flex-col items-start justify-center">
          <p className="mono-label">Detail</p>
          <p className="mt-2 max-w-measure-narrow text-small text-quiet">
            Select a node. Persons show every record we hold and where it came from; ventures show
            score and members.
          </p>
        </div>
      )}
      {selection?.kind === "person" &&
        (dossier ? (
          <PersonPanel key={selection.id} dossier={dossier} onSelectPerson={onSelectPerson} />
        ) : (
          <p className="text-small text-quiet">Person not found.</p>
        ))}
      {selection?.kind === "venture" && (
        <VenturePanel ventureId={selection.id} onSelectPerson={onSelectPerson} />
      )}
    </aside>
  );
}
