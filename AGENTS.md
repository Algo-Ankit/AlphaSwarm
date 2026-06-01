# System Instructions for Codex & Codex

1. **MANDATORY CONTEXT**: Before you generate any code or execute any commands, you MUST read the `ARCHITECTURE.md` file in this directory to understand the SaaS architecture.
2. **STATE TRACKING**: When you complete a task, you MUST automatically update the `CURRENT STATE & ROADMAP` checklist inside `ARCHITECTURE.md`.
3. **API CONTRACTS**: Do not ask the user for backend details. Read the `openapi.json` file.
4. **DATABASE SCHEMA**: Do not ask the user for table structures. Read the `schema.sql` file.
5. **VERSION CONTROL**: Whenever you finish building a functional feature or phase, you MUST automatically run `git add .` and `git commit -m "..."` with a concise message describing the update. Do not ask for permission to commit.
