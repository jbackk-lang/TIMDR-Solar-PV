# TIMDR-Solar-PV

Detekcja degradacji, zabrudzenia, zacienienia i awarii inwertera w
instalacji fotowoltaicznej — na tym samym operatorze TIMDR
(fuse → twist/trend/anomalies/rhythm → fusion_score), którego
używają `TIMDR-Battery-Predict` i `TIMDR-Industrial-Predict`, więc
**dokłada się do reszty ekosystemu bez zmiany interfejsu wywołania**
(patrz sekcja "Podłączalność" niżej).

## Instalacja

```bash
pip install -r requirements.txt
```

## Szybki start

```bash
python -c "
from demo_scenarios import make_demo_data
from timdr_solar_fusion import TIMDRSolarFusion
from timdr_solar_predict import TIMDRSolarPredict

t, s = make_demo_data('long_term_degradation')
fusion = TIMDRSolarFusion()
E, PR = fusion.fuse(t, s['power'], s['poa_irradiance'], s['module_temp'], s['pdc0'])

predict = TIMDRSolarPredict()
print(predict.degradation_rate_per_year(t, E))
"

python api.py       # REST API + dashboard na http://127.0.0.1:5001
pytest -q           # 17 testow
```

Na Windows: `run.bat` instaluje zależności i uruchamia API/dashboard w
przeglądarce (bez uruchamiania testów — testy uruchom osobno przez
`pytest -q`).

Dashboard (`static/dashboard.html`, serwowany na `/`): wybór
scenariusza demo, wykresy E(t)/trendu, karty health score/tempa
degradacji/czasu do progu/fusion score/anomalii/rytmu, wgrywanie
własnego CSV (kolumny `power, poa_irradiance, module_temp`; `pdc0` i
`gamma_pdc` podaje się osobno w polach obok, bo to nie są kolumny
czasowe).

## Czym się różni od `TIMDR-Battery-Predict`

