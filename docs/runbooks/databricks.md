# Databricks bootstrap runbook (Day 0)

Everything code-side is already built and verified offline; this is the manual
part that needs a browser, followed by one command sequence. Total time is
roughly 20 minutes plus signup email round-trips.

## 1. Create the workspace (browser)

1. Sign up for **Databricks Free Edition** (no card, non-commercial):
   <https://www.databricks.com/learn/free-edition>. Log in to the workspace.
2. Note the workspace URL, e.g. `https://dbc-xxxxxxxx.cloud.databricks.com`.
3. Free Edition is serverless-only with a **Serverless Starter Warehouse**
   already provisioned: *SQL Warehouses* → copy its **ID** (the hex segment in
   the connection details' HTTP path `/sql/1.0/warehouses/<id>`).

## 2. Service principal + OAuth secret (browser)

1. *Settings → Identity and access → Service principals* → **Add service
   principal** (name it `dealflow-app`).
2. Open it → *Secrets* → **Generate secret**. Copy the **client ID**
   (application ID) and the **secret** immediately.
3. Grants (an admin user): the service principal needs `CAN USE` on the
   warehouse (*SQL Warehouses → Permissions*). Catalog grants come after the
   DDLs exist: `GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY ON CATALOG
   dealflow_dev TO <application-id>` (repeat for `dealflow`), plus
   `READ VOLUME, WRITE VOLUME ON VOLUME dealflow_dev.ops.staging`.
   For the hackathon it is fine to run the apply/load steps below as your own
   user via a personal OAuth token instead - but the app path (WS-F proxy)
   must use the service principal.

## 3. Local credentials

```sh
cp .env.example .env   # then fill in:
# DATABRICKS_HOST=https://dbc-xxxxxxxx.cloud.databricks.com
# DATABRICKS_CLIENT_ID=<service-principal application id>
# DATABRICKS_CLIENT_SECRET=<generated secret>
# DATABRICKS_WAREHOUSE_ID=<warehouse id>
```

`.env` is git-ignored; never commit it.

## 4. Command sequence (in order)

```sh
uv run poe smoke              # SELECT 1; gte-large returns 1024 floats;
                              # which databricks-claude-* endpoints resolve
uv run poe ddl-apply          # all tables/views in dealflow_dev AND dealflow
uv run poe ddl-apply          # re-run must be a no-op (T1 acceptance)
uv run poe fixtures-load      # personas into dealflow_dev + view spot-check
uv run poe fixtures-load      # re-run must report 0 inserted / 0 updated (T5)
uv run poe verify-merge       # double-run 0/0, changed-hash update,
                              # suppressed-key block (T3 acceptance)
```

Afterwards record in `docs/contract.md` which Claude endpoints resolved and
whether the Anthropic-API fallback is active, then collect sign-off from the
workstream leads and declare the contract **frozen** (additive-only from
there).

## Known Free Edition caveats

- "Certain models not available" - that is exactly what `poe smoke` measures;
  unavailable Claude endpoints route to the Anthropic API (Message Batches
  for ER adjudication, per the entity-resolution reference).
- Fair-use daily shutoff: keep jobs modest, run backfills off-peak.
- If `CREATE CATALOG` is restricted on your workspace, create `dealflow` and
  `dealflow_dev` once in the UI (*Catalog → Create catalog*) and re-run
  `poe ddl-apply`; everything else is `IF NOT EXISTS`.

## Other Day-0 externals (from the roadmap)

- Email `zefix@bj.admin.ch` for free PublicREST credentials (long turnaround).
- OpenAlex API key (self-serve) · GitHub PAT per developer · Anthropic API key.
- Lovable project + Lovable Cloud; Resend account + outreach subdomain
  SPF/DKIM DNS (propagation is the long pole).
