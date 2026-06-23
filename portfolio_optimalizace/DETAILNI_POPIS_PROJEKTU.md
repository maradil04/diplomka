# Detailní analyticko-technický popis projektu `portfolio_optimalizace`

## 1. Úvod a účel projektu

Tato práce je webová aplikace postavená nad frameworkem Dash/Flask v jazyce Python. Jejím hlavním účelem není pouze evidence investičního portfolia, ale především zpracování transakčních a tržních dat do podoby, ve které nad nimi lze provádět finanční a statistickou analýzu. Technická architektura aplikace proto slouží jako prostředek k tomu, aby bylo možné data bezpečně načíst, validovat, uložit, transformovat, analyzovat a následně interpretovat.

Aplikace umožňuje:

- přihlášení uživatele přes Google OAuth
- import transakční historie z CSV
- správu více portfolií na jednoho uživatele
- rekonstrukci aktuální i historické hodnoty portfolia z transakcí a cenových dat
- výpočet výkonnostních a rizikových metrik
- porovnání portfolia s benchmarky na základě časových řad
- zobrazení pasivních příjmů, výdajů a dividend
- predikci budoucího vývoje portfolia a jednotlivých aktiv za pomoci ARIMA a GARCH modelů
- rebalancing portfolia za pomoci tří optimalizačních modelů
- uložení výsledku rebalancingu jako nového odvozeného portfolia
- export portfolio reportu do PDF
- přepínání jazyka uživatelského rozhraní mezi češtinou a angličtinou

Jádrem aplikace je myšlenka, že všechna hlavní analytická místa pracují nad jedním aktivním portfoliem zvoleným v pravém sidebaru. Uživatel si tedy vybere portfolio, datum, případně soubor pro import, a následně všechny analytické stránky pracují nad stejným datovým kontextem. To je důležité nejen uživatelsky, ale i metodicky: dashboard, predikce, optimalizace i PDF report vycházejí ze stejného zdroje dat a jejich výstupy jsou proto vzájemně porovnatelné.

Aplikace je napsána jako serverem renderovaná interaktivní analytická aplikace v Dash. To znamená, že:

- frontend a backend jsou v jednom projektu
- velká část interaktivity je řízena Dash callbacky
- HTML struktura uživatelského rozhraní se skládá v Pythonu
- data se mezi prvky aplikace přenášejí přes `dcc.Store`, callbacky a session

Z pohledu diplomové práce je tedy technická část podřízena datově-analytickému cíli. Důležité není pouze to, že aplikace běží jako webová služba, ale zejména to, že převádí heterogenní vstupní data na časové řady, výnosy, rizikové charakteristiky, predikční vstupy a optimalizační scénáře.

## 2. Použitý technologický stack

Projekt používá následující hlavní knihovny a technologie:

- `Dash` pro samotné webové rozhraní a callbackový model.
- `Flask` jako serverový základ pod Dash aplikací.
- `PostgreSQL` jako cílovou databázi v hostovaném prostředí.
- `psycopg` pro komunikaci s PostgreSQL.
- `python-dotenv` pro načítání konfiguračních proměnných z `.env`.
- `pandas` a `numpy` pro datové transformace.
- `plotly` pro interaktivní grafy v samotné webové aplikaci.
- `matplotlib` pro serverové vykreslování grafů do PDF reportu.
- `statsmodels` pro modely ARIMA/SARIMA a statistické testy.
- `arch` pro GARCH modelování volatility.
- `scipy` pro optimalizační úlohy v rebalancingu.
- `scikit-learn` je v závislostech přítomen, ale aktuální jádro predikční logiky je postavené hlavně nad ARIMA/GARCH přístupem.
- `yfinance` jako pomocný zdroj při dohledávání mapování tickerů.
- `gunicorn` jako produkční WSGI server pro nasazení na Render.

Volba tohoto stacku dává smysl pro akademický i prototypově-produktový projekt, protože:

- Dash výrazně zrychluje vývoj datově orientovaného UI,
- `pandas` umožňuje pohodlnou práci s transakčními i cenovými daty,
- `plotly` je vhodné pro finanční dashboardy,
- PostgreSQL je robustnější než lokální SQLite při reálném hostingu,
- `statsmodels` a `arch` jsou vhodné pro statistické modelování časových řad.

## 3. Struktura projektu na vysoké úrovni

Kořen projektu obsahuje několik typů souborů a adresářů:

- `app.py`
  Základní bootstrap aplikace. Inicializuje Dash app, session, auth routy a databázi.

- `index.py`
  Hlavní kompoziční soubor aplikace. Definuje globální layout, `dcc.Store`, hlavní callbacky shellu, správu portfolií, export PDF a další orchestrace.

- `pages/`
  Jednotlivé stránky Dash aplikace:
  - `landing.py`
  - `home.py`
  - `predikce.py`
  - `rebalance.py`

- `components/`
  Znovupoužitelné UI komponenty:
  - `app_shell.py`
  - `auth_controls.py`
  - `portfolio_sidebar.py`

- `backend/`
  Serverová a datová logika:
  - přihlášení
  - session
  - databáze
  - repository vrstva
  - servisní vrstva

- `utils/`
  Pomocné utility:
  - výpočet historické hodnoty portfolia
  - překladový slovník a jazykové utility

- `assets/`
  Statické styly a obrázky načítané automaticky Dashem.

- `scripts/`
  Pomocný migrační skript pro přesun ze SQLite do PostgreSQL.

- `data/`, `df_prices.csv`, `portfolio.csv` a další CSV
  Data a záložní/fallback soubory používané pro tržní ceny nebo testovací data.

### 3.1 Analyticko-statistický pohled na strukturu

Z hlediska statistického zpracování lze projekt číst jako datovou pipeline, nikoliv pouze jako webovou aplikaci. Jednotlivé části systému na sebe navazují v tomto pořadí:

1. Uživatel importuje transakční data ve formátu CSV.
2. Importní vrstva data validuje, normalizuje názvy sloupců, převádí peněžní hodnoty a kontroluje povolené typy transakcí.
3. Databázová vrstva ukládá normalizované transakce, informace o portfoliích a historická cenová data.
4. Servisní vrstva převádí uložené transakce zpět do analytických `DataFrame` struktur.
5. Nad transakcemi a cenami se rekonstruuje historická držba aktiv a hodnota portfolia v čase.
6. Z časových řad se počítají výnosy, rizikové metriky, benchmarky, dividendové souhrny a TWR-like index očištěný o externí cash flow.
7. Predikční část používá transformované časové řady jako vstup pro ARIMA/SARIMA a případně GARCH model.
8. Rebalanční část převádí historické výnosy aktiv na optimalizační vstupy pro Mean-Variance, Risk Parity a CVaR model.
9. Výstupy jsou prezentovány v dashboardu, uloženy jako odvozené portfolio nebo exportovány do PDF reportu.

Tento pohled je důležitý, protože ukazuje, že aplikační architektura není samoúčelná. Slouží k tomu, aby byl zachován kontrolovaný tok od surových uživatelských dat až po statisticky interpretovatelné výstupy.

