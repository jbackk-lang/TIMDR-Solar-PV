"""
timdr_pv_battery_coupling.py — TIMDR PV+Bateria, analiza ZESPOLONA
======================================================================
Nie dwa niezależne systemy porównywane po fakcie, tylko jeden wspólny
model przepływu: PV (`TIMDRSolarFusion`) liczy deficyt mocy `E_pv=1-PR`,
który NAPĘDZA równoważne dodatkowe zużycie baterii (kompensacja
prądowa). To zużycie trafia do TEGO SAMEGO kanału rezystancji, którego
używa `TIMDRBatteryFusion.fuse()` — więc `E_bat` "widzi" wpływ PV bez
osobnego, niezależnie kalibrowanego "kanału alarmu od PV". To jest sens
"zespolonej" analizy: jeden potok danych, nie dwa potoki porównywane na
końcu.

## Dwa mechanizmy z literatury (zbiegają się na TEJ SAMEJ wielkości)

Historia pytań w tej sesji: (1) "co jak zacienienie PV wymusi kompensację
prądową baterii" → (2) hipoteza użytkownika "prawdopodobnie napięcie
wtórne z baterii powoduje zużycie" → (3) druga hipoteza użytkownika
"albo kondensacja w panelu [obudowie], bo przeładowane są baterie" → (4)
"zobacz u źródeł co jest prawdopodobną przyczyną i ten parametr musi
wpływać". Zweryfikowano w źródłach (patrz niżej) — obie hipotezy są
mechanistycznie realne, ale ŻADNA z nich to "napięcie" jako takie:

1. **Zużycie cykliczne z kompensacji prądowej.** Zacienienie PV → deficyt
   mocy → bateria rozładowuje się mocniej, żeby skompensować → większy
   skumulowany przepływ ładunku (Ah throughput). Capacity fade / wzrost
   rezystancji koreluje z throughput w przybliżeniu jako pierwiastek
   kwadratowy skumulowanego throughput — potwierdzone empirycznie w
   literaturze starzenia cykli ogniw grafit-LFP (dyfuzja, wzrost SEI).
   Model: `R(t) = R0 + k*sqrt(Q_cum(t))`. To NIE jest chwilowy spadek
   napięcia pod obciążeniem (IR-drop) — ten jest odwracalny i znika, gdy
   prąd wraca do normy. To co NIEODWRACALNE to powolny wzrost R w
   czasie, funkcja SKUMULOWANEGO przepływu ładunku, nie chwilowej
   wartości prądu/napięcia.
   Źródła: Naumann et al., "Analysis and modeling of cycle aging of a
   commercial LiFePO4/graphite cell" (cycle-life model, power-law
   throughput/DOD); przegląd capacity-fade (ScienceDirect,
   S0378775325017574) — "capacity fade follows a power law relationship
   with charge throughput, power law factor ~0.5", diffusion/SEI-growth.

2. **Korozja od przeładowania.** Dłuższy czas w wysokim SOC (np. bo
   kontroler doładowuje mocniej po dniach zacienienia, żeby nadrobić
   deficyt) → gazowanie/ciepło → wilgoć/kondensacja w obudowie → korozja
   styków → WIĘKSZA rezystancja PRZEJŚCIA (nie ogniwa samego, ale
   połączeń). To jest mechanizm ODDZIELNY od (1) — modelowany tu jako
   osobno oznaczony składnik ADDYTYWNY, nie zmieszany bez etykiety.
   Źródła: Unbound Solar / Solarif — przegrzanie, gazowanie i skrócona
   żywotność przy przeładowaniu; przewodniki po obudowach elektroniki
   solarnej — gwałtowne wahania temperatury dzień/noc powodują
   kondensację uwięzionej wilgoci w szczelnej obudowie, zalecenie:
   żelowy osuszacz / zawór oddychający IP68; korozja styków baterii —
   czyszczenie + smar dielektryczny jako standardowa przeciwdziałanie.

**Wspólny obserwowalny parametr: rezystancja.** Obie hipotezy —
"napięcie wtórne" użytkownika (w praktyce: efekt kompensacji prądowej,
mechanizm 1) i "kondensacja z przeładowania" (mechanizm 2) — zbiegają się
na TYM SAMYM kanale, który `TIMDRBatteryFusion.fuse()` już ma:
rezystancji wewnętrznej/przejścia. To dlatego ten moduł NIE dodaje
nowego kanału czujnika (np. "wilgotność obudowy") — modeluje obie
przyczyny jako wkład do jednej już istniejącej, mierzalnej wielkości.

## Uczciwe zastrzeżenie dot. metryki wykrywania (z pre-rejestrowanego testu)

Test na syntetycznych danych (patrz `test_pv_battery_coupling.py`)
ujawnił ważną pułapkę: globalna regresja liniowa na całej 2-letniej
historii `E_bat` (`TIMDRBatteryPredict.degradation_model()` z
`window=len(t)`) dała WZGLĘDNĄ różnicę 140% między ramieniem "często
zacienianym" (20 zdarzeń/2 lata) a kontrolnym — ale ABSOLUTNA różnica
końcowej rezystancji wyniosła tylko ~2% (0.157 vs 0.154). Duża względna
% różnica przy nachyleniu bliskim zera w mianowniku to klasyczny artefakt
— NIE jest raportowana tu jako główny wynik. Bardziej wiarygodny jest
`max|trend_z()|` (lokalny, okienkowy detektor): ~22.2 (zacieniana) vs
~19.7 (kontrolna), ~13% różnicy — mniejszy, ale bardziej wiarygodny
sygnał. WNIOSEK: przy umiarkowanej częstości zacienienia efekt jest
realny, ale SKROMNY — to narastające zjawisko wielomiesięczne/wieloletnie
(`trend()`), nie pojedynczy ostry alarm (`anomalies()`/`twist()`) — spójne
z wcześniejszym testem pojedynczego zdarzenia zacienienia (+15% prądu
przez 1 zdarzenie NIE wywołało żadnego alarmu baterii — ani anomalii,
ani skrętu — bo pojedynczy krok jest zbyt mały względem progów MAD-z
3.0/3.5 skalibrowanych na całej historii).

## Ograniczenia (jawnie, nie ukryte)

- Stałe `r0`/`k`/`corrosion_rate` są rzędu wielkości z literatury
  (kształt: pierwiastek z throughput), ale NIE skalibrowane do
  konkretnego typu ogniwa — do realnego użycia potrzeba dopasowania do
  danych pomiarowych własnego pakietu baterii.
- Mechanizm 2 (korozja/kondensacja) wymaga `soc_fraction(t)` jako wejścia
  — jeśli go nie ma, moduł działa z samym mechanizmem 1
  (`corrosion_rate=0.0`, jawny domyślny wyłącznik, nie milczące
  pominięcie).
- Nie modeluje realnej pojemności/SOC-dynamiki (brak pełnego modelu
  elektrochemicznego) — to jest model WARSTWY SPRZĘŻENIA (jak deficyt PV
  przekłada się na dodatkowe obciążenie baterii), nie zastępuje realnego
  BMS/modelu ogniwa.

## Podłączalność

`TIMDRPVBatteryCoupling` przyjmuje instancję `TIMDRBatteryFusion`
(zwendorowaną kopię w `_vendor_timdr_battery_fusion.py` tego repo) z
zewnątrz — nie tworzy jej sam — więc wywołujący kod (np. dashboard, API)
może użyć własnej instancji/wersji bez zmiany tego modułu.
"""

