# Repository Guidelines

## Project Structure & Module Organization
- `Kaja_Tridi_v6_4.py` contains the entire PyQt6 application: UI, data models, thumbnail workers, and file operations.
- Optional assets live next to the script: `kajovo.ico` (window icon) and `reklama.mp4` (post-run video).
- Generated files: `Kaja_Tridi_Obrazky.log` (runtime logs) and `Kaja_session.json` (saved session state). Keep these out of source control.

## Build, Test, and Development Commands
- Install deps: `pip install PyQt6 Pillow send2trash` (send2trash is optional; without it deletes are permanent).
- Run locally: `python Kaja_Tridi_v6_4.py` (launches the GUI).
- There is no build step or separate CLI entrypoint.

## Coding Style & Naming Conventions
- Python: 4-space indentation; follow existing patterns (constants in `ALL_CAPS`, classes in `CamelCase`, functions in `snake_case`).
- Keep Czech UI strings and log text consistent with nearby dialogs; avoid mixing languages mid-flow.
- Use `BASE_DIR` for any new file I/O so relative paths remain beside the script.

## Testing Guidelines
- No automated tests are present.
- Manual smoke test: launch the app, scan a small test folder, verify thumbnails, duplicate detection, and run "SPUSŤ Petra" only on disposable copies (it moves/deletes files).

## Commit & Pull Request Guidelines
- No Git history is present here, so there is no established commit message convention. Use short, imperative subjects (e.g., "Add bucket rename shortcut") or Conventional Commits if you introduce history.
- PRs should describe user-facing changes, include screenshots for UI updates, and list manual test steps; call out any file-deletion risks explicitly.
- Token pro GitHub karelmartinek-a11y/FotoSelector je uložen mimo repozitář. Pokud je potřeba, použijte vlastní přihlášení nebo lokálně dostupný přístupový token.