## 4. Životní cyklus aplikace po startu

### 4.1 `app.py`

Soubor `app.py` je nejnižší startovací vrstva aplikace.

Provádí tyto kroky:

1. Určí `PROJECT_ROOT`.
2. Načte konfigurační proměnné: při lokálním běhu ze souborů `.env` a `backend/.env`, při nasazení na Render z proměnných prostředí definovaných v nastavení služby.
3. Vytvoří Dash aplikaci:
   - `use_pages=True` zapíná Dash page systém,
   - `suppress_callback_exceptions=True` dovoluje callbacky i pro komponenty mimo aktuální layout stránky,
   - `prevent_initial_callbacks="initial_duplicate"` upravuje chování některých callbacků při inicializaci,
   - `meta_tags` nastavují viewport pro mobilní zařízení.
4. Získá Flask server přes `app.server`.
5. Zavolá:
   - `configure_session(server)`,
   - `init_db()`,
   - `register_auth_routes(server)`,
   - `register_route_guards(server)`.
6. Při spuštění přes `python app.py` navíc importuje `index.py` a spustí debug server.

Tato struktura zajišťuje, že:

- při produkčním běhu přes `gunicorn index:server` se použije layout a callbacky z `index.py`,
- při lokálním běhu přes `app.py` se shell a callbacky také korektně zaregistrují.

### 4.2 `index.py`

Soubor `index.py` je řídicí panel celé aplikace. Obsahuje:

- globální `app.layout`,
- `validation_layout`,
- definice session store komponent,
- callbacky pro bootstrap uživatele a portfolia,
- callbacky pro přepínání sidebarů,
- callbacky pro výběr/smazání/vytvoření portfolia,
- callback pro export PDF reportu,
- callback pro přebudování shellu při změně auth stavu, jazykové volby nebo portfolia.

## 5. Globální layout a stav aplikace

V `index.py` je definován hlavní layout jako `html.Div` obsahující:

- `dcc.Location(id="url")`
  Řídí aktuální URL a routování.

- `dcc.Store(id="stored-data", storage_type="session")`
  Uchovává serializovaná transakční data aktivního portfolia v session storage.

- `dcc.Store(id="auth-store", storage_type="session")`
  Ukládá informace o autentizaci uživatele pro frontend.

- `dcc.Store(id="portfolio-list-store", storage_type="session")`
  Uchovává seznam portfolií aktuálního uživatele.

- `dcc.Store(id="active-portfolio-store", storage_type="session")`
  Ukládá ID právě aktivního portfolia.

- `dcc.Store(id="language-store", storage_type="session", data="cs")`
  Ukládá zvolený jazyk UI. Výchozí jazyk je čeština.

- `dcc.Store(id="ui-store", storage_type="session", data={...})`
  Udržuje čistě prezentační stav shellu:
  - zda je otevřen pravý portfolio sidebar,
  - zda je otevřen levý mobilní menu sidebar.

- `dcc.Download(id="portfolio-report-download")`
  Slouží jako výstup pro generovaný PDF report.

- `dcc.Interval` komponenty pro bootstrap auth a aktivního portfolia.

- overlay pro “čekání na vložení portfolia”.

- `app-shell`, který obsahuje kompletní obal aplikace včetně headeru, menu, sidebarů a `page_container`.

### Proč jsou použity `dcc.Store`

`dcc.Store` je v Dash velmi vhodný pro lehký sdílený stav mezi callbacky. V tomto projektu je to klíčové, protože:

- uživatel si vybírá aktivní portfolio na jednom místě,
- několik stránek nad ním následně počítá dashboard, predikce i rebalance,
- UI musí reagovat bez vlastního ručního REST API.

## 6. App shell a rozvržení UI

Soubor `components/app_shell.py` skládá kostru celé aplikace:

- fixní horní záhlaví,
- pravý portfolio sidebar,
- tlačítko pro otevření pravého sidebaru,
- hlavní obsah přes `page_container`.

Záhlaví obsahuje:

- tlačítko `Menu`,
- navigační odkazy na stránky, pokud je uživatel přihlášen,
- blok autentizačních prvků uprostřed fixního záhlaví.

Pravý sidebar slouží jako globální ovládací panel, který je oddělený od navigace mezi stránkami, což odstraňuje nutnost duplikovat tyto ovládací prvky.


Soubor `components/auth_controls.py` funguje dle logiky:

- pokud uživatel není autentizovaný, zobrazí se Google login tlačítko,
- pokud přihlášen je, zobrazí se text “Přihlášen jako (Jméno uživatele převzaté z dat z Gmailu)” a odkaz na logout.

Tato komponenta je znovupoužitelná a není vázaná na konkrétní stránku.


Soubor `components/portfolio_sidebar.py` obsahuje pravý sidebar, který se skládá z těchto bloků:

1. Přepínač jazyka.
2. Nadpis a popis kontextu portfolia.
3. `DatePickerSingle` pro globální datum.
4. Sekci pro import CSV.
5. Stavovou hlášku importu.
6. Tlačítko pro export PDF reportu.
7. Progress bar pro generování reportu.
8. Formulář pro vytvoření nového portfolia.
9. Seznam uživatelových portfolií.
10. Status text ke stavu portfolia.
11. Tlačítko pro mazání již nepotřebných portfolií.

Do CSV importu je zabudovaná logika zobrazení požadovaného formátu a odmítnutí souborů v jakémkoliv jiném formátu.

## 7. Autentizace a session

Soubor `backend/session.py` řeší dvě věci:

- konfiguraci session cookie,
- guard logiku pro chráněné routy.

#### Konfigurace session

Nastavují se:

- `SECRET_KEY`,
- `SESSION_COOKIE_HTTPONLY`,
- `SESSION_COOKIE_SAMESITE`,
- `SESSION_COOKIE_SECURE`,
- `PREFERRED_URL_SCHEME`.

To znamená:

- cookie není dostupná JavaScriptem,
- v produkci je vynuceno HTTPS chování,
- session je centralizovaná na Flask úrovni.

#### Route guards

Existují chráněné cesty:

- `/dashboard`
- `/predikce`
- `/rebalance`

Pokud uživatel není přihlášen a zkusí vstoupit na chráněnou stránku, je přesměrován na `/`.

Součástí je i canonical redirect logika pro případy, kdy OAuth redirect URI a skutečný host neodpovídají a aplikace běží lokálně na jiné host/port kombinaci.

### 7.2 `backend/auth.py`

Tato vrstva implementuje Google OAuth:

- `/auth/login/google`
- `/auth/callback/google`
- `/auth/logout`

#### Login flow

Při kliknutí na přihlášení:

1. ověří se, že jsou nakonfigurovány OAuth proměnné,
2. vygeneruje se `state`,
3. state se uloží do session,
4. uživatel je přesměrován na Google consent screen.

#### Callback flow

Po návratu z Google:

1. zkontroluje se `state`,
2. vymění se autorizační kód za tokeny,
3. ověří se `id_token`,
4. načte se profil uživatele,
5. provede se `upsert_google_user`,
6. uloží se `user_id` do session,
7. nastaví nebo dohledá aktivní portfolio,
8. uživatel je přesměrován na `/dashboard`.

#### Logout

Logout čistí:

- `user_id`,
- `active_portfolio_id`,
- `oauth_state`.

## 8. Databázová vrstva

### 8.1 `backend/db.py`

Soubor `backend/db.py` shrnuje práci s PostgreSQL:

- čtení `DATABASE_URL`,
- vytváření nového připojení,
- per-request připojení přes Flask,
- zavření připojení,
- inicializaci schématu.

### 8.2 `backend/models.py`

Tento soubor ve skutečnosti nedefinuje ORM modely, ale SQL schéma. Obsahuje:

- `SCHEMA_STATEMENTS`
- `POST_SCHEMA_MIGRATIONS`
- `TICKER_MAPPING_SEED_ROWS`

Databázové tabulky:

Tabulka `users`

Ukládá:

- Google sub,
- email,
- jméno,
- avatar URL,
- timestamp vytvoření a posledního loginu.

Tabulka `portfolios` ukládá:

- vazbu na uživatele,
- název portfolia,
- základní měnu,
- zdrojový název souboru,
- volitelný odkaz na zdrojové portfolio,
- informaci, zda je portfolio odvozené z rebalancingu,
- počáteční efektivní datum,
- baseline investovaný kapitál.

Tato tabulka je klíčová pro podporu “normálních” i “odvozených” portfolií.

Tabulka `portfolio_transactions` obsahuje detaily transakcí portfolia:

- datum,
- ticker,
- typ,
- quantity,
- částku,
- původní částku v originální měně,
- měnu,
- `raw_json`.

`raw_json` je důležitý, protože umožňuje zachovat původní vstupní payload a znovu z něj rekonstruovat dataframe s vyšší věrností.

Tabulka `portfolio_imports` je auditní tabulka importů a obsahuje:

- název souboru,
- čas uploadu,
- počet řádků,
- status.

Tabulka `market_prices` ukládá historické cenové řady.



Tabulka `market_data_download_locks` se používá se pro koordinaci downloadů cenových dat, aby více procesů nestahovalo stejné tickery současně.

Tabulka `ticker_symbol_mappings` mapuje uživatelský ticker na provider ticker včetně informace o burze a měně.

### 8.3 Repository vrstva

Repository vrstva je jednoduchá, účelová a bez ORM. To je pro tento projekt pragmatické:

- logika SQL je transparentní,
- není zde další abstrakce navíc,
- aplikace je datově relativně jednoduchá.

#### `backend/repositories/users.py`

Obsahuje:

- `get_user_by_id`
- `get_user_by_google_sub`
- `upsert_google_user`

#### `backend/repositories/portfolios.py`

Obsahuje:

- listování portfolií uživatele,
- načtení portfolia podle ID a user ID,
- vytvoření portfolia,
- zajištění defaultního portfolia,
- update metadat portfolia,
- smazání portfolia.

#### `backend/repositories/transactions.py`

Obsahuje:

- kompletní nahrazení transakcí portfolia při importu,
- listování transakcí.

Zvolený model je “replace import”, tedy nový import přepíše předchozí transakce daného portfolia. To je jednoduché a deterministické chování vhodné pro tento typ aplikace.

#### `backend/repositories/market_prices.py`

Obsahuje:

- načítání cenových řad,
- přehled pokrytí dat,
- bulk upsert cen,
- správu download locků.

Je napsaná tak, aby fungovala:

- uvnitř Flask app contextu,
- i mimo něj.

To je důležité například pro skripty nebo servisní funkce mimo standardní request.

#### `backend/repositories/ticker_mappings.py`

Obsahuje CRUD logiku pro mapování tickerů.

## 9. Servisní vrstva


Kód `backend/services/portfolio_service.py` je základní business vrstvou pro práci s portfolii, jejíž základní funkcí je:

- vytvořit prázdný dataframe se správnými sloupci,
- normalizovat peněžní hodnoty,
- spočítat čistý investovaný kapitál,
- vrátit seznam portfolií,
- správně pracovat s aktivním portfoliem,
- nastavit aktivní portfolio do session,
- vytvořit portfolio,
- smazat portfolio,
- načíst transakce portfolia do dataframe.

Velmi důležitá je funkce `load_portfolio_transactions_dataframe`, protože:

- převádí data z DB do tvaru vhodného pro analytické funkce,
- snaží se využít `raw_json`, pokud existuje,
- doplňuje chybějící sloupce podle očekávané tabulkové struktury.

Pro zajištění robustního importu csv se využívá také `backend/services/import_service.py`.


#### Hlavní vlastnosti importu

- přijímá pouze `.csv`,
- podporuje více encodingů při dekódování,
- umí automaticky přemapovat běžné varianty názvů sloupců,
- umí normalizovat typy transakcí,
- umí normalizovat tickery a měny,
- validuje přítomnost povinných sloupců,
- validuje povinná pole podle typu transakce,
- převádí částky do EUR,
- ukládá původní i převedené hodnoty.

#### Kanonický očekávaný formát

Import očekává sloupce:

- `Date`
- `Ticker`
- `Type`
- `Quantity`
- `Price per share`
- `Total Amount`
- `Currency`
- `FX Rate`

Povinné sloupce:

- `Date`
- `Ticker`
- `Type`
- `Quantity`
- `Total Amount`
- `Currency`


Veškeré peněžní hodnoty se převádějí z původní měny na Eura. K tomu slouží `backend/services/currency_conversion_service.py`, které:

- normalizuje peněžní hodnoty,
- normalizuje kódy měn,
- používá tabulku orientačních kurzů do EUR.


Jedna z nejdůležitějších částí backendu na práci s daty je `backend/services/market_data_service.py`, která má na starosti:

- načítání cenových dat,
- fallback na lokální CSV,
- mapování tickerů na provider tickery,
- dohledání provider tickeru pomocí `yfinance`,
- cacheování cenových výsledků,
- koordinace uzamykání paralelního stahování.


#### Mapování tickerů

Vstupní tickery uživatele nejsou nutně stejné jako tickery datového providera. Například data uživatele mohou obsahovat ticker AAPL. Aplikace ovšem hladá podle systému BURZA.TICKER - v tomto případě by to tedy například mohlo být NYSE.AAPL. Proto se používá:

- `ticker_symbol_mappings` tabulka, která obsahuje záznamy o často obchodovaných aktivech a burz, na kterých se často obchodují,
- doplňkové dohledání přes `yfinance`.

#### PDF Report

Kód `backend/services/report_service.py` vytváří serverově generovaný PDF report.

#### Jak report vzniká

1. Načte se aktivní portfolio.
2. Načtou se transakce.
3. Načtou se ceny.
4. Importují se pomocné funkce z `pages.home` a `pages.predikce`.
5. Sestaví se:
   - souhrnné metriky,
   - rizikové metriky portfolia,
   - asset risk tabulka,
   - historie hodnoty portfolia,
   - alokace,
   - pasivní příjmy/výdaje,
   - měsíční dividendy,
   - portfolio predikce.
