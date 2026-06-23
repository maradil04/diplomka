# Stručná osnova teoretické části diplomové práce

## 1. Úvod do problematiky investičních portfolií

- co je investiční portfolio
- základní cíle investora
- vztah mezi výnosem, rizikem a diverzifikací
- význam sledování historické výkonnosti portfolia

## 2. Finanční data a jejich specifika

- charakter finančních časových řad
- ceny aktiv versus výnosy aktiv
- logaritmické a jednoduché výnosy
- nestacionarita finančních řad
- volatilita a její proměnlivost v čase

## 3. Měření výkonnosti portfolia

- absolutní výnos
- relativní výnos
- ROI
- anualizovaný výnos
- rozdíl mezi hodnotou portfolia a výkonností portfolia
- význam cash-flow-adjusted hodnocení
- TWR jako metoda očištění o externí vklady a výběry

## 4. Riziko portfolia a jeho měření

- pojem rizika ve financích
- volatilita jako základní míra rizika
- drawdown a maximální drawdown
- downside risk
- Sharpe Ratio
- Sortino Ratio
- rozdíl mezi celkovou a downside volatilitou

## 5. Teorie diverzifikace a alokace aktiv

- princip diverzifikace
- korelace mezi aktivy
- význam kovarianční matice
- vztah diverzifikace a snížení rizika portfolia

## 6. Modern Portfolio Theory

- Markowitzův model
- očekávaný výnos a variance
- efektivní hranice
- kompromis mezi výnosem a rizikem
- omezení klasického mean-variance přístupu

## 7. Alternativní přístupy k optimalizaci portfolia

- Risk Parity
- CVaR a tail risk
- porovnání variance-based a downside/tail-risk přístupů

## 8. Časové řady a jejich modelování

- definice časové řady
- trend, sezónnost, náhodná složka
- stacionarita
- diferencování
- autokorelace a parciální autokorelace

## 9. ARIMA modely

- základní princip AR, I, MA složek
- význam parametrů p, d, q
- stacionarita jako podmínka
- odhad modelu
- interpretace reziduí
- výhody a limity ARIMA ve financích

## 10. SARIMA a sezónnost

- kdy má smysl uvažovat sezónnost
- sezónní složka modelu
- parametry sezónního modelu
- omezení sezónních modelů pro finanční data

## 11. Testování vlastností časových řad a reziduí

- ADF test
- Ljung-Box test
- ARCH efekt
- význam diagnostiky reziduí

## 12. Heteroskedasticita

- podmíněná heteroskedasticita
- motivace pro GARCH modely

## 13. GARCH modely

- princip GARCH
- modelování podmíněné variance
- interpretace volatility forecastu
- využití GARCH spolu s ARIMA

## 14. Predikce portfolia

- rozdíl mezi predikcí hodnoty portfolia a predikcí výkonnosti
- problém externích cash flow
- nutnost normalizace výkonu portfolia
- návrat z predikovaných výnosů zpět na úroveň hodnoty portfolia

## 15. Rebalancing portfolia

- definice rebalancingu
- důvody pro rebalance
- výhody a nevýhody různých metod
- vztah rebalancingu a rizikového profilu investora

## 16. Praktické otázky implementace analytického systému

- kvalita vstupních dat
- validace a čištění dat
- práce s více měnami
- mapování tickerů
- interpretace výsledků pro uživatele

## 17. Omezení modelů a metod

- citlivost na kvalitu vstupních dat
- omezení historických dat pro budoucí predikci
- omezení klasických statistických modelů
- nejistota predikce
- rozdíl mezi modelem a realitou finančního trhu

## 18. Vazba teorie na praktickou aplikaci

- jak teorie vstupuje do dashboardu
- jak teorie vstupuje do predikce
- jak teorie vstupuje do rebalancingu
- jak uživatelská aplikace převádí statistické koncepty do praktického nástroje

