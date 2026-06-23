# Detailní popis statistických procesů použitých v aplikaci

## 1. Úvod

Tento dokument se soustředí výhradně na statistické a kvantitativní procesy použité v aplikaci `portfolio_optimalizace`. Cílem není popsat celé webové rozhraní, ale přesně vysvětlit:

- jaké statistické postupy jsou použity,
- na jakých datech pracují,
- proč byly zvoleny,
- jak jsou implementovány v aplikaci,
- jaké mají výhody, omezení a interpretační význam.

V aplikaci se statistické procesy používají ve třech hlavních oblastech:

1. výpočet historické výkonnosti portfolia,
2. výpočet rizikových metrik,
3. predikce a optimalizace portfolia.

## 2. Povaha vstupních dat

### 2.1 Transakční data

Primární vstup aplikace tvoří transakční historie portfolia. Tyto transakce obsahují zejména:

- datum,
- ticker,
- typ transakce,
- množství,
- cenu za kus,
- celkovou hodnotu transakce,
- měnu,
- případně FX kurz.

Z hlediska statistiky je důležité, že samotné transakce nejsou časovou řadou cen. Jsou to události, které mění:

- stav držených kusů,
- strukturu portfolia,
- cash flow investora.

Proto je před jakoukoli analýzou nutné z těchto transakcí odvodit časovou řadu portfoliové hodnoty nebo portfoliové výkonnosti.

### 2.2 Cenová data

Sekundární vstup tvoří historické tržní ceny aktiv. Aplikace využívá hlavně sloupec `adjusted_close`, tedy upravenou závěrečnou cenu. Ta je vhodnější než raw close, protože lépe reprezentuje ekonomicky srovnatelnou hodnotu instrumentu v čase.

Z cenových dat se odvozují:

- historické hodnoty pozic,
- výnosy aktiv,
- volatilita aktiv,
- korelace a kovariance aktiv,
- vstupy do predikce,
- vstupy do rebalancing modelů.

## 3. Rekonstrukce historické hodnoty portfolia

### 3.1 Problém

Historická hodnota portfolia není přímo dána pouze transakcemi ani pouze cenami. Je nutné spojit:

- kolik kusů bylo v daný den drženo,
- jaká byla v daný den cena každého aktiva.

### 3.2 Statistická a datová logika řešení

V modulu `utils/portfolio_history.py` probíhá následující postup:

1. Z transakcí typu `BUY - MARKET` a `SELL - MARKET` se vytvoří časová řada čistých změn počtu kusů.
2. Tyto změny se agregují po dnech a po tickeru.
3. Nad nimi se počítá kumulativní součet, čímž vzniká počet držených kusů v čase.
4. Cenové řady aktiv se očistí, zarovnají a doplní forward-fillem.
5. Pomocí časového spojení `merge_asof` se pro každé datum ceny přiřadí poslední známý stav držby.
6. Pro každé aktivum se počítá:

`position_value = CumulativeShares * adjusted_close`

7. Součtem přes všechna aktiva vzniká hodnota portfolia v čase.

### 3.3 Proč je tento postup vhodný

Tento přístup je metodicky správný, protože:

- transakce přicházejí v diskrétních okamžicích,
- ceny aktiv existují po obchodních dnech,
- počet držených kusů mezi dvěma transakcemi zůstává konstantní,
- `merge_asof` je přirozená technika pro přiřazení posledního známého stavu k danému datu.

### 3.4 Statistický význam

Tento krok je základní předzpracování. Bez něj by nebylo možné definovat:

- časovou řadu portfoliové hodnoty,
- historické výnosy portfolia,
- drawdown,
- volatilitu portfolia,
- predikci portfolia.

## 4. Čištění a normalizace peněžních hodnot

### 4.1 Motivace

Importovaná data mohou obsahovat:

- mezery,
- nezlomitelné mezery,
- čárky jako desetinný oddělovač,
- tečky jako oddělovač tisíců,
- symboly měn.