6. Vygenerují se stránky do PDF.

PDF report, stejně jako zbytek aplikace, podporuje českou i anglickou lokalizaci.

## 10. Utility vrstva

### 10. Převod transakcí na plnou historii

Zdrojovými daty pro výpočty ohledně portfolia je transakční historie klienta. Abychom aplikace tuto transakční historii převedla na časovou řadu, používá kód `utils/portfolio_history.py`, který obsahuje:

- extrakci tickerů,
- sestavení historie držených kusů,
- sjednocení cenových dat na společný datový panel,
- forward-fill cen,
- výpočet hodnoty pozic a součtu za portfolio.

Základní logika je:

1. z transakcí typu buy/sell se postaví kumulativní držení aktiv po dnech,
2. ceny se očistí a zarovnají,
3. pro každý ticker se přes `merge_asof` přiřadí poslední známý stav držených kusů,
4. spočítá se pozice `shares * adjusted_close`,
5. agreguje se za den.

To je rozumný přístup, protože:

- transakce a ceny mají různé granularitě,
- ceny nemusí být pro všechny tickery pro každý den,
- historická hodnota portfolia musí vzniknout z držby a cen dohromady.

### 10.2 `utils/i18n.py`

Tento soubor obsahuje:

- defaultní jazyk,
- seznam podporovaných jazyků,
- velký slovník `TRANSLATIONS`,
- helpery typu `t(...)`, `normalize_language(...)`, `language_options(...)`.

Právě zde je centralizována veškerá textová lokalizace UI.

To je správně, protože:

- texty nejsou rozseté bez kontroly po celé aplikaci,
- přidání dalšího jazyka je technicky snazší,
- callbacky mohou reagovat na `language-store`.

## 11. Landing Page

Landing page je minimalistická vizuální úvodní stránka dostupná na `/`. V aplikaci je definována v souboru `landing.py`. Stránka neobasuje žádné výpočty, ale slouží pouze jako úvodní vstup do aplikace, kde se uživatel může přihlásit a kam je odkázaný v případě, že chce vstoupit na limitovanou stránku bez přihlášení.


## 12. Domovská stránka

Stránka `home.py` funguje jako hlavní analytický dashboard portfolia. Jedná se stránku s nejvyšším počtem callbacků, které vracejí dashboard s mnoha analytickými ukazateli pro vybrané portfolio.

### 12.1 Hlavní role stránky

Dashboard poskytuje:

- souhrnnou tabulku portfolia,
- souhrn výnosu a rizika portfolia,
- tabulku rizika po jednotlivých aktivech,
- historický graf hodnoty portfolia,
- graf relativního vývoje cen aktiv,
- benchmark comparison,
- pie/bar rozpad portfolia,
- pasivní příjmy a výdaje,
- měsíční dividendy,
- upload/import callbacky,
- lokalizaci statických textů stránky.

### 12.2 Pomocné funkce ve `home.py`

Pro práci s daty je aplikaci používáno několik pomocných funkcí. Lze je rozdělit do kategorií:

#### a) práce s datem a časem

- `_to_naive_ts`
- `_to_naive_day`
- `_to_naive_series`
- `_force_naive_series`
- `_force_naive_scalar`

Tyto funkce sjednocují práci s timezone-aware i timezone-naive hodnotami. To je důležité, protože vstupy přicházejí z různých zdrojů a zejména knihovny pandas a Plotly jsou citlivé na nekonzistentní časové zdroje.

#### b) práce s peněžními daty

- `_parse_money_series`
- `_format_numeric_display`

Tyto funkce jsou důležité pro datovou kvalitu. Finanční data přicházejí v různých formátech a s různými oddělovači, takže před výpočtem výnosů, alokací nebo cash flow musí být převedena na konzistentní numerickou reprezentaci.

#### c) barevné utility pro grafy

Například:

- `_hex_to_rgb`
- `_rgb_to_hex`
- `_interpolate_hex`
- `_green_black_palette`

Tyto funkce slouží k tomu, aby grafy a heatmapy měly konzistentní vizuální styl.

#### d) analytické výpočty nad portfoliem

Například:

- `sjednoceni`
- `fees_divi`
- `soucasna_cena`
- `celkove_fee_divi`
- `vypocet_dividend`
- `hodnota_portfolia_v_case`
- `vypocitat_nevyuzity_kapital`
- `investovany_kapital`
- `vypocet_flow`
- `twr_index_from_df`
- `_resolve_summary_metrics`
- `make_benchmark_series`

Tyto funkce vracejí hodnoty, které se následně využívají v callbacích na dashboardy.

### 12.3 Klíčové výpočtové myšlenky dashboardu

#### Hodnota portfolia

Historická hodnota portfolia se nepočítá pouze ze součtu cash flow, ale z kombinace:

- transakční historie,
- držených množství,
- historických cen aktiv.

Metodicky jde o rekonstrukci stavové proměnné z událostních dat. Transakce určují změny pozic a cenová data určují tržní hodnotu těchto pozic v jednotlivých dnech. K tomu, abychom dostali časovou řadu historických hodnot portfolia, musíme tyto dva typy údajů propojit.

#### Odhad volné hotovosti

Funkce `vypocitat_nevyuzity_kapital` používá účetní logiku:

- plu vložení peněz 
- mínus výběr peněz
- mínus nákupy
- plus prodeje
- mínus poplatky
- plus dividendy

#### Rizikové a výkonnostní ukazatele

Hlavní stránka slouží hlavně k tomu, aby obsahovala dashboard, který dokáže odpovědět na tyto základní otázky:

- jaká je aktuální tržní hodnota portfolia?
- jak se hodnota vyvíjela v čase?
- jaké části portfolia nesou největší riziko?
- jak se portfolio chová ve vztahu k benchmarkům?
- jak významnou roli hrají dividendy, poplatky a nevyužitá hotovost?

Jedná se o základní údaje portfolia, které má uživatel společně na jedné stránce.

### 12.4 Callbacky dashboardu

Dashboard je rozdělen do několika callbacků, z nichž každý obsluhuje jeden vizuální blok. Mezi hlavní callbacky domovské stránky patří:

- výpočet sjednocené tabulky,
- výpočet tabulky fees/dividend,
- výpočet hlavní tabulky portfolia,
- výpočet souhrnu portfolia,
- výpočet souhrnu rizik,
- výpočet asset-level risk summary,
- graf relativního výkonu aktiv,
- update dropdownu tickerů,
- benchmark comparison,
- historický graf portfolia,
- monthly dividends,
- overlay prázdného stavu,
- upload CSV a uložení do DB,
- lokalizace statických textů.



## 13. Stránka Predikce

Stránka `predikce.py` představuje hlávní statistickou částí aplikace. Jejím cílem je automaticky detekovat nejlepší model ARIMA, otestovat rezidua a případně automaticky vybrat nejlepší model GARCH a pomocí těchto modelů predikovat jak hodnotu, tak i volatilitu portfolia. Jde tedy o tento analytický řetězec:

