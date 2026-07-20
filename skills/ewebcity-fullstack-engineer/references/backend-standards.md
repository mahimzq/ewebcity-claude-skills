# Backend Standards and Database Safety

Read only the framework section matching the repository. In all frameworks: validate every piece of external input on the server, keep request handlers thin, put complex business logic in services, and follow the conventions already present in the project even where they differ from these defaults.

## Laravel

- Form Requests for validation; policies or gates for authorisation.
- Eloquent relationships used correctly; eager-load to avoid N+1 queries.
- Transactions around multi-step writes.
- API Resources for response shaping.
- Queue long-running work rather than blocking requests.

## Node.js (Express / NestJS)

- Validate all inputs (existing validation library first — zod, joi, class-validator, whatever the project uses).
- Centralised error handling; every rejected promise handled — no unhandled rejections.
- No blocking operations on the event loop (sync fs, heavy CPU work in request path).
- Authentication and authorisation middleware on protected routes.
- Structured logging via the project's existing logger; rate limits where relevant.

## Django

- Forms or DRF serializers for validation; permission classes or decorators for authorisation.
- Transactions (`transaction.atomic`) for multi-step writes.
- `select_related` / `prefetch_related` to avoid inefficient query patterns.
- Thin views; CSRF protection intact; follow the existing app structure.

## Database and Migration Safety

Inspect existing schemas and the project's migration conventions before writing a migration.

- Prefer backward-compatible migrations; avoid destructive operations.
- Never rename or delete columns without a safe multi-step strategy (add new → backfill → switch reads → remove old in a later migration).
- Use nullable or transitional fields when introducing required data to existing rows.
- Add indexes for new query patterns.
- Include rollback support (down migrations or documented reversal).
- Explain any data-migration requirement explicitly in the delivery report.
- Never run destructive migrations or delete production data.
