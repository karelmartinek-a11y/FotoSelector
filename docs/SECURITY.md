# Bezpečnost

## Co chráníme
- originální fotografie uživatele,
- OAuth tokeny a identitu cloudových účtů,
- lokální cache cloudových položek,
- session JSON a bucket cíle,
- správnost finálního přesunu nebo exportu.

## Nedůvěryhodné vstupy
- obsah lokálních adresářů,
- metadata a obsah přicházející z cloudových API,
- načítaný `Kaja_session.json`,
- placeholder soubory synchronizačních klientů.

## Aktivní ochrany
- Tokeny se neukládají do session JSON ani do `cloud_original_metadata`.
- Primárně se používá systémový keyring; fallback soubor má omezená práva.
- Cache žije mimo repozitář a má manifest s providerem, účtem, assetem a revizí.
- Lokální session roots se sanitizují přes `realpath()` a nesmí být root filesystemu.
- Cloud-only nebo nedostupný asset se nedává do duplicate pipeline jako lokální soubor.
- Cloudové originály se vzdáleně nemažou a nepřesouvají.
- `TRASH` u cloudových položek nespouští vzdálené mazání; uživatel musí zvolit explicitní exportní cíl, pokud chce kopii.
- Při kolizi cílového jména se používá non-conflicting cesta, takže nedochází k tichému přepsání.

## Kde se co ukládá
- `Kaja_session.json`: metadata session bez tokenů.
- systémový keyring nebo lokální fallback: OAuth tokeny.
- uživatelský app data adresář: cache a veřejná metadata cloudových účtů.

## Zbytková rizika
- Fallback token store je pořád lokální soubor; proto je pouze nouzový.
- Google Photos Picker zpřístupní jen položky, které uživatel v oficiálním pickeru sám vybere; aplikace proto netvrdí plný přístup k celé knihovně.
- Google Photos export režim zůstává k dispozici jako lokální fallback bez cloudového přihlášení.
- Apple Photos a iCloud Drive pracují podle toho, co je skutečně dostupné lokálně na disku.