1. načtení aktivního portfolia nebo vybraného aktiva,
2. vytvoření vhodné časové řady,
3. převod řady na logaritmické výnosy,
4. výběr modelu střední hodnoty pomocí ARIMA,
5. diagnostika reziduí,
6. případné modelování volatility pomocí GARCH,
7. převod predikovaných výnosů zpět na hodnotovou nebo cenovou trajektorii,
8. vykreslení bodové predikce a pásem nejistoty.

### 13.1 Dvě úrovně predikce

Stránka řeší:

1. predikci celého portfolia,
2. predikci jednotlivého vybraného aktiva.

Tyto dvě úrovně jsou záměrně oddělené, protože pracují s odlišnou interpretací vstupní řady.

U predikce jednotlivého aktiva je vstupem cenová řada `adjusted_close` pro zvolený ticker. Tato řada reprezentuje historický vývoj jednoho instrumentu a po převodu na logaritmické výnosy vstupuje přímo do modelu.

U predikce celého portfolia není vhodné modelovat prostou hodnotu portfolia. Portfolio je totiž ovlivněno nejen trhem, ale také rozhodnutím uživatele o vkladech a výběrech. Proto se nejprve vytváří cash-flow-adjusted TWR index, který se následně modeluje jako časová řada investiční výkonnosti. Teprve po predikci tohoto indexu se výsledek škáluje zpět na aktuální peněžní hodnotu portfolia.

### 13.2 Proč není predikce na neupravené hodnotě portfolia

Důležitá vlastnost je, že predikce celého portfolia již nepracuje přímo s raw `portfolio_value`, ale s cash-flow-adjusted TWR normalizací.

To je metodicky zásadní, protože osobní portfolio může být deformováno vklady nebo výběry, což by vedlo k modelování s neodpovídajícími daty. Ve výsledku by predikce nebyly interpretovatelné. Očištění o externí cash flow tedy zajišťuje kvalitu vstupní řady, která následně vede k interpretovatelným výsledkům.

Konkrétně funkce `build_portfolio_twr_index` nejprve zavolá `build_portfolio_value_history`, která z transakcí a cen rekonstruuje hodnotu portfolia v čase. Následně se z transakční historie vyberou pouze externí peněžní toky:

- `CASH TOP-UP` jako kladný vklad,
- `CASH WITHDRAWAL` jako záporný výběr.

Tyto toky jsou zarovnány na nejbližší následující den, pro který existuje portfoliová hodnota. Poté se vytvoří pomocná logika:

- hodnota portfolia je chápána jako `units * NAV`,
- externí vklad nebo výběr mění počet jednotek,
- tržní vývoj mění hodnotu jedné jednotky, tedy `NAV`,
- TWR výnos je odvozen ze změny `NAV`, nikoliv ze změny celkové hodnoty portfolia.

Tím se řeší zásadní problém osobních portfolií: pokud investor vloží další kapitál, celková hodnota portfolia vzroste, ale nejde o výnos vytvořený trhem. TWR-like index tento efekt odděluje. Výchozí hodnota indexu je nastavena na `100`, takže výsledná řada je interpretovatelná jako normalizovaná výkonnost portfolia od začátku sledovaného období.

### 13.3 Hlavní analytické bloky

Stránka obsahuje:

- načtení aktivního portfolia přes `active-portfolio-store`,
- načtení relevantních cenových dat podle tickerů v portfoliu,
- rekonstrukci historické hodnoty portfolia,
- výpočet cash-flow-adjusted TWR indexu,
- převzorkování řad na obchodní dny pomocí `asfreq("B").ffill()`,
- převod cen na returns,
- log returns,
- train/test split pro časové řady,
- odhad minimální diferenciace přes ADF,
- grid search ARIMA,
- grid search SARIMA,
- testy reziduí,
- detekci ARCH efektu,
- grid search GARCH,
- konstrukci sigma pásem,
- převod predikovaných returns zpět na price/value path.

V aktivním callbacku je horizont predikce nastaven na `30` budoucích obchodních dní. Zároveň je požadováno alespoň `80` pozorování vstupní časové řady. Pokud portfolio nebo aktivum nemá dostatek historických dat, aplikace model nespustí a místo toho uživateli zobrazí informaci o nedostatečném počtu pozorování. Toto omezení je důležité, protože ARIMA i GARCH modely jsou na krátkých řadách velmi nestabilní.

Pro portfolio se vytvářejí dvě řady:

- `performance_series`, tedy TWR index použitý pro modelování výnosů,
- `current_value_series`, tedy skutečná historická hodnota portfolia použitá pro vykreslení a finální škálování predikce.

Pro jednotlivé aktivum se pracuje přímo s řadou `adjusted_close`. V obou případech se vstup převádí na logaritmické výnosy:

`r_t = log(P_t) - log(P_{t-1})`

U portfolia je `P_t` hodnota TWR indexu, u aktiva je `P_t` upravená závěrečná cena. Použití logaritmických výnosů je vhodné proto, že výnosy jsou aditivní v čase a při převodu zpět na cenu lze použít exponenciálu kumulovaného součtu výnosů.

### 13.4 ARIMA model

Funkce `pick_mean_model_rmse`:

- rozdělí data na train/test,
- otestuje varianty ARIMA,
- případně zohlední sezónnost,
- vrátí nejlepší model podle RMSE.

Aplikace tedy porovnává více parametrizací a používá chybovou metriku RMSE na testovací části časové řady. Konkrétní implementace pracuje následovně:

1. Řada logaritmických výnosů se rozdělí chronologicky na trénovací a testovací část v poměru 80/20.
2. Funkce `estimate_d_min_adf` pomocí ADF testu hledá nejmenší stupeň diferenciace `d`, při kterém lze zamítnout jednotkový kořen. Testuje se maximálně do `d = 2`.
3. Nad trénovací částí se provede grid search ARIMA modelů. Vzhledem k výkonnosti aplikace se prohledávají pouze hodnoty `p` od 0 do 3, `q` od 0 do 3 a hodnoty `d` v rozsahu odhadnutém ADF testem.
4. Každý kandidátní model se natrénuje na trénovací části a vytvoří predikci délky testovací části.
5. Predikce se porovná se skutečnou testovací řadou a vypočítá se hodnota RMSE.
6. U reziduí se navíc provádí Ljung-Box test autokorelace. Hledáme model, jehož rezidua se chovají jako bílý šum.
8. Finální ARIMA model se poté znovu natrénuje na celé dostupné řadě logaritmických výnosů a z něj se generuje budoucí predikce.

Nejlepší model se tedy vybírá podle toho, jak dobře dokáže predikovat a ne jak dobře vysvětluje minulost.


### 13.5 GARCH model

Pokud rezidua mean modelu vykazují ARCH efekt, používá se GARCH pro odhad volatility a pásem nejistoty. To je metodicky vhodné pro finanční časové řady, protože volatilita bývá heteroskedastická a konstantní variance je s daty vývoje cen akcií nerealistická.

