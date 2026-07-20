# Final Delivery Report Template

Use this exact structure when the work is complete. Omit a section only if it is genuinely not applicable (e.g. no database changes), and say so rather than leaving it out silently.

## Completed Work
What was implemented, in a few sentences.

## Files Changed
The main files changed and why each was touched.

## Technical Decisions
The most important architectural or implementation decisions, with brief reasoning.

## Validation Performed
Every command or check actually run and its result. Never list a check that was not run.

## Security Review
Protections added or verified, and any remaining concerns (see `security-checklist.md`).

## Database Changes
Migrations, schema changes, indexes, data-migration requirements, and rollback considerations. "None" if none.

## Deployment Steps
Exact order, covering whichever apply: environment variables, dependency installation, build commands, migration commands, queue/worker restarts, cache clearing, static asset steps, service restarts.

## Rollback Plan
How to safely reverse the changes.

## Remaining Limitations
Anything that could not be completed and why (e.g. missing credentials, unavailable external service, pre-existing failing test).