import numpy as np


def ah_throughput_cumulative(t_days, current):
    """Skumulowany przepływ ładunku [Ah] — trapezoidalna/schodkowa całka
    |current| dt, t_days w dniach (przeliczane na godziny)."""
    t_days = np.asarray(t_days, float)
    current = np.asarray(current, float)
    if len(t_days) == 0:
        return np.array([])
    dt_hours = np.diff(t_days, prepend=t_days[0]) * 24.0
    ah_increment = np.abs(current) * dt_hours
    return np.cumsum(ah_increment)


def cycle_wear_resistance(t_days, current, r0=0.05, k=0.0008):
    """Mechanizm 1: R(t) = r0 + k*sqrt(Q_cum(t)) — wzrost rezystancji z
    kumulacji przepływu ładunku (throughput), wykładnik 0.5 z literatury
    starzenia cykli (nie strojony pod ten projekt — patrz nagłówek modułu)."""
    q_cum = ah_throughput_cumulative(t_days, current)
    return r0 + k * np.sqrt(np.maximum(q_cum, 0.0))


def overcharge_corrosion_addon(t_days, soc_fraction, high_soc_threshold=0.95, corrosion_rate=0.0005):
    """Mechanizm 2: dodatkowy ADDYTYWNY wzrost R z czasu spędzonego
    powyżej progu wysokiego SOC (proxy przeładowania -> gazowanie ->
    wilgoć/kondensacja -> korozja styków). Zwraca przyrost R do DODANIA
    do mechanizmu 1, nie mnożenia — oba mechanizmy są niezależnymi,
    addytywnymi wkładami do tej samej wielkości fizycznej."""
    t_days = np.asarray(t_days, float)
    soc_fraction = np.asarray(soc_fraction, float)
    if len(t_days) == 0:
        return np.array([])
    dt_days = np.diff(t_days, prepend=t_days[0])
    high_soc_days = np.where(soc_fraction >= high_soc_threshold, dt_days, 0.0)
    return corrosion_rate * np.cumsum(high_soc_days)