Proto je nejprve nutné převést textové peněžní zápisy na číselný formát.

### 4.2 Použitý postup

V `portfolio_service.py`, `import_service.py` a `currency_conversion_service.py` jsou použity normalizační funkce, které:

- odstraní symboly měn,
- vyčistí oddělovače,
- převedou čísla do strojově čitelného tvaru,
- zkusí zachovat ekonomický význam částky.

### 4.3 Statistický význam

Čistota numerických dat je zásadní, protože:

- chybná částka by poškodila ROI,
- chybný cash flow by poškodil TWR,
- chybná cena by poškodila alokaci i rizikové metriky,
- chybná převodní logika by deformovala mult měnové portfolio.

## 5. Měnová normalizace a převod do EUR

### 5.1 Proč je převod potřeba

Portfolio může obsahovat aktiva denominovaná v různých měnách. Aby bylo možné:

- sčítat hodnoty,
- počítat celkový profit,
- vytvářet dashboard summary,

je nutná interní referenční měna. V aplikaci je touto měnou EUR.

### 5.2 Použitý postup

Servis `currency_conversion_service.py`:

- nejprve zkusí použít explicitní `FX Rate`,
- pokud není k dispozici, použije fallback kurzovní mapu.

### 5.3 Statistická interpretace

Tento krok není predikční model, ale transformační model dat. Má však přímý vliv na kvalitu všech navazujících statistik, protože:

- sjednocuje jednotky měření,
- dělá agregaci ekonomicky smysluplnou,
- snižuje riziko chybných meziměnových součtů.

## 6. Výpočet investovaného kapitálu a odhad volné hotovosti

### 6.1 Investovaný kapitál

Investovaný kapitál je v aplikaci odhadován z transakcí `CASH TOP-UP` a `CASH WITHDRAWAL`. Jeho význam není čistě statistický, ale slouží jako referenční základ pro:

- ROI,
- interpretaci portfoliových zisků,
- simulaci odvozených portfolií po rebalance.

### 6.2 Estimated free cash

Odhad volné hotovosti je počítán jako:

- cash top-up
- minus cash withdrawal
- minus buy
- plus sell
- minus fees
- plus dividends

### 6.3 Proč se jedná o odhad

Nejde o bankovně auditovaný zůstatek, ale o účetní rekonstrukci z importovaných transakcí. Statisticky je to deterministická transformace vstupu, nikoli stochastický model.

## 7. Cash-flow-adjusted výkonnost portfolia

### 7.1 Problém raw portfolio value

Syrová hodnota portfolia je ovlivněna dvěma odlišnými mechanismy:

1. tržním pohybem aktiv,
2. externími cash flow investora.

Pokud investor vloží velký objem nového kapitálu, hodnota portfolia skokově vzroste, aniž by to znamenalo investiční výkonnost.

### 7.2 Proč nestačí portfolio value

Pokud by byla predikce nebo vyhodnocení výkonnosti založena jen na portfolio value:

- model by zaměňoval vklady za trend,
- metriky výkonu by byly zkreslené,
- porovnání s benchmarky by bylo nekorektní.

### 7.3 TWR přístup v aplikaci

V `home.py` a zejména `predikce.py` je implementován cash-flow-adjusted TWR-like index.

Zjednodušená logika:

1. vezme se historická časová řada `portfolio_value`,
2. pro stejné datové body se sestaví externí cash flow,
3. denní výnos se počítá pouze z tržně očištěné změny:

`r_t = (V_t - CF_t) / V_{t-1} - 1`

nebo ekvivalentní konstrukcí, která odděluje externí tok od růstu hodnoty.

4. tyto výnosy se následně řetězí do TWR indexu.

### 7.4 Proč je TWR vhodný

Time-weighted return:

- omezuje vliv velikosti a načasování vkladů a výběrů,
- lépe reprezentuje investiční výkon samotné alokace,
- je vhodnější pro modelování budoucí výkonnosti.

