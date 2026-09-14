"""
timdr_solar_fusion.py — TIMDR Solar Fusion
=================================================
Fuzja czujników instalacji fotowoltaicznej (moc DC/AC, naświetlenie w
płaszczyźnie modułu POA, temperatura modułu) w jeden sygnał "stanu
zdrowia" E(t), plus standardowy zestaw detektorów TIMDR (twist, trend,
anomalie, rytm) na tym sygnale — TEN SAM interfejs co
TIMDR-Battery-Predict/timdr_battery_fusion.py (fuse/twist/trend/
anomalies/rhythm/fusion_score), żeby dało się to łatwo podłączyć do
tego samego "operatora" co reszta ekosystemu.

RÓŻNICA WOBEC TIMDR-Battery-Predict: tam `fuse()` nie miał modelu
fizycznego łączącego 4 surowe czujniki w jedną wielkość, więc użyto
ogólnej fuzji MAD z-score (odchylenie każdego czujnika od jego własnej
mediany). Tutaj fotowoltaika MA dobrze ugruntowany, standardowy w
branży model fizyczny (PVWatts DC, Dobos 2014, zaimplementowany w
pvlib — referencyjnej bibliotece NREL) łączący naświetlenie i
temperaturę modułu w oczekiwaną moc "zdrowego" panelu. Więc zamiast
fuzji MAD, `fuse()` liczy PRAWDZIWY Performance Ratio (PR) — przemysłowy
standard: PR = P_rzeczywiste / P_oczekiwane(G, T) — i to PR (nie
surowa moc) jest sygnałem stanu E(t)/1-PR(t) podawanym dalej do
twist/trend/anomalies/rhythm. To ROZDZIELA efekt pogody (naświetlenie,
temperatura — usuwane przez normalizację) od efektu stanu panelu
(degradacja, zabrudzenie, zacienienie, awaria — to co zostaje w PR).

Referencja modelu: Dobos, A. P. (2014). "PVWatts Version 5 Manual".
NREL/TP-6A20-62641. Implementacja: pvlib.pvsystem.pvwatts_dc().
"""

import numpy as np

try:
    from pvlib.pvsystem import pvwatts_dc
except ImportError:  # pvlib jest opcjonalna zaleznoscia tylko dla expected_power();
    pvwatts_dc = None  # reszta klasy (operatory na juz policzonym PR) dziala bez niej.


