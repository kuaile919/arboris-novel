# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI server. Main modules are in `backend/app/`: `api/routers`, `services`, `repositories`, `models`, `schemas`, `core`, and `db`.
- `backend/prompts/`: Markdown prompt templates used by AI workflows.
- `frontend/`: Vue 3 + Vite client (`src/views`, `src/components`, `src/stores`, `src/api`).
- `deploy/`: deployment assets (`docker-compose.yml`, `Dockerfile`, `nginx.conf`).
- `docs/` and root reports: architecture, audit, and deployment references.

## Build, Test, and Development Commands
- Full stack (Linux/macOS): `./start.sh`
- Full stack (Windows): `start.bat`.
- Backend local: `cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --reload-dir app --reload-dir prompts --port 8000`
- Frontend local: `cd frontend && npm install && npm run dev`
- Frontend quality gates: `npm run type-check`, `npm run format`, `npm run build`
- Docker deploy build: `docker compose -f deploy/docker-compose.yml up -d --build`

## Coding Style & Naming Conventions
- Python: follow PEP 8, 4-space indentation, `snake_case` for functions/files, `PascalCase` for classes, and prefer type hints.
- Vue/TS: follow `frontend/.prettierrc.json` (`semi: false`, `singleQuote: true`, `printWidth: 100`).
- Keep existing naming patterns: components in `PascalCase.vue` (for example `WDWorkspace.vue`), composables as `useX.ts`.
- Keep boundaries clean: router -> service -> repository/model.

## Testing Guidelines
- No enforced coverage threshold exists yet; include validation notes in each PR.
- Existing smoke/integration scripts: `python backend/test_anthropic.py`, `python test-local-embedding.py`.
- Minimum frontend check before PR: `npm run type-check`.
- New backend tests should follow `test_*.py`.

## Commit & Pull Request Guidelines
- Prefer Conventional Commit prefixes used in history: `feat:`, `fix:`, `docs:`.
- Keep commits scoped; exclude local noise (`.idea/`, `*.log`, `.env*`, `*.sqlite`, `node_modules/`).
- PRs should include: summary, impacted paths, env/config changes, commands run, and screenshots/GIFs for UI updates.
- Link related issues and flag breaking changes clearly.

## Security & Configuration Tips
- Bootstrap config from `deploy/.env.example` or `backend/env.example`.
- Never commit API keys or secrets.
- Treat `backend/storage/logs/` and local DB files as local artifacts.