### 7.5 Statistický dopad

Použití TWR zde není pouze účetní rozhodnutí, ale přímo statistická nutnost. Díky němu:

- modelovaná řada je interpretovatelnější,
- trend a volatilita odrážejí trh, ne chování investora,
- ARIMA/GARCH modely dostávají kvalitnější vstup.

## 8. Výnosové transformace

### 8.1 Jednoduché výnosy

Jednoduchý výnos je obvykle:

`r_t = P_t / P_{t-1} - 1`

Tento tvar je intuitivní a snadno interpretovatelný.

### 8.2 Logaritmické výnosy

Logaritmický výnos:

`g_t = ln(P_t / P_{t-1})`

### 8.3 Proč jsou log výnosy vhodné

V aplikaci se pro predikční část používají právě log returns, protože:

- jsou aditivní přes čas,
- bývají vhodnější pro modelování časových řad,
- usnadňují návrat z predikovaných výnosů zpět na cenovou trajektorii.

### 8.4 Převod zpět na cenovou trajektorii

Po predikci budoucích log returns se zpětně skládá price path:

`P_{t+h} = P_t * exp(sum(g_{t+1} ... g_{t+h}))`

To je implementováno ve funkcích typu `returns_to_price_path`, `logret_to_price_path` apod.

## 9. Rizikové metriky portfolia

### 9.1 Volatilita

Volatilita vyjadřuje rozptyl výnosů. V aplikaci reprezentuje základní míru rizika.

Její použití je odůvodněné tím, že:

- jde o standardní finanční metriku,
- je kompatibilní s mean-variance rámcem,
- je potřeba i pro Sharpe Ratio.

### 9.2 Maximum drawdown

Maximum drawdown měří největší pokles od předchozího maxima. Jde o velmi důležitou praktickou metriku, protože investor často vnímá riziko právě jako ztrátu od vrcholu.

Statisticky drawdown zachycuje:

- sekvenční charakter ztrát,
- nejhorší historickou epizodu,
- nelineární aspekt rizika, který variance sama nezachytí.

### 9.3 Sharpe Ratio

Sharpe Ratio je poměr výnosu k celkovému riziku. V aplikaci zůstává pod tímto originálním názvem i v české lokalizaci.

Jeho význam:

- normalizuje výkon o volatilitu,
- dovoluje porovnat efektivitu rizika mezi portfolii.

### 9.4 Sortino Ratio

Sortino Ratio používá downside volatilitu místo celkové volatility.

Je výhodné, protože:

- nepenalizuje pozitivní výkyvy,
- je investičně intuitivnější,
- doplňuje Sharpe Ratio o asymetričtější pohled na riziko.

## 10. Asset-level risk metriky

Kromě portfoliových metrik aplikace počítá i metriky po jednotlivých aktivech.

To je důležité pro:

- rozpoznání nejrizikovějších pozic,
- interpretaci koncentrace rizika,
- vstupní diagnostiku před rebalance.

Na úrovni aktiv se opět pracuje zejména s:

- hodnotou pozice,
- profitabilitou,
- volatilitou,
- podílem na portfoliu.

## 11. Benchmark normalization a srovnání

### 11.1 Proč benchmark

Bez benchmarku je výkon portfolia obtížně interpretovatelný. Uživatel může vědět, že portfolio rostlo, ale neví, zda rostlo lépe nebo hůře než širší trh.

### 11.2 Normalizace na společný základ

V dashboardu jsou benchmarky i portfolio indexovány od společného startu, typicky na 100. To umožňuje vizuálně i statisticky korektní porovnání.

### 11.3 Statistický význam

Indexace na společný základ:

- eliminuje rozdíl v absolutních cenových hladinách,
- převádí srovnání na relativní výkon,
- usnadňuje interpretaci investorovi.

## 12. Detekce sezónnosti

