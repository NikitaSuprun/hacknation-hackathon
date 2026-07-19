# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""WS-G's two additive deterministic ER rules: D7 (LinkedIn) and D8 (repo team).

Stage 2 of entity resolution (docs/plan/reference/entity-resolution.md) is a
deterministic SQL pass owned by WS-D; the Hack Nation source plugs in by
contributing two more rules, with zero engine changes. Both sit at or above the
0.90 auto-link floor, so every candidate row auto-links:

- D7 (0.97): a hacknation PSR shares its linkedin_url with a PSR from another
  source; attach it to the golden person that twin already resolves to.
- D8 (0.90): a Hack Nation project pitches a githubUrl; a core contributor of
  that repo whose name_norm agrees with a declared team member at Jaro-Winkler
  >= 0.9 identifies the member's golden person. "Core contributor" is the team
  gate frozen in scoring-and-memo.md: share >= 0.10, or >= 0.05 with >= 10
  commits.

Each SELECT yields candidate link rows (person_id, source_record_id,
match_method, match_confidence, then evidence-friendly columns) over the frozen
tables, unqualified per the session-catalog convention. They document the exact
rule semantics; the engine owns execution and must:

- register a `jaro_winkler` SQL UDF before D8 - Databricks SQL has no builtin;
  Splink (already the Stage-3 dependency) ships one;
- mint ids via tools.ids.link_id(person_id, source_record_id, match_method) and
  MERGE into silver.person_source_link, so re-runs are idempotent (add-only,
  never auto-retracting);
- fold the trailing projection columns into the link's evidence VARIANT
  (fixture links use {"rule": ..., ...});
- note D8 reads the declared team from bronze.hacknation_projects_raw
  payload:team via a VARIANT lateral explode, because silver has no hacknation
  membership table until the venture builder runs; the engine may materialize
  that hop differently as long as the semantics hold.

The match_method strings are frozen in entity-resolution.md and appear in
silver.person_source_link's method comment; the DDL carries no CHECK on
match_method, so adding them was purely additive.
"""

from typing import Final

MATCH_METHOD_D7: Final[str] = "det_linkedin"
CONFIDENCE_D7: Final[float] = 0.97

MATCH_METHOD_D8: Final[str] = "det_hn_repo"
CONFIDENCE_D8: Final[float] = 0.90

D7_SQL: Final[str] = """\
-- D7: LinkedIn-URL equality between a Hack Nation PSR and a PSR of any other
-- source. Cross-source only: two hacknation accounts sharing a URL are a
-- same-source-collision review case, never an auto-link.
SELECT
  l.person_id,
  a.source_record_id,
  'det_linkedin' AS match_method,
  0.97 AS match_confidence,
  b.source_record_id AS matched_source_record_id,
  a.linkedin_url
FROM silver.person_source_record a
JOIN silver.person_source_record b       -- hop 1: same URL, different source
  ON b.linkedin_url = a.linkedin_url AND b.source <> 'hacknation'
JOIN silver.person_source_link l         -- hop 2: the twin's golden person
  ON l.source_record_id = b.source_record_id AND l.status = 'active'
WHERE a.source = 'hacknation'
  AND a.linkedin_url IS NOT NULL
  -- candidates only for not-yet-linked PSRs (the engine enforces this too)
  AND NOT EXISTS (SELECT 1 FROM silver.person_source_link existing
                  WHERE existing.source_record_id = a.source_record_id
                    AND existing.status = 'active')
"""

D8_SQL: Final[str] = """\
-- D8: Hack Nation project githubUrl -> GitHub repo -> core contributor whose
-- name agrees (Jaro-Winkler >= 0.9). The declared team exists only in the
-- bronze projects payload until the venture builder runs, so the team hop
-- reads the frozen bronze table directly via a VARIANT lateral explode.
WITH hn_team AS (
  SELECT
    hp.project_id AS hn_project_id,
    -- normalize the pitched URL to the owner/repo form of silver.project full_name
    lower(regexp_replace(regexp_replace(hp.payload:githubUrl::string,
          '^https?://(www[.])?github[.]com/', ''), '([.]git)?/?$', '')) AS repo_full_name,
    tm.value:userId::string AS user_id
  FROM bronze.hacknation_projects_raw hp,
       LATERAL variant_explode(hp.payload:team) AS tm
  WHERE hp.payload:githubUrl::string IS NOT NULL
)
SELECT
  l.person_id,
  a.source_record_id,
  'det_hn_repo' AS match_method,
  0.90 AS match_confidence,
  ctr.source_record_id AS matched_source_record_id,
  t.hn_project_id,
  t.repo_full_name,
  jaro_winkler(a.name_norm, b.name_norm) AS name_jw
FROM hn_team t
JOIN silver.project g                    -- hop 1: the scraped repo row
  ON g.source_platform = 'github' AND lower(g.full_name) = t.repo_full_name
JOIN silver.contribution ctr             -- hop 2: core contributors only
  ON ctr.project_id = g.project_id
 AND (ctr.contribution_share >= 0.10
      OR (ctr.contribution_share >= 0.05 AND ctr.commit_count >= 10))
JOIN silver.person_source_record b       -- hop 3: contributor github PSR (name_norm)
  ON b.source_record_id = ctr.source_record_id
JOIN silver.person_source_link l         -- hop 4: the contributor's golden person
  ON l.source_record_id = ctr.source_record_id AND l.status = 'active'
JOIN silver.person_source_record a       -- hop 5: team member PSR, source_key = userId
  ON a.source = 'hacknation' AND a.source_key = t.user_id
WHERE jaro_winkler(a.name_norm, b.name_norm) >= 0.9  -- engine-registered UDF
  AND NOT EXISTS (SELECT 1 FROM silver.person_source_link existing
                  WHERE existing.source_record_id = a.source_record_id
                    AND existing.status = 'active')
"""