def coupled_battery_current(t_days, current_baseline, pv_deficit, coupling_gain):
    """Sprzężenie: prąd = bazowy * (1 + coupling_gain * deficyt_PV).
    `pv_deficit` oczekiwany z TIMDRSolarFusion jako `E_pv = 1-PR`
    (przycinany do >=0 — ujemny deficyt, tj. panel lepszy niż model,
    nie zmniejsza obciążenia baterii w tym module)."""
    pv_deficit = np.clip(np.asarray(pv_deficit, float), 0.0, None)
    return np.asarray(current_baseline, float) * (1.0 + coupling_gain * pv_deficit)


class TIMDRPVBatteryCoupling:
    """Jeden wspólny obiekt łączący deficyt PV z modelem zużycia baterii,
    wg dwóch mechanizmów z literatury opisanych w nagłówku modułu."""

    def __init__(self, coupling_gain=0.6, r0=0.05, k=0.0008,
                 corrosion_rate=0.0, high_soc_threshold=0.95):
        self.coupling_gain = coupling_gain
        self.r0 = r0
        self.k = k
        self.corrosion_rate = corrosion_rate
        self.high_soc_threshold = high_soc_threshold

    def joint_battery_resistance(self, t_days, current_baseline, pv_deficit, soc_fraction=None):
        current = coupled_battery_current(t_days, current_baseline, pv_deficit, self.coupling_gain)
        resistance = cycle_wear_resistance(t_days, current, r0=self.r0, k=self.k)
        if soc_fraction is not None and self.corrosion_rate > 0:
            resistance = resistance + overcharge_corrosion_addon(
                t_days, soc_fraction, self.high_soc_threshold, self.corrosion_rate
            )
        return current, resistance

    def analyze(self, t_days, voltage, current_baseline, temperature, pv_deficit,
                battery_fusion, soc_fraction=None):
        """`battery_fusion`: instancja TIMDRBatteryFusion (np. z
        `_vendor_timdr_battery_fusion.py`), przekazana z zewnątrz — patrz
        sekcja Podłączalność w nagłówku modułu."""
        current, resistance = self.joint_battery_resistance(
            t_days, current_baseline, pv_deficit, soc_fraction
        )
        E, Z = battery_fusion.fuse(t_days, voltage, current, temperature, resistance)
        tw_idx, tw_z = battery_fusion.twist(t_days, E)
        tr_sl, tr_z = battery_fusion.trend(t_days, E, window=60)
        an_idx, an_z = battery_fusion.anomalies(E)
        return {
            "current": current,
            "resistance": resistance,
            "E": E,
            "twist_idx": tw_idx,
            "twist_z": tw_z,
            "trend_slopes": tr_sl,
            "trend_z": tr_z,
            "anomaly_idx": an_idx,
            "anomaly_z": an_z,
        }
