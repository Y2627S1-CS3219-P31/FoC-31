# AGENTS.md — frontend

See the root `AGENTS.md` for monorepo-wide conventions.

## Service specifics

- React + TypeScript + Vite SPA. Dev server on port `5173`.
- Talks ONLY to the API Gateway (`VITE_API_BASE_URL`); never call backend
  services directly.
- Must be responsive across desktop + mobile (project M1). Keep layout logic
  in CSS (`src/index.css`) mobile-friendly.
- Server-side authorization is the source of truth; do not rely on client-side
  role checks for security (they are UX only).
- Add pages under `src/pages/`; register routes in `src/App.tsx`.

## AI usage

Add a file-header attribution comment to every AI-influenced file and log
prompts in `../ai/usage-log.md`.
