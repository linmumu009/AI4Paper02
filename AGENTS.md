# Repository Guidelines

## Project Structure & Module Organization

This multi-client AI4Papers app uses `Sever/` for the Python/FastAPI backend (the spelling is intentional): `api.py` composes the app, `routers/` defines endpoints, `services/` holds business logic, and `tests/` contains unit tests. `View/` is the Vue 3/Vite web UI; `mobile_new/` is the Vant mobile UI. Shared TypeScript contracts and transports live in `shared/`. `exe/` wraps `View/` with Tauri 2 for Windows. `ios/` is the SwiftUI client generated from `project.yml`. Treat `dist/`, `node_modules/`, `exe/src-tauri/target/`, runtime data, and release bundles as generated.

## Build, Test, and Development Commands

- `cd Sever; pip install -r requirements.txt` installs backend dependencies.
- `cd Sever; uvicorn api:app --reload --port 8000` starts the local API.
- `cd View; npm install; npm run dev` runs the main web client; `npm run build` type-checks and builds it.
- `cd mobile_new; npm install; npm run dev` serves the mobile client on port 5175; `npm run build` validates its production bundle.
- `cd exe; npm install; npm run build` creates the Tauri installer after configuring `.env.production`.
- `cd ios; xcodegen generate` regenerates the Xcode project from its canonical YAML.

## Coding Style & Naming Conventions

Follow existing files: four spaces and `snake_case` for Python; two spaces, single quotes, and no semicolons for TypeScript/Vue; standard Swift/Xcode formatting for iOS. Use `PascalCase` for Vue components, Swift types, and Python test classes; `camelCase` for TypeScript/Swift functions; and `test_*.py` for Python tests. Keep endpoint logic thin by moving reusable behavior into `Sever/services/`, and update `shared/types/` when API contracts change. No repository-wide formatter or linter is configured, so avoid unrelated reformatting.

## Testing Guidelines

Run backend tests with `python -m unittest discover -s Sever/tests -p "test_*.py"`. For iOS, generate the project, then run `xcodebuild test -project AI4PapersApp.xcodeproj -scheme AI4PapersApp -destination 'platform=iOS Simulator,name=iPhone 15'` from `ios/`. Add regression tests beside the affected layer; keep iOS fixtures in `ios/AI4PapersAppTests/Fixtures/`. `shared/api/__tests__/` uses Vitest syntax, but no runner is configured; document any setup you add. There is no stated coverage threshold.

## Commit & Pull Request Guidelines

History is sparse and uses short release-oriented messages, so no formal convention is established. Prefer concise imperative, scoped commits such as `server: handle arXiv retry-after`. Pull requests should explain behavior and affected clients, list validation commands, link relevant issues, and include screenshots or recordings for UI changes. Never commit API keys, `.env.production`, signing keys, generated bundles, or local runtime data.

## Validated Change Sync

After completing and validating user-requested file changes, add their absolute paths to `changed_files_abs_paths.txt`, keeping the list deduplicated, then follow `docs/change_sync_deploy_workflow.md` unless the user explicitly says not to sync or deploy. Prefer the one-command `deploy_changed_files.ps1` workflow with an explicit `View`, `Mobile`, `Both`, or `Backend` target. The current low-memory production server should normally use a locally validated build with `-UseLocalDist`; do not add `dist` to Git or the permanent changed-file list. Use server-side `-InstallNpm` builds only when explicitly appropriate and sufficient server memory is available. Upload only source, configuration, and intentional artifact files; never add private keys, `.env` files, credentials, runtime data, `node_modules`, test results, or generated build directories. The sync script uses the repository-external private key `%USERPROFILE%\.ssh\ai4papers_sync_ed25519`; do not copy that key into this repository or to the server. Never use the unrelated `sf_llin` key for this server.
