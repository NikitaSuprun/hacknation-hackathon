-- 50_views.sql  (run with ${catalog} = dealflow | dealflow_dev)
-- The UI/proxy contract: the app reads these views, never base tables.
USE CATALOG ${catalog};

CREATE OR REPLACE VIEW gold.v_ranked_ventures AS
SELECT v.venture_id, v.name, v.one_liner, v.status, v.quality_tier, v.market_tags,
       s.final_score, s.confidence, s.ideal_match,
       s.s_individual_experience, s.s_schools, s.s_network_ties, s.s_prior_collaboration,
       s.s_problem_realness, s.s_product_defensibility, s.s_market, s.s_traction,
       s.breakdown, s.scored_at
FROM gold.venture v
LEFT JOIN gold.venture_score s ON s.venture_id = v.venture_id AND s.is_latest;

CREATE OR REPLACE VIEW gold.v_venture_team AS
SELECT vm.venture_id, p.person_id, p.full_name, p.headline, p.github_login, p.orcid,
       p.linkedin_url, p.affiliation, p.avatar_url, vm.role_hint, vm.is_founder_guess, vm.weight, vm.evidence
FROM gold.venture_member vm JOIN silver.person p USING (person_id)
WHERE p.status = 'active';

CREATE OR REPLACE VIEW gold.v_person_network AS      -- the sorted "people_connected" array the UI wants
SELECT person_id,
       sort_array(collect_list(struct(weight, other_person_id, connection_type)), false) AS people_connected
FROM (
  SELECT person_a_id AS person_id, person_b_id AS other_person_id, connection_type, weight FROM silver.person_connection
  UNION ALL
  SELECT person_b_id, person_a_id, connection_type, weight FROM silver.person_connection
) GROUP BY person_id;

CREATE OR REPLACE VIEW gold.v_person_similarity AS   -- SQL dot product (unit vectors) vs the active ideal
SELECT pf.person_id, ic.profile_id,
       aggregate(zip_with(pf.profile_embedding, ic.embedding, (x,y) -> CAST(x*y AS DOUBLE)), 0D, (a,b)->a+b) AS domain_fit
FROM gold.person_features pf CROSS JOIN gold.ideal_candidate ic
WHERE ic.is_active AND pf.profile_embedding IS NOT NULL;

-- One row per (active person, fact): every signal reachable through active links.
-- Column contract (see docs/contract.md): person_id, signal_type, artifact_id,
-- artifact_name, role, magnitude, confidence, source_url, occurred_at.
CREATE OR REPLACE VIEW gold.v_person_signals AS
SELECT p.person_id,
       'contribution'                    AS signal_type,
       c.project_id                      AS artifact_id,
       pr.full_name                      AS artifact_name,
       CAST(NULL AS STRING)              AS role,
       c.commit_count                    AS magnitude,
       c.confidence                      AS confidence,
       c.source_url                      AS source_url,
       c.last_commit_at                  AS occurred_at
FROM silver.person p
JOIN silver.person_source_link l ON l.person_id = p.person_id AND l.status = 'active'
JOIN silver.contribution c       ON c.source_record_id = l.source_record_id
JOIN silver.project pr           ON pr.project_id = c.project_id
WHERE p.status = 'active'
UNION ALL
SELECT p.person_id,
       'authorship'                      AS signal_type,
       a.publication_id                  AS artifact_id,
       pub.title                         AS artifact_name,
       CAST(a.author_position AS STRING) AS role,
       pub.citation_count                AS magnitude,
       a.confidence                      AS confidence,
       a.source_url                      AS source_url,
       CAST(pub.published_at AS TIMESTAMP) AS occurred_at
FROM silver.person p
JOIN silver.person_source_link l ON l.person_id = p.person_id AND l.status = 'active'
JOIN silver.authorship a         ON a.source_record_id = l.source_record_id
JOIN silver.publication pub      ON pub.publication_id = a.publication_id
WHERE p.status = 'active'
UNION ALL
SELECT p.person_id,
       'officer'                         AS signal_type,
       o.company_id                      AS artifact_id,
       co.name                           AS artifact_name,
       o.role_norm                       AS role,
       CAST(NULL AS INT)                 AS magnitude,
       o.confidence                      AS confidence,
       o.source_url                      AS source_url,
       CAST(o.registered_at AS TIMESTAMP) AS occurred_at
FROM silver.person p
JOIN silver.person_source_link l ON l.person_id = p.person_id AND l.status = 'active'
JOIN silver.officer o            ON o.source_record_id = l.source_record_id
JOIN silver.company co           ON co.company_id = o.company_id
WHERE p.status = 'active';