V predikční části existují dvě doplňkové techniky detekce sezónnosti:

- FFT-based přístup,
- ACF-based přístup.

### 12.1 FFT detekce

Fourierova transformace pomáhá odhalit dominantní periodické složky v časové řadě.

Vhodnost:

- umí najít periodickou strukturu i bez ruční specifikace periody,
- je užitečná jako pomocný signál pro potenciální SARIMA model.

### 12.2 ACF detekce

Autocorrelation function hledá významné peaky v autokorelaci.

Vhodnost:

- je klasickým nástrojem časových řad,
- dává přímou informaci o opakujících se závislostech.

### 12.3 Interpretace v aplikaci

Sezónnost se zde nebere dogmaticky. Slouží spíše jako pomocný indikátor, zda má smysl zvažovat SARIMA variantu.

## 13. Stacionarita a ADF test

### 13.1 Proč je stacionarita důležitá

ARIMA modely předpokládají práci se stacionární řadou nebo s řadou, kterou lze stacionarizovat diferencováním.

### 13.2 ADF test v aplikaci

Funkce `estimate_d_min_adf` postupně zkouší:

- `d = 0`
- `d = 1`
- `d = 2`

a hledá nejmenší diferenciaci, při níž ADF test zamítne jednotkový kořen.

### 13.3 Proč se tento krok používá

Tento postup:

- brání zbytečně vysokému differencování,
- pomáhá stabilizovat vstup do ARIMA,
- přidává model selection logice statistickou oporu.

## 14. Autokorelace a Ljung-Box test

### 14.1 Autokorelace

Autokorelace vyjadřuje závislost současné hodnoty na minulých hodnotách. Pro časové řady je to zásadní koncept, protože právě na této závislosti stojí ARIMA modely.

### 14.2 Ljung-Box test

Ljung-Box test v aplikaci slouží jako diagnostika reziduí. Ověřuje, zda v reziduích po odfitování modelu zůstává autokorelace.

### 14.3 Proč je důležitý

Dobrá predikční specifikace by měla z reziduí odstranit systematickou lineární strukturu. Pokud rezidua stále vykazují autokorelaci, model mean procesu je nedostatečný.

## 15. ARIMA modelování

### 15.1 Podstata modelu

ARIMA model kombinuje:

- autoregresní část,
- integrovanou část,
- moving average část.

Je vhodný pro:

- krátkodobé predikce,
- časové řady s autokorelační strukturou,
- situace, kdy nechceme nasazovat příliš komplexní modely.

### 15.2 Implementace v aplikaci

V `predikce.py` jsou použity:

- grid search přes kandidátní hodnoty `p` a `q`,
- odhad `d` přes ADF logiku,
- hodnocení přes RMSE na train/test splitu.

### 15.3 Proč je použit RMSE-based výběr

To je prakticky orientované rozhodnutí. Místo čistě informačních kritérií jako AIC/BIC je zde důležitá i out-of-sample chyba predikce.

### 15.4 Výhody ARIMA v tomto projektu

- relativně transparentní interpretace,
- akademická obhajitelnost,
- vhodnost pro menší až střední datové řady,
- rozumná kombinace s GARCH.

### 15.5 Omezení

- nezachycuje nelineární efekty,
- je citlivý na specifikaci,
- u finančních dat mívá omezenou predikční sílu v mean části.

## 16. SARIMA modelování

SARIMA rozšiřuje ARIMA o sezónní strukturu.

V této aplikaci je přítomna logika pro její použití, ale není to dominantní jádro. To je rozumné, protože finanční denní výnosy často nemají silnou a stabilní klasickou sezónnost.

Její přítomnost je nicméně metodicky cenná, protože ukazuje, že aplikace je připravena i na scénář, kdy by se opakující periodické vzorce ukázaly jako relevantní.

## 17. ARCH efekt a GARCH modelování

### 17.1 Proč ARIMA nestačí

ARIMA modeluje podmíněný střed. Finanční data ale často vykazují další jev:

- volatilita není konstantní,
- klastruje se v čase.

Proto je nutné oddělit:

- model mean procesu,
- model variance procesu.

### 17.2 Detekce ARCH efektu

V aplikaci se používá:

- Engle ARCH LM test,
- případně pomocné diagnostiky reziduí.

Pokud je ARCH efekt přítomen, je to signál, že:

- rezidua mají podmíněně proměnlivou volatilitu,
- variance sama nese predikovatelnou strukturu.

### 17.3 GARCH model

GARCH model používá minulou volatilitu a minulá kvadratická rezidua k odhadu budoucí podmíněné variance.

V aplikaci slouží pro:

- forecast sigma,
- konstrukci intervalových pásem nejistoty.

### 17.4 Proč je GARCH vhodný v aplikaci

Protože uživateli nestačí jen jedna predikovaná střední křivka. Je užitečné ukázat i:

- jaká je přibližná nejistota predikce,
- jak široké může být očekávané pásmo budoucího vývoje.

## 18. Konstrukce forecast pásem

Po odhadu mean procesu a volatility se z budoucích log returns a sigma skládají pásma nejistoty.

Typická logika:

- střední cesta = mean forecast,
- horní a dolní pásmo = mean ± k * sigma,
- poté převod na cenovou/hodnotovou trajektorii.

Tato pásma nejsou přesným “pravděpodobnostním intervalem reality”, ale praktickou vizualizací modelové nejistoty.

## 19. Predikce jednotlivého aktiva versus celého portfolia

### 19.1 Predikce aktiva

Predikce jednotlivého aktiva pracuje nad jeho vlastní cenovou řadou. Má smysl tehdy, když chceme:

- analyzovat konkrétní ticker,
- porovnat jeho historický a očekávaný trend,
- sledovat jeho individuální volatilitu.

### 19.2 Predikce portfolia

Predikce portfolia pracuje nad cash-flow-adjusted TWR indexem portfolia. To je metodicky jiná úloha než predikce jednoho aktiva, protože:

- portfolio je agregát více instrumentů,
- mění se jeho složení,
- do raw hodnoty zasahují externí cash flow.

## 20. Rebalancing – statistické a optimalizační procesy

Rebalancing není klasická inferenční statistika, ale využívá kvantitativní a optimalizační modely nad historickými výnosy.

### 20.1 Vstupní returns

Nejprve jsou z cen aktiv odvozeny historické returns. Ty tvoří základ pro:

- odhad průměrných výnosů,
- odhad kovarianční matice,
- scénáře ztrát.

### 20.2 Mean-Variance Optimization

#### Princip

Model používá:

- vektor očekávaných výnosů `mu`,
- kovarianční matici `Sigma`.

Cíl je maximalizovat užitek:

`mu^T w - lambda * w^T Sigma w`

#### Proč je použit

Jde o klasický základ portfoliové teorie. Je akademicky velmi důležitý a dobře obhajitelný.

#### Omezení

- citlivost na odhad očekávaných výnosů,
- citlivost na kovarianční matici,
- potenciálně nestabilní váhy.

### 20.3 Risk Parity

#### Princip

Risk Parity neusiluje o maximalizaci výnosu, ale o rovnoměrné rozložení rizikových příspěvků jednotlivých aktiv.

#### Proč je použit

- méně závisí na odhadu mean returns,
- bývá robustnější,
- lépe odpovídá konzervativnějšímu přístupu.

#### Statistický význam

Klíčová je zde role kovarianční struktury. Model implicitně pracuje s tím, jak se aktiva spolupohybují, a snaží se kontrolovat příspěvky k agregovanému riziku.

### 20.4 CVaR Optimization

#### Princip

CVaR se zaměřuje na očekávanou ztrátu za hranicí určitého kvantilu.

#### Proč je použit

Variance není ideální, když investora zajímají hlavně špatné scénáře. CVaR lépe vystihuje tail risk.

