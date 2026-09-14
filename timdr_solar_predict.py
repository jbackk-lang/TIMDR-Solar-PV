"""
timdr_solar_predict.py — TIMDR Solar Predict
=================================================
Predykcyjne utrzymanie instalacji PV: tempo degradacji w %/rok
(bezpośrednio porównywalne z opublikowanym benchmarkiem branżowym),
czas do progu ostrzegawczego (analogiczny do TTF w TIMDR-Battery-Predict)
i wynik zdrowia (health_score) — na sygnale E(t)=1-PR(t) z
timdr_solar_fusion.py::TIMDRSolarFusion.fuse().

BENCHMARK ZEWNĘTRZNY (nie wymyślony, nie dostrojony pod te dane):
mediana tempa degradacji paneli krzemowych wg analizy NREL na ~2500
instalacjach komercyjnych/użytkowych to 0.75%/rok (Jordan i in., "PV
Degradation Methodology" / NREL 2024 analysis cytowana w materiałach
NREL PVDAQ). `degradation_rate_per_year()` zwraca wartość w tych samych
jednostkach właśnie po to, żeby dało się uczciwie porównać wynik
detektora z tą niezależną liczbą - nie żeby ją odtworzyć (to nie jest
kalibrowane pod 0.75, po prostu w tych samych jednostkach).
"""

import numpy as np

DAYS_PER_YEAR = 365.25
NREL_MEDIAN_DEGRADATION_PCT_PER_YEAR = 0.75  # Jordan et al./NREL, cytowane w PVDAQ - benchmark zewnetrzny


class TIMDRSolarPredict:
    def __init__(self, mad_scale=1.4826):
        self.mad_scale = mad_scale

    def degradation_rate_per_year(self, t_days, E, window_days=365):
        """
        Nachylenie E(t) (t w DNIACH) w ostatnim oknie `window_days`,
        przeliczone na %/rok (E=1-PR, wiec dE/dt>0 = spadek wydajnosci =
        realna degradacja/brud). Regresja centrowana (t0=t_win[0]) -
        ten sam fix numeryczny co TIMDRBatteryPredict.degradation_model,
        z tego samego, udokumentowanego juz w tym ekosystemie powodu
        (surowe epoch-timestampy daja katastrofalnie zle uwarunkowany
        lstsq).

        Zwraca dict {rate_pct_per_year, n_points, window_days_actual,
        vs_nrel_median_ratio} - ostatnie pole to rate/0.75, >1 znaczy
        szybsza degradacja niz mediana NREL, nie "zle" samo w sobie
        (mediana to mediana, polowa realnych instalacji jest nad nia).
        """
        t_days = np.asarray(t_days, float)
        E = np.asarray(E, float)
        valid = np.isfinite(E)
        if valid.sum() < 2:
            return {"rate_pct_per_year": None, "n_points": int(valid.sum()),
                    "window_days_actual": 0.0, "vs_nrel_median_ratio": None}

        t_valid = t_days[valid]
        E_valid = E[valid]
        cutoff = t_valid[-1] - window_days
        sel = t_valid >= cutoff
        t_win = t_valid[sel]
        E_win = E_valid[sel]
        if len(t_win) < 2:
            return {"rate_pct_per_year": None, "n_points": int(len(t_win)),
                    "window_days_actual": 0.0, "vs_nrel_median_ratio": None}

        t0 = t_win[0]
        t_rel = t_win - t0
        A = np.column_stack([t_rel, np.ones_like(t_rel)])
        a, b = np.linalg.lstsq(A, E_win, rcond=None)[0]

        rate_pct_per_year = float(a * DAYS_PER_YEAR * 100.0)
        ratio = (rate_pct_per_year / NREL_MEDIAN_DEGRADATION_PCT_PER_YEAR
                 if NREL_MEDIAN_DEGRADATION_PCT_PER_YEAR else None)

        return {
            "rate_pct_per_year": rate_pct_per_year,
            "n_points": int(len(t_win)),
            "window_days_actual": float(t_win[-1] - t_win[0]),
            "vs_nrel_median_ratio": ratio,
        }

    def time_to_threshold(self, t_days, E, threshold=0.10, window_days=365):
        """
        Analog TTF z TIMDR-Battery-Predict: ekstrapolacja LINIOWA
        (świadomie nie wykładnicza jak w battery - degradacja PV w
        skali lat jest w literaturze modelowana jako w przybliżeniu
        liniowa, nie wykładniczo przyspieszająca, patrz Jordan et al.)
        trendu E(t) do progu `threshold`. Zwraca dni OD OSTATNIEGO
        pomiaru (nie współrzędną t) - ten sam fix co
        TIMDRBatteryPredict.predict_failure. threshold=0.10 domyslnie =
        "10% instantaneous underperformance vs model" - prog
        ostrzegawczy do konserwacji (czyszczenie/przeglad), NIE prog
        gwarancyjny producenta (ten jest zwykle E~0.20 po 25 latach).
        """
        t_days = np.asarray(t_days, float)
        E = np.asarray(E, float)
        valid = np.isfinite(E)
        if valid.sum() < 2:
            return None

        t_valid = t_days[valid]
        E_valid = E[valid]
        cutoff = t_valid[-1] - window_days
        sel = t_valid >= cutoff
        t_win = t_valid[sel]
        E_win = E_valid[sel]
        if len(t_win) < 2:
            return None

        t0 = t_win[0]
        t_rel = t_win - t0
        A = np.column_stack([t_rel, np.ones_like(t_rel)])
        a, b = np.linalg.lstsq(A, E_win, rcond=None)[0]
        t_ref = t_valid[-1] - t0

        if a <= 0:
            return np.inf  # E nie rosnie (nie degraduje sie) w tym oknie
        ttd = (threshold - b) / a - t_ref
        return float(max(0.0, ttd))

    def health_score(self, E, threshold=0.10, window=30):
        """Identyczny wzorzec co TIMDRBatteryPredict.health_score():
        mediana OSTATNIEGO okna (nie cala historia - jeden stary skok
        nie 'zatruwa' wyniku na zawsze), porownana do tego samego progu
        co time_to_threshold."""
        E = np.asarray(E, float)
        valid = E[np.isfinite(E)]
        if valid.size == 0:
            return 1.0
        recent = valid[-window:]
        level = float(np.median(recent))
        score = np.clip(level / threshold, 0.0, 1.0) if threshold > 0 else 0.0
        return float(1.0 - score)
