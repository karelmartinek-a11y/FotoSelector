# Forenzní audit popupů a jednotný standard

## Kompletní seznam popupů v programu

### Vlastní potvrzovací a informační dialogy
- `MainWindow._kajo_box`: jednotná náhrada za `QMessageBox` pro info, varování i chyby.
- `MainWindow.prompt_unsaved`: potvrzení u neuložené session.
- `MainWindow.on_new_session`: dvojité potvrzení založení nové session.
- `MainWindow.on_exit`: potvrzení ukončení programu.
- `MainWindow.on_run_apply`: varování před fyzickým přesunem a souhrn po dokončení nebo přerušení.
- `MainWindow.on_run_apply`: upozornění na chybějící cílové složky.
- `MainWindow.assign_selected_to_bucket`: upozornění při pokusu přesouvat mimo hlavní pohled.
- `MainWindow._do_save` a `MainWindow.on_load`: chybové hlášky při ukládání a načítání.

### Vstupní a nastavovací dialogy
- `KajoTextInputDialog`: přejmenování hromádek `T1` až `T4`.
- `ScanOptionsDialog`: nastavení minimální a maximální velikosti a ignorování systémových obrázků.

### Dialog pro práci s duplicitami
- `DuplicateGroupDialog`: rozhodování nad jednou skupinou duplicit, výběr snímku k zachování, auto režim, přesun do přihrádky `DUPLICITA`, bezpečné storno i zavřením křížkem.

### Systémové souborové dialogy převedené do stejného vzhledu
- `MainWindow._exec_directory_dialog`: výběr zdrojové složky a cílových složek hromádek.
- `MainWindow._exec_save_dialog`: výběr cesty pro uložení session.
- `MainWindow._exec_open_dialog`: výběr session pro načtení.

### Průběhové dialogy
- `DagmarProgress`: sken adresářů, filtrování podle velikosti, načítání obrázků, obnova session, hledání duplicit a fyzické provádění přesunů.

## Jednotný standard pro další použití

### Vzhled
- Všechny popupy používají stejné tmavé pozadí, akcentní záhlaví, stejnou typografii a stejnou sadu tlačítek.
- Nativní systémové popupy se nepoužívají; i výběr souborů a složek běží jako nenativní Qt dialog se stejným stylem.
- Tlačítka mají vždy semantické barvy: potvrzení `zlatá`, neutrální akce `tmavá plocha`, nevratné nebo rizikové akce `červená`.

### Ergonomie
- Každý dialog má stručný nadpis, vysvětlující podtitulek a čitelný obsah.
- Zavření křížkem je chápáno stejně jako bezpečné storno.
- Dialogy nepoužívají systémové zvuky; zvukové chování řídí aplikace sama.

### Dlouhé operace
- Každý průběhový dialog ukazuje uplynulý čas.
- Pokud je znám celkový rozsah, ukazuje i odhad zbývajícího času.
- Pokud rozsah znám není, běží spinner a text výslovně říká, že odhad ještě nelze spočítat.
- Zavření nebo stisk tlačítka pro přerušení okamžitě vyžádá storno běžící operace.
- Po přerušení fyzického přesunu aplikace přejde do bezpečného výchozího stavu, aby v session nezůstaly neplatné cesty.

### Pravidlo pro budoucí vývoj
- Nové popupy mají vznikat pouze přes `KajoChoiceDialog`, `KajoTextInputDialog`, `ScanOptionsDialog`, `DagmarProgress` nebo přes helpery `_exec_directory_dialog`, `_exec_open_dialog`, `_exec_save_dialog`.