GARCH model, narozdíl od bodové predikce ARIMA modelu, modeluje proměnlivost volatility v čase. Díky tomu může aplikace zobrazit také pásma nejistoty, která lépe odpovídají povaze finančních dat.

Implementace postupuje ve dvou krocích. Nejprve funkce `detect_arch_effect` aplikuje ARCH test na rezidua ARIMA modelu. Používá se hladina významnosti `alpha = 0.05` a `12` zpoždění. Pokud test ARCH efekt nepotvrdí, GARCH model se nepoužije a aplikace později sáhne po jednodušší historické volatilitě logaritmických výnosů.

Pokud je ARCH efekt detekován, funkce `forecast_sigma_series` pokračuje modelem GARCH. Rezidua se škálují na procenta, tedy násobí se hodnotou `100`, protože knihovna `arch` numericky lépe pracuje s výnosy v procentních bodech. Po odhadu modelu se výsledná volatilita převádí zpět dělením `100`.

Parametry GARCH mohou nabývat hodnot 0-2. Kód obsahuje grid search funkci `grid_search_garch_rmse`, která porovnává kombinace `p` a `q`. Hodnocení GARCH části je založeno na RMSE mezi druhou mocninou testovacích výnosů a predikovanou variancí.

Výstupem volatility modelu není cena, ale budoucí řada směrodatných odchylek `sigma_future`. Tato řada se následně používá při konstrukci predikčních pásem.

### 13.6 Převod predikovaných výnosů zpět na hodnotovou trajektorii

ARIMA model nepredikuje přímo cenu aktiva ani peněžní hodnotu portfolia. Predikuje budoucí logaritmické výnosy. Ty je nutné převést zpět na úroveň, kterou lze zobrazit v grafu.

Převod probíhá pomocí vztahu:

`P_{t+h} = P_t * exp(sum(r_1, ..., r_h))`

V kódu tuto logiku reprezentuje funkce `returns_to_price_path`. U jednotlivého aktiva je `P_t` poslední známá cena `adjusted_close`. Výsledkem je přímo budoucí cenová trajektorie aktiva.

U portfolia je postup o jeden krok složitější:

1. ARIMA model predikuje výnosy TWR indexu.
2. Tyto výnosy se převedou na budoucí trajektorii TWR indexu.
3. Poslední hodnota skutečného portfolia se porovná s poslední hodnotou TWR indexu.
4. Vypočte se škálovací faktor: `scale = current_portfolio_value / last_index_level`
5. Predikovaný index a jeho pásma se tímto faktorem vynásobí.

Díky tomu model stále pracuje s očištěnou výkonnostní řadou, ale výsledný graf je zobrazen v peněžní hodnotě portfolia. Tato kombinace je důležitá, protože zajišťuje, že model není ovlivněn vklady a výběry, ale zároveň je graficky interpretovatelný pro uživatele, který vidí svůj graf hodnoty portfolia s predickcí.

### 13.7 Konstrukce pásem nejistoty

Pásma nejistoty jsou konstruována funkcí `sigma_to_price_bands`. Vychází se z predikovaných logaritmických výnosů a z budoucí volatility `sigma_future`. Pro každý horizont se kumuluje:

- očekávaný výnos,
- odhadovaná variance.

Kumulovaná variance se počítá jako součet budoucích variancí:

`var_cum_h = sum(sigma_i^2)`

Směrodatná odchylka pro daný horizont je potom:

`std_cum_h = sqrt(var_cum_h)`

Horní a dolní pásmo se konstruuje jako:

`upper_h = P_t * exp(mu_cum_h + k * std_cum_h)`

`lower_h = P_t * exp(mu_cum_h - k * std_cum_h)`

Aplikace vykresluje dvě úrovně pásem:

- `±1 sigma` jako užší pásmo,
- `±2 sigma` jako širší pásmo.

Pokud GARCH model není použit nebo vrátí prázdnou volatilitu, aplikace použije historickou směrodatnou odchylku logaritmických výnosů. Tím je zajištěno, že uživatel dostane pásma nejistoty i v situaci, kdy ARCH efekt není statisticky potvrzen.

### 13.8 Interpretace predikce

Predikční výstup je nutné chápat jako modelový scénář, nikoliv jako jistou předpověď budoucí ceny nebo hodnoty portfolia. Výsledek závisí na:

- délce a kvalitě historické řady,
- stabilitě statistických vlastností dat,
- přítomnosti strukturálních změn na trhu,
- zvolené transformaci výnosů,
- odhadu volatility.

Právě proto aplikace pracuje s historickou řadou, střední predikovanou trajektorií a volatilními pásmy. Uživatel tak nedostává pouze jedno číslo, ale kontext pro interpretaci nejistoty.

Z hlediska interpretace je potřeba rozlišit tři vrstvy výstupu:

- historická část grafu ukazuje skutečně pozorovaná data,
- tečkovaná predikční křivka ukazuje střední modelovou trajektorii,
- oranžová pásma ukazují nejistotu vyplývající z volatility.


### 13.9 Výstupy stránky

Portfolio predikce vrací:

- historickou řadu,
- budoucí predikovanou střední trajektorii,
- volatilní pásma,
- textové shrnutí modelu.

Textové shrnutí modelu je vloženo přímo do titulku grafu. U portfolia obsahuje například informaci, že ARIMA byla aplikována na cash-flow-adjusted returns, hodnotu RMSE, p-hodnotu ARCH testu a informaci, zda byl použit GARCH model. U predikce jednotlivého aktiva je výstup analogický, pouze vstupem není TWR index, ale cenová řada zvoleného tickeru.

### 13.10 Callbacková logika a uživatelský tok

Predikční stránka obsahuje dva hlavní callbacky:

- `portfolio_mean_plus_volatility_forecast`,
- `mean_plus_volatility_forecast`.

Callback `portfolio_mean_plus_volatility_forecast` se spouští tlačítkem pro predikci portfolia. Nejprve načte aktivní portfolio, následně jeho tickery, odpovídající tržní data, TWR index, logaritmické výnosy, ARIMA model, rezidua, volatilitu a nakonec vytvoří graf. Tento výpočet je spouštěn explicitně tlačítkem, protože je výpočetně náročnější než běžné dashboard callbacky a kdyby se restartoval při každém znovu načtení stránky, tak by celou aplikaci výrazně zpomaloval.

Callback `mean_plus_volatility_forecast` se spouští výběrem tickeru v dropdownu. Seznam tickerů se vytváří z aktivního portfolia, takže uživatel nepredikuje libovolné aktivum mimo svůj kontext, ale pouze instrumenty, které v portfoliu reálně má. Pro vybraný ticker se načtou cenová data, převedou se na business-day časovou řadu, vypočtou se logaritmické výnosy a použije se stejný ARIMA plus GARCH postup jako u portfolia.

Tato konstrukce zajišťuje metodickou konzistenci celé stránky: portfolio i jednotlivá aktiva používají stejnou statistickou logiku, liší se pouze vstupní časová řada a finální interpretace výsledku.

## 14. Stránka Rebalance