class TIMDRSolarFusion:
    def __init__(self, mad_scale=1.4826, irradiance_floor=50.0):
        """
        irradiance_floor: ponizej tego POA [W/m^2] PR jest niezdefiniowany
        (dzielenie przez ~0, o zmierzchu/switach szum czujnika dominuje) -
        te probki sa maskowane (NaN), nie wchodza do zadnego z operatorow
        ponizej. To NIE jest dostrajanie po fakcie - 50 W/m^2 to
        standardowy, branzowy prog "daytime" uzywany w analizie PV
        (patrz np. filtrowanie w NREL PVDAQ QA pipeline).
        """
        self.mad_scale = mad_scale
        self.irradiance_floor = irradiance_floor

    def _mad_z(self, x):
        x = np.asarray(x, float)
        mask = np.isfinite(x)
        if not np.any(mask):
            return np.full_like(x, np.nan)
        med = np.nanmedian(x)
        mad = np.nanmedian(np.abs(x[mask] - med)) * self.mad_scale
        z = np.full_like(x, np.nan)
        if mad == 0:
            span = np.nanmax(x) - np.nanmin(x)
            if span == 0:
                z[mask] = 0.0
                return z
            z[mask] = (x[mask] - med) / (span / 4.0)
            return z
        z[mask] = (x[mask] - med) / mad
        return z

    def expected_power(self, poa_irradiance, module_temp, pdc0, gamma_pdc=-0.004):
        """Oczekiwana moc DC 'zdrowego' panelu wg modelu PVWatts (Dobos 2014).
        pdc0: nominalna moc DC w warunkach STC [W]. gamma_pdc: wspolczynnik
        temperaturowy mocy [1/degC] (domyslnie -0.004, typowe dla c-Si)."""
        if pvwatts_dc is None:
            raise ImportError("pvlib nie jest zainstalowane - wymagane dla expected_power(). pip install pvlib")
        return pvwatts_dc(np.asarray(poa_irradiance, float), np.asarray(module_temp, float),
                            pdc0, gamma_pdc)

    def fuse(self, t, power, poa_irradiance, module_temp, pdc0, gamma_pdc=-0.004):
        """
        Zwraca (E, PR):
          PR  - Performance Ratio = P_rzeczywiste / P_oczekiwane(G,T), maskowany
                NaN dla probek ponizej irradiance_floor (noc/zmierzch).
          E   - "sygnal stanu" = 1 - PR, wiec E=0 to idealnie zdrowy panel,
                E>0 to niedobor (degradacja/brud/zacienienie/awaria),
                E<0 to NADWYZKA wzgledem modelu (np. zle skalibrowany pdc0,
                albo czujnik irradiancji zacieniony wczesniej niz panel -
                warte zgloszenia, nie tylko odfiltrowania).
        Ten sam ksztalt zwrotki co TIMDRBatteryFusion.fuse() (E, Z) -
        E podajesz dalej do twist/trend/anomalies/rhythm bez zmian.
        """
        t = np.asarray(t, float)
        power = np.asarray(power, float)
        poa = np.asarray(poa_irradiance, float)
        temp = np.asarray(module_temp, float)

        expected = self.expected_power(poa, temp, pdc0, gamma_pdc)
        PR = np.full_like(power, np.nan, dtype=float)
        daytime = poa >= self.irradiance_floor
        with np.errstate(divide="ignore", invalid="ignore"):
            PR[daytime] = power[daytime] / expected[daytime]

        E = 1.0 - PR
        return E, PR

    def twist(self, t, E):
        """Identyczne jak TIMDRBatteryFusion.twist(): druga pochodna E
        (przyspieszenie zmiany) powyzej progu MAD-z = nagle zdarzenie
        (np. zacienienie chmura, wylaczenie inwertera). NaN (noc) w E
        sa ignorowane przy liczeniu gradientu przez interpolacje liniowa
        po probkach dziennych - patrz _fill_daytime_gaps()."""
        t = np.asarray(t, float)
        E = np.asarray(E, float)
        E_filled, valid_mask = self._fill_daytime_gaps(t, E)
        if valid_mask.sum() < 3:
            return np.array([], int), np.full_like(E, np.nan)
        dE = np.gradient(E_filled, t)
        ddE = np.gradient(dE, t)
        z_valid = self._mad_z(ddE[valid_mask])
        z = np.full_like(E, np.nan)
        z[valid_mask] = z_valid
        idx = np.where(np.abs(z) > 3.5)[0]
        return idx, z

    def trend(self, t, E, window=30):
        """Identyczne jak TIMDRBatteryFusion.trend(): krocząca regresja
        liniowa E~t w oknie `window` PRÓBEK DZIENNYCH (nie surowych
        indeksow - noc jest pomijana). Nachylenie > 0 = E rosnie =
        panel traci wydajnosc wzgledem modelu (degradacja/brud) -
        to jest wlasnie sygnal 'tempo degradacji' w %/rok, patrz
        timdr_solar_predict.py::degradation_rate_per_year()."""
        t = np.asarray(t, float)
        E = np.asarray(E, float)
        n = len(t)
        slopes = np.full_like(E, np.nan)
        valid_idx = np.where(np.isfinite(E))[0]
        if len(valid_idx) < 2:
            return slopes, np.full_like(slopes, np.nan)
        for k, i in enumerate(valid_idx):
            j0 = max(0, k - window + 1)
            sel = valid_idx[j0:k + 1]
            tt = t[sel]
            ee = E[sel]
            if len(tt) < 2:
                continue
            A = np.column_stack([tt, np.ones_like(tt)])
            a, b = np.linalg.lstsq(A, ee, rcond=None)[0]
            slopes[i] = a
        z = np.full_like(slopes, np.nan)
        z[valid_idx] = self._mad_z(slopes[valid_idx])
        return slopes, z

    def anomalies(self, E):
        """Identyczne jak TIMDRBatteryFusion.anomalies(): |MAD z-score(E)| > 3."""
        E = np.asarray(E, float)
        z = self._mad_z(E)
        idx = np.where(np.abs(z) > 3.0)[0]
        return idx, z

    def rhythm(self, E, max_lag=48, power_thresh=0.4):
        """Identyczne jak TIMDRBatteryFusion.rhythm() (pelny detrend +
        tylko lokalne maksima autokorelacji), zastosowane do probek
        DZIENNYCH E (noc odfiltrowana przed wywolaniem, patrz
        _fill_daytime_gaps). Dla PV rytm dobowy jest USUNIETY juz przez
        maskowanie nocy i normalizacje PR wzgledem naswietlenia - jesli
        cokolwiek periodycznego zostaje w PR, to podejrzany artefakt
        (np. cykl czyszczenia szyby, sezonowy kat padania nie w pelni
        skorygowany przez model), a nie sama fizyka dnia/nocy."""
        E = np.asarray(E, float)
        E = E[np.isfinite(E)]
        n = len(E)
        if n < 3:
            return [], np.nan

        t_idx = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(t_idx, E, 1)
        E = E - (slope * t_idx + intercept)

        max_lag = min(max_lag, n - 1)
        ac = np.zeros(max_lag + 1)
        for lag in range(max_lag + 1):
            if lag == 0:
                ac[lag] = np.dot(E, E) / n
            else:
                overlap = n - lag
                if overlap <= 0:
                    break
                ac[lag] = np.dot(E[:-lag], E[lag:]) / overlap

        if ac[0] == 0:
            return [], 0.0
        ac /= ac[0]

        peaks = [
            (i, float(ac[i])) for i in range(1, len(ac) - 1)
            if ac[i] > ac[i - 1] and ac[i] > ac[i + 1] and ac[i] >= power_thresh
        ]
        if not peaks:
            return [], 0.0
        score = max(p for _, p in peaks)
        return [p for p, _ in peaks], score

    def fusion_score(self, twist_z, trend_z, anomaly_z, rhythm_score):
        """Identyczne wagi jak TIMDRBatteryFusion.fusion_score() - NIE
        przetunowane pod PV, celowo, zeby porownanie miedzy domenami
        bylo uczciwe (te same wagi = ten sam 'operator', inna fizyka
        wejsciowa)."""
        def safe_nanmax_abs(x):
            x = np.asarray(x, float)
            x = x[np.isfinite(x)]
            return float(np.max(np.abs(x))) if x.size else 0.0

        r = rhythm_score if np.isfinite(rhythm_score) else 0.0
        return float(
            0.4 * safe_nanmax_abs(twist_z) +
            0.3 * safe_nanmax_abs(trend_z) +
            0.2 * safe_nanmax_abs(anomaly_z) +
            0.1 * r
        )

    @staticmethod
    def _fill_daytime_gaps(t, E):
        """Zwraca (E_filled, valid_mask) - E z NaN (noc) zastapionymi
        interpolacja liniowa MIEDZY probkami dziennymi (potrzebne tylko
        do liczenia gradientu w twist(); anomalies/trend/rhythm dzialaja
        na samych probkach dziennych bez interpolacji)."""
        t = np.asarray(t, float)
        E = np.asarray(E, float)
        valid = np.isfinite(E)
        if valid.sum() < 2:
            return E.copy(), valid
        E_filled = E.copy()
        nan_idx = np.where(~valid)[0]
        if len(nan_idx):
            E_filled[nan_idx] = np.interp(t[nan_idx], t[valid], E[valid])
        return E_filled, valid
