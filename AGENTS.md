## Conversational Style

- Keep answers short and concise
- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text (e.g., "Thanks @user" not "Thanks so much @user!")
- Technical prose only, be direct
- When the user asks a question, answer it first before making edits or running implementation commands.
- When responding to user feedback or an analysis, explicitly say whether you agree or disagree before saying what you
  changed.

## Code Quality

- Read files in full before wide-ranging changes, before editing files you have not fully inspected, and when asked to
  investigate or audit. Do not rely on search snippets for broad changes.
- Inline single-line helpers that have only one call site.
- Prefer simple stacked guard clauses over compound conditions: use separate early returns instead of
  `if condition_a or condition_b`.
- Always ask before removing functionality or code that appears intentional.
- Do not preserve backward compatibility unless the user asks for it.
- Never run `makemigrations` or `migrate` unless explicitly asked.
- Do not add or generate tests unless this was agreed with the user beforehand.
- After changes, run `make format` and then `make lint`.

## Git Conventions

- Format commit subjects as `<scope>: <imperative action>`, following the Linux kernel style (for example,
  `users: normalize email before saving`).

## Code Conventions

- Write the project name `learnd` in lowercase at all times.
- Add type hints to function and method signatures.
- In modules, place public functions near the top and private helpers below them.
- In usecase modules, place supporting types immediately above the first public function that uses them, grouping them
  with their associated operation.
- Models should use `TextChoices` for enums.
- Assign Django model fields directly. If `ty` reports `invalid-assignment`, add
  `# ty: ignore[invalid-assignment]` to the assignment; do not use `setattr()` to evade the warning.
- Access model querysets through `objects`; do not use `_default_manager`.
- Internationalize user-facing labels and strings in Python and templates.
- Use absolute imports from `src/`, except within `usecases` packages, where local relative imports are preferred.