#### Statistický význam

CVaR je riziková míra citlivá na levou část rozdělení výnosů. Je proto vhodná tam, kde má uživatel větší averzi vůči extrémním ztrátám než vůči běžné volatilitě.

## 21. Diagnostika kvality modelů

V aplikaci se nepočítá pouze jeden model bez ověření. Používá se několik kroků diagnostiky:

- train/test split,
- RMSE hodnocení,
- ADF test,
- ACF,
- Ljung-Box,
- ARCH detekce.

To je velmi důležité, protože projekt tím neukazuje pouze “výslednou predikci”, ale i metodologickou opatrnost při výběru modelu.

## 22. Proč jsou použity právě tyto statistické procesy

Výběr metod je logický vzhledem k cíli aplikace:

### ARIMA

- klasický,
- dobře obhajitelný,
- vhodný pro akademické použití,
- interpretovatelný.

### GARCH

- přirozený doplněk k ARIMA u finančních dat,
- modeluje volatilitu,
- zlepšuje realistický charakter forecastu.

### TWR

- odděluje investiční výkon od cash flow investora,
- zlepšuje interpretaci i kvalitu vstupu pro predikci.

### Volatilita, drawdown, Sharpe, Sortino

- standardní investiční metriky,
- dobře srozumitelné,
- společně pokrývají více pohledů na riziko.

### Mean-Variance, Risk Parity, CVaR

- reprezentují tři různé filozofie alokace:
  - výnos-riziko kompromis,
  - rovnováha rizikových příspěvků,
  - ochrana proti tail risku.

## 23. Omezení použitých statistických procesů

Je důležité výslovně uvést, že žádná z metod není dokonalá.

### Omezení ARIMA/SARIMA

- závislost na minulosti,
- omezená schopnost zachytit strukturální zlomy,
- citlivost na délku a kvalitu dat.

### Omezení GARCH

- modeluje volatilitu podmíněně na minulosti,
- nemusí zachytit extrémní tržní události mimo historický vzor.

### Omezení TWR

- vyžaduje správné zachycení cash flow,
- při chybném importu může být zkreslen.

### Omezení Mean-Variance

- odhad mean returns bývá velmi nestabilní,
- malé změny vstupů mohou měnit optimální váhy.

### Omezení Risk Parity

- samo o sobě neoptimalizuje výnos,
- může preferovat defenzivnější struktury.

### Omezení CVaR

- je citlivé na empirický vzorek a odhad tail behavior,
- historická data nemusí reprezentovat budoucí extrémy.

## 24. Jak statistické procesy společně tvoří celek

Největší síla aplikace není v jediné metodě, ale v kombinaci více vrstev:

1. validace a očištění dat,
2. rekonstrukce historické hodnoty portfolia,
3. oddělení cash flow od výkonu,
4. výpočet základních a pokročilejších rizikových metrik,
5. statistická predikce střední hodnoty a volatility,
6. optimalizační návrh nového složení portfolia.

Tím vzniká souvislý analytický řetězec:

- od raw dat,
- přes statistické zpracování,
- až po rozhodovací podporu pro investora.

## 25. Shrnutí

Statistické procesy použité v aplikaci jsou zvoleny tak, aby:

- odpovídaly povaze finančních časových řad,
- byly akademicky obhajitelné,
- byly prakticky implementovatelné v reálné webové aplikaci,
- poskytovaly srozumitelné výsledky koncovému uživateli.

Jádrem statistické logiky aplikace jsou:

- konstrukce cash-flow-adjusted portfoliové výkonnosti,
- výpočet rizikových metrik,
- ARIMA-based modelování mean procesu,
- GARCH-based modelování volatility,
- optimalizační rebalance modely postavené nad historickými returns.

Právě tato kombinace vytváří z aplikace nejen vizualizační dashboard, ale kvantitativní analytický nástroj s jasným metodologickým základem.
