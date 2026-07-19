# Config & data

- Secrets in `.env` only (python-dotenv); `.env.example` is committed, `.env` never.
- Settings are frozen dataclasses built from explicit sources — no field defaults,
  no silent env-var fallbacks; missing config fails fast at startup.
- SQL lives in `*.sql` files run by name (`schemas/ddl/`), not in string literals.
- Data files shipped in-repo must be CC0/CC-BY/public-register licensed.