Stránka `rebalance.py` představuje optimalizační část aplikace. Zatímco dashboard popisuje současný a historický stav portfolia a predikce modeluje možný budoucí vývoj, rebalancing hledá alternativní rozložení vah aktiv podle zvoleného optimalizačního kritéria.

### 14.1 Tři modely

Implementovány jsou:

1. Mean-Variance
2. Risk Parity
3. CVaR optimalizace

### 14.2 Převod cen na výnosy

Základním vstupem optimalizačních modelů jsou historické returns spočítané z `adjusted_close`.

Tento krok je zásadní, protože optimalizační modely nepracují přímo s cenami aktiv, ale s jejich výnosovým a rizikovým profilem. Z cenových řad se proto odvozují výnosy, volatilita, kovarianční struktura a případně scénáře ztrát. Kvalita těchto vstupů přímo ovlivňuje kvalitu výsledných vah.

### 14.3 Mean-Variance

Cílem je maximalizovat užitek typu:

- očekávaný výnos
- minus penalizace variance podle parametru `lambda`

Je to klasický Markowitzovský přístup.

Model vychází z předpokladu, že investor hodnotí portfolio podle kompromisu mezi očekávaným výnosem a rizikem měřeným variancí. Parametr `lambda` reprezentuje míru averze k riziku: vyšší penalizace variance vede ke konzervativnějším vahám, zatímco nižší penalizace dovoluje agresivnější alokaci.

### 14.4 Risk Parity

Risk parity se snaží rozložit rizikové příspěvky aktiv rovnoměrně. Výhoda:

- méně spoléhá na přesné odhady očekávaných výnosů,
- často vede ke stabilnějším vahám.

Statisticky je tento model užitečný proto, že odhady očekávaných výnosů bývají u finančních aktiv velmi nejisté. Risk Parity proto přesouvá důraz z průměrného výnosu na strukturu rizika a snaží se zabránit tomu, aby celkové riziko portfolia dominovalo pouze několik volatilních pozic.

### 14.5 CVaR

CVaR optimalizace cílí na omezení tail risku, tedy ztrát v nepříznivých scénářích.

To je dobré doplnění k variance-based přístupům, protože variance sama nerozlišuje “dobrou” a “špatnou” volatilitu.

CVaR pracuje s průměrnou ztrátou v nejhorší části rozdělení. Tím lépe zachycuje situace, které jsou pro investora prakticky nejnebezpečnější: výrazné poklesy hodnoty portfolia. Tento přístup je vhodný zejména tam, kde rozdělení výnosů nemusí být symetrické a kde samotná směrodatná odchylka nestačí k popisu rizika.

### 14.6 Uložení výsledku

Každý model může výsledek uložit jako nové portfolio:

- `rebalance_mv`
- `rebalance_rp`
- `rebalance_cvar`

To výrazně zvyšuje praktičnost aplikace, protože rebalance není jen jednorázový výpočet, ale může se stát plnohodnotným analyzovatelným portfoliem. Výskledky tedy nejsou odděleny od zbytku systému. Odvozené portfolio lze znovu vyhodnotit v dashboardu, porovnat s původním portfoliem, predikovat a exportovat. Rebalancing se tak stává součástí opakovatelného analytického cyklu. Historie portfolia se počítá tak, že se předpokládá, že všechny aktiva byla nakoupena v den první transakce portfolia.

Případně jde výsledné váhy a tickery kopírovat a vložit do tabulkových editorů.

### 14.7 Layout stránky

Stránka obsahuje tři paralelní modelové karty s:

- parametry,
- tlačítkem spuštění,
- výsledkovou tabulkou,
- tlačítkem uložení.

Byla doplněna výrazná mobilní responzivita, aby se modely na úzkých obrazovkách skládaly pod sebe.

## 15. Lokalizace

Lokalizace je navržena tak, aby:

- výchozí jazyk byl čeština,
- uživatel mohl přepínat jazyk v sidebaru,
- jazyk se ukládal do session storage,
- stránky i PDF reagovaly na zvolený jazyk.

Technicky to funguje takto:

1. Dropdown v sidebaru mění `language-switch`.
2. Callback v `index.py` zapisuje normalizovanou hodnotu do `language-store`.
3. Statické i dynamické texty na stránkách používají `t(language, key)`.
4. PDF export dostává jazyk jako argument.

Tento přístup je robustnější než ruční podmínky přímo v komponentách, protože centralizuje jazykové klíče.

## 16. PDF export

PDF export je navázán na aktuálně zvolené portfolio a jazyk.

Obsah reportu typicky zahrnuje:

- titulní stránku,
- dashboard summary,
- rizikové metriky portfolia,
- holdings tabulky,
- asset risk tabulku,
- alokaci portfolia,
- pasivní příjmy/výdaje,
- měsíční dividendy,
- historický vývoj portfolia,
- portfolio prediction.

Generování probíhá serverově a callback na export zobrazuje progress bar, protože výpočet může trvat delší dobu.

## 17. Deployment a hosting

### 17.1 `render.yaml`

Nasazení je připraveno na Render:

- build command: `pip install -r requirements.txt`
- start command: `gunicorn index:server`

To znamená, že produkční vstupní bod aplikace je `index.py`, nikoliv `app.py`.

### 17.2 Environment proměnné

Projekt očekává minimálně:

- `DATABASE_URL`
- `FLASK_SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- případně `EODHD_API_TOKEN`

### 17.3 Lokální a hostované prostředí

Projekt má stále i lokální artefakty:

- `.env`
- `app.db`
- `test.db`
- fallback CSV soubory

To je běžné u projektu, který se vyvíjel lokálně a následně byl hostován.

## 18. Migrační skript

Soubor `scripts/migrate_sqlite_to_postgres.py` slouží k migraci dat ze staré SQLite databáze `app.db` do PostgreSQL.

Migruje:

- uživatele,
- portfolia,
- transakce,
- importy.

Takový skript je důležitý, protože ukazuje, že projekt prošel přechodem z lokálního jednoduššího úložiště na produkčnější databázovou vrstvu.

## 19. Datový tok aplikace

Z pohledu “co se stane, když uživatel pracuje s aplikací” lze projekt číst takto:

### Scénář A – přihlášení

1. Uživatel přijde na landing page.
2. Klikne na Google login.
3. Projde OAuth flow.
4. Do session se uloží `user_id`.
5. Bootstrap callback načte auth stav a portfolia.

### Scénář B – výběr portfolia

1. Uživatel v sidebaru klikne na portfolio.
2. Callback nastaví `active-portfolio-store`.
3. Dashboard si z DB načte transakce aktivního portfolia.
4. Ostatní stránky začnou pracovat nad stejným kontextem.

### Scénář C – import CSV

1. Uživatel otevře import sekci.
2. Nahraje CSV.
3. `parse_upload_contents` soubor dekóduje a validuje.
4. Transakce se převedou do DB záznamů.
5. Portfolio metadata se aktualizují.
6. Dashboard po dalším načtení pracuje s novými daty.

### Scénář D – predikce

1. Uživatel otevře stránku predikce.
2. Načtou se transakce a ceny aktivního portfolia.
3. Vypočte se TWR index a returns.
4. Vybere se mean model.
5. Případně se modeluje volatilita.
6. Vykreslí se forecast a pásma nejistoty.

### Scénář E – rebalance

1. Uživatel otevře rebalance stránku.
2. Načtou se returns aktivního portfolia.
3. Spustí se zvolený optimalizační model.
4. Výsledek lze zkopírovat nebo uložit jako nové portfolio.

### Scénář F – PDF export

1. Uživatel klikne na export v sidebaru.
2. Zobrazí se progress bar.
3. Backend vygeneruje PDF.
4. Prohlížeč stáhne soubor.

## 20. Návrhové důvody a silné stránky řešení

Mezi hlavní silné stránky řešení patří zejména propojení datového zpracování, statistické analýzy a technické implementace:

### a) Kontrolovaný tok od surových dat k interpretaci

Transakční data nejsou používána přímo bez úprav. Nejprve procházejí validací, normalizací, uložením, rekonstrukcí portfoliové historie a teprve následně jsou použita pro výpočty metrik, predikce a optimalizaci. To snižuje riziko, že statistické výstupy budou založeny na nekonzistentních vstupech.

### b) Jedno aktivní portfolio jako globální analytický kontext

Jedno aktivní portfolio výrazně zjednodušuje práci uživatele a zároveň zajišťuje metodickou konzistenci. Dashboard, predikce, rebalancing i PDF report pracují nad stejným portfoliem a stejným datovým stavem.

### c) Robustní CSV import a normalizace dat

Validace je dostatečně přísná, aby odmítla strukturálně nevhodná data, ale zároveň uživatelsky vstřícná vůči běžným formátovým odchylkám. To je důležité zejména proto, že kvalita vstupních dat přímo určuje kvalitu výnosových, rizikových a predikčních výpočtů.

### d) Cash-flow-adjusted predikce portfolia

Normalizovaná TWR-like řada zohledňuje, že velké cash top-upy nebo výběry by jinak znehodnotily model. Predikční část proto pracuje s řadou, která lépe reprezentuje investiční výkonnost, ne pouze změnu objemu vloženého kapitálu.

### e) Kombinace více statistických a optimalizačních pohledů

Aplikace nekončí u jedné metriky ani u jednoho modelu. Kombinuje historickou výkonnost, rizikové ukazatele, benchmarky, ARIMA/SARIMA modelování, GARCH volatilitu a tři rebalanční přístupy. Díky tomu poskytuje širší analytický obraz portfolia.

### f) Podpora odvozených portfolií

Výsledek rebalancingu je plnohodnotný objekt, ne jen jednorázový výstup. Lze jej dále analyzovat stejnými nástroji jako původní portfolio.

### g) Repository + service rozdělení

Oddělení SQL operací od business a analytické logiky zvyšuje přehlednost projektu a usnadňuje další rozšiřování datové vrstvy.

### h) Přímé Dash callbacky místo zbytečně složité API vrstvy

Pro tento typ analytické aplikace je to pragmatické řešení, protože výpočtové bloky jsou úzce propojené s vizuálními výstupy.

### i) Lokalizace UI i PDF

To zvyšuje použitelnost i kvalitu výstupů.

## 21. Současné kompromisy a limity

Projekt je funkční a architektonicky smysluplný, ale nese i několik přirozených kompromisů:

- některé výpočtové funkce jsou stále poměrně rozsáhlé přímo ve stránkách,
- dashboard i predikce mají hodně logiky v jednom souboru,
- část fallback dat je stále držena v CSV,
- session secret má v kódu lokální default pro development,
- některé texty a encoding stopy naznačují historický vývoj přes více prostředí a kódování.

Tyto limity však samy o sobě neshazují funkčnost. Spíše ukazují přirozený vývoj projektu od akademického prototypu k robustnější hostované aplikaci.

## 22. Přehled významných souborů

### Kořen projektu

- `app.py` – bootstrap Dash/Flask aplikace
- `index.py` – hlavní layout a globální callbacky
- `render.yaml` – deploy konfigurace pro Render
- `requirements.txt` – Python závislosti
- `runtime.txt` – runtime specifikace pro hosting
- `df_prices.csv` – fallback historická cenová data
- `portfolio.csv` – ukázkové portfolio
- `portfolio_currency.csv` – pomocná ukázková data
- `stahovani.py` – starší pomocný skript na stahování cen
- `app.db`, `test.db` – historické/lokální databázové artefakty

### `backend/`

- `auth.py` – Google OAuth
- `db.py` – DB connection management a init
- `models.py` – SQL schéma
- `session.py` – session a route guards
- `repositories/` – nízkoúrovňové SQL operace
- `services/` – business logika

### `components/`

- `app_shell.py` – celkové obalení aplikace
- `auth_controls.py` – přihlášení/odhlášení
- `portfolio_sidebar.py` – pravý portfolio sidebar

### `pages/`

- `landing.py` – veřejná landing page
- `home.py` – hlavní dashboard
- `predikce.py` – predikce
- `rebalance.py` – optimalizace portfolia

### `utils/`

- `i18n.py` – lokalizace
- `portfolio_history.py` – historie portfolia z transakcí a cen

### `scripts/`

- `migrate_sqlite_to_postgres.py` – jednorázová migrace databáze

## 23. Shrnutí analyticko-technického řešení jednou větou

Projekt je interaktivní analytická aplikace postavená nad Dash, Flaskem a PostgreSQL, která převádí importovanou transakční historii a tržní ceny na časové řady portfolia, výnosové a rizikové metriky, statistické predikce, optimalizační návrhy rebalancingu a strukturovaný PDF report.

## 24. Shrnutí z pohledu diplomové práce

Z pohledu diplomové práce je na tomto projektu důležité, že kombinuje:

- datové inženýrství,
- webové aplikační rozhraní,
- finanční analytiku,
- časové řady,
- optimalizační modely,
- autentizaci,
- persistentní ukládání dat,
- export profesionálního reportu.

Nejde tedy pouze o vizualizační dashboard, ale o relativně komplexní analytický systém, kde jednotlivé části dávají smysl jako celek:

- uživatel data vloží,
- systém je validuje a uloží,
- transakční data se spojí s historickými cenami,
- z nich se rekonstruuje hodnota a struktura portfolia v čase,
- systém vypočte výkonnostní, rizikové a cash-flow ukazatele,
- časové řady jsou použity pro predikci budoucího vývoje,
- výnosová data jsou použita pro návrh alternativní alokace,
- výsledky jsou interpretovány v dashboardu a exportovány do reportu.

To je z akademického hlediska silné, protože projekt nestaví pouze jednu dílčí funkcionalitu, ale řeší plný tok od vstupu dat přes jejich statistické zpracování až po interpretaci a export výsledku. Technická část aplikace je přitom důležitá hlavně proto, že umožňuje opakovatelné, konzistentní a uživatelsky dostupné provedení těchto analytických procesů.
