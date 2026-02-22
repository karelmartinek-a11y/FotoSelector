# Security

## Threat model
### Assets
- originální fotky uživatele,
- cílové složky třídění,
- session JSON (obsahuje lokální cesty).

### Entrypoints
- výběr složek přes UI,
- načtení session JSON,
- finální fyzický přesun/smazání souborů.

### Trust boundaries
- filesystem uživatele (nedůvěryhodný vstup: JSON i obsah složek),
- externí knihovny (Pillow, send2trash, PyQt6).

## Security guidelines
- Neprovádět deserializaci mimo `json` (žádný pickle/eval/exec).
- Session data validovat a filtrovat na scope aktuální relace.
- Nepřepisovat existující cílové soubory při přesunu.
- Nezapisovat secrets/PII do logu.

## Secrets
Repo nepoužívá API klíče. Pokud někdy přibudou, ukládat je mimo repo (CI secrets / OS keyring).

## Dependency policy
- Závislosti držet minimální (`PyQt6`, `Pillow`, `send2trash`).
- Při změně dependencies ověřit kompatibilitu a rizika supply chain.