`TIMDRBatteryFusion.fuse()` nie miał prostego modelu fizycznego
łączącego 4 surowe czujniki (napięcie/prąd/temperatura/rezystancja) w
jedną wielkość, więc użyto ogólnej fuzji MAD z-score. Fotowoltaika MA
dobrze ugruntowany, standardowy w branży model fizyczny — **PVWatts DC**
(Dobos 2014, NREL/TP-6A20-62641, zaimplementowany w
[pvlib](https://pvlib-python.readthedocs.io/), referencyjnej bibliotece
NREL) — łączący naświetlenie POA i temperaturę modułu w oczekiwaną moc
"zdrowego" panelu. Zamiast fuzji MAD, `fuse()` liczy prawdziwy
**Performance Ratio** (przemysłowy standard): `PR = P_rzeczywiste /
P_oczekiwane(G, T)`. To rozdziela efekt pogody (usuwany przez
normalizację) od efektu stanu panelu (degradacja/brud/zacienienie/awaria
— to co zostaje w PR). `E = 1 - PR` (0 = zdrowy panel) jest podawane
dalej do DOKŁADNIE tych samych operatorów `twist/trend/anomalies/rhythm`
co w Battery-Predict — te same wagi w `fusion_score()`, celowo nie
przetunowane pod PV, żeby porównanie między domenami było uczciwe.

## Podłączalność do reszty ekosystemu

`TIMDRSolarFusion`/`TIMDRSolarPredict` mają dokładnie ten sam kształt
API co `TIMDRBatteryFusion`/`TIMDRBatteryPredict`:

```python
fuse(t, ...) -> (E, cos_dodatkowego)     # Battery: (E, Z) / Solar: (E, PR)
twist(t, E) -> (idx, z)
trend(t, E, window) -> (slopes, z)
anomalies(E) -> (idx, z)
rhythm(E) -> (periods, score)
fusion_score(twist_z, trend_z, anomaly_z, rhythm_score) -> float
```

Jedyna rzecz specyficzna dla domeny to argumenty `fuse()` (tu:
`power, poa_irradiance, module_temp, pdc0`, nie `voltage, current,
temperature, resistance`). Żeby użyć tego kodu w innym repo: skopiuj
`timdr_solar_fusion.py` + `timdr_solar_predict.py` z nagłówkiem
"ZWENDOROWANE" (ten sam wzorzec co reszta ekosystemu — patrz
`KATEGORIE.md` w `jbackk-lang.github.io`, sekcja "Powiązania kodu") —
reszta kodu wywołującego (np. `api.py`, dashboard) zmienia się tylko w
miejscu wywołania `fuse()`.

## Metodologia i uczciwe ograniczenia

**Kontrola pozytywna (zweryfikowana empirycznie):** scenariusz
`long_term_degradation` wstrzykuje znane tempo degradacji 1.5%/rok
(celowo powyżej mediany NREL 0.75%/rok, żeby kontrola była
jednoznaczna). Pierwszy przebieg `degradation_rate_per_year()` odzyskał
**1.497%/rok** (błąd względny 0.2%) — mechanizm działa, nie tylko
"nie crashuje".

**Uczciwy wynik negatywny (nie ukryty):** `anomalies()` (globalny
MAD z-score na E) **NIE wykrywa** trwałego skoku poziomu (scenariusz
`partial_shading_onset`) — bo po zdarzeniu "nowy poziom" staje się
częścią rozkładu tła, nie odstającą wartością względem NIEGO samego.
To ten sam problem klasy "kalibracja na oknie zawierającym już
zdarzenie", znany z `TIMDR-Earthquake-Core` (`HISTORIA_I_TESTY.md`).
Zamiast tego `trend()` (regresja krocząca) wykrywa PRZEJŚCIE między
poziomami jako lokalny wybuch nachylenia — **to jest właściwy operator
dla trwałego zacienienia w tym zestawie narzędzi, nie `anomalies()`**.
Test `test_partial_shading_onset_missed_by_anomalies_but_caught_by_trend`
dokumentuje to wprost, zamiast cicho zmieniać scenariusz na taki, który
"wygląda ładniej".

**Dane syntetyczne są fizycznie ugruntowane, nie dowolne:** geometria
słoneczna i model clearsky pochodzą z pvlib (ta sama biblioteka, której
używa NREL/przemysł) dla prawdziwej lokalizacji (Denver, CO). Temperatura
otoczenia jest STYLIZOWANYM modelem sezonowym (sinusoida dopasowana do
typowego klimatu Denver) — jawnie oznaczone jako nie-prawdziwy zapis
stacji pogodowej, w odróżnieniu od naświetlenia/geometrii słonecznej.

**Walidacja na PRAWDZIWYCH danych NREL PVDAQ: NIE WYKONANA w tym
środowisku.** `real_pvdaq_test.py` jest gotowy do uruchomienia (parsuje
format PVDAQ wg oficjalnej dokumentacji schematu), ale sandbox, w którym
ten kod powstał, miał dostęp sieciowy tylko do github.com i PyPI — sam
bucket danych PVDAQ (dziesiątki-setki MB na system, publiczny S3 bez
logowania) był niedostępny. Instrukcja pobrania i uruchomienia
samodzielnie: patrz nagłówek `real_pvdaq_test.py`. To jest jawnie
oznaczone jako otwarty punkt, nie ukryte za milczeniem — analogicznie do
tego, jak `TIMDR-Geometry-Formalism` oznaczył swój kod jako "napisany i
sprawdzony ręcznie, ale nieuruchomiony" w sesji bez dostępu do sandboxa.

## Ograniczenia (zwięźle)

- Model PVWatts zakłada stały `pdc0`/`gamma_pdc` — nie modeluje
  degradacji spektralnej ani zmian kąta padania (IAM) osobno; oba
  wchodzą w wypadkową PR, więc detektor widzi je jako "coś się zmienia",
  nie rozróżnia który mechanizm.
- `anomalies()` nie wykrywa trwałych skoków poziomu (patrz wyżej) — do
  tego służy `trend()`.
- Brak walidacji na realnych danych (patrz wyżej) — priorytet numer 1
  do zrobienia przed jakimkolwiek użyciem produkcyjnym.

## Rozszerzenie: analiza zespolona PV+bateria (`timdr_pv_battery_coupling.py`)

Odpowiedź na pytanie "co jak połączyć z Battery-Predict, jak zadziała
system na zaciemnienie" — zamiast dwóch osobnych systemów porównywanych
po fakcie, jeden wspólny potok: deficyt PV (`E_pv=1-PR`) napędza
dodatkowe obciążenie/zużycie baterii, które trafia do TEGO SAMEGO kanału
rezystancji w `TIMDRBatteryFusion.fuse()` (zwendorowana kopia w
`_vendor_timdr_battery_fusion.py`, ten sam wzorzec co
`TIMDR-Earthquake-Core/core/_vendor_timdr_meta_dynamics_core.py`).

**Dwa mechanizmy z literatury (research przed budową, nie zgadywanie):**

1. Zużycie cykliczne z kompensacji prądowej — zacienienie PV → bateria
   kompensuje większym prądem → większy skumulowany przepływ ładunku (Ah
   throughput) → rezystancja rośnie w przybliżeniu jak `R0+k*sqrt(Q_cum)`
   (power-law throughput/capacity-fade, ~0.5, z modeli starzenia cykli
   ogniw grafit-LFP — [Naumann et al., cycle aging graphite-LFP](https://www.sciencedirect.com/science/article/abs/pii/S0378775310021269),
   [przegląd capacity fade vs. resistance increase](https://www.sciencedirect.com/science/article/pii/S0378775325017574)).
   To NIE jest chwilowy spadek napięcia pod obciążeniem (odwracalny) —
   to skumulowany, nieodwracalny efekt.
2. Korozja od przeładowania — dłuższy czas w wysokim SOC → gazowanie/
   ciepło → wilgoć/kondensacja w obudowie → korozja styków → też wyższa
   rezystancja, niezależnie od (1) ([ryzyko przeładowania baterii](https://solarif.com/academy-article/what-is-the-risk-of-battery-overcharging-in-solar-systems/),
   [kondensacja w szczelnych obudowach elektroniki](https://www.yg-enclosure.com/article/waterproof-enclosure-for-solar-charge-controller-installation-guide.html)).

Obie hipotezy zbiegają się na TYM SAMYM obserwowalnym parametrze
(rezystancja) — dlatego moduł nie dodaje nowego kanału czujnika, tylko
modeluje obie przyczyny jako wkład do jednej już istniejącej wielkości.

**Uczciwy wynik testu (`test_pv_battery_coupling.py`, 10/10 testów,
pre-rejestrowane progi):** przy umiarkowanej częstości zacienienia (20
zdarzeń/2 lata) efekt jest REALNY, ale SKROMNY — końcowa rezystancja
wyższa o ~2% (nie dramatycznie), `max|trend_z|` wyższy o ~13%. Pierwsza
próba z globalną regresją liniową na całej historii dała mylącą względną
różnicę 140% — to był artefakt bliskiego zera mianownika, nie prawdziwy
efekt, i został odrzucony na rzecz miary absolutnej/`trend_z`. Osobny
test potwierdza też wcześniejszy wynik z tej sesji: POJEDYNCZE zdarzenie
zacienienia (jednorazowy skok prądu) NIE wywołuje fałszywego alarmu
baterii (ani `anomalies()`, ani `twist()`) — efekt ujawnia się dopiero
jako powolny `trend()` w horyzoncie miesięcy/lat, nie jako ostry alarm.

## Struktura

```
TIMDR-Solar-PV/
├── timdr_solar_fusion.py            — operator: fuse/twist/trend/anomalies/rhythm/fusion_score
├── timdr_solar_predict.py           — degradation_rate_per_year/time_to_threshold/health_score
├── timdr_pv_battery_coupling.py     — rozszerzenie: analiza zespolona PV+bateria (patrz wyzej)
├── _vendor_timdr_battery_fusion.py  — zwendorowana kopia TIMDRBatteryFusion (dla rozszerzenia)
├── demo_scenarios.py                — 5 syntetycznych scenariuszy (fizycznie ugruntowanych przez pvlib)
├── real_pvdaq_test.py               — walidacja na realnych danych NREL PVDAQ (do uruchomienia przez usera)
├── test_demo_scenarios.py           — 7 testow (kontrole pozytywne/negatywne)
├── test_pv_battery_coupling.py      — 10 testow rozszerzenia (kontrole pozytywne/negatywne)
├── api.py                           — REST API (Flask), serwuje dashboard na /
├── static/dashboard.html            — dashboard (wykresy, karty wynikow, wgrywanie CSV)
├── run.bat                          — Windows: instaluje zaleznosci, uruchamia API/dashboard
├── requirements.txt, LICENSE, .gitignore
```
