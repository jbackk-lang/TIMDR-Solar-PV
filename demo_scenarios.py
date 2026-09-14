"""
demo_scenarios.py — syntetyczne zestawy danych demo dla TIMDR-Solar-PV
================================================================================
5 scenariuszy dla instalacji fotowoltaicznej — każdy fizycznie ugruntowany
przez pvlib (NREL): naświetlenie z modelu clearsky + geometria słoneczna dla
prawdziwej lokalizacji, temperatura modułu z modelu Faimana, oczekiwana moc
zdrowego panelu z modelu PVWatts DC (Dobos 2014). Defekty (degradacja/
zabrudzenie/zacienienie/awaria) są wstrzykiwane jako MNOŻNIK/OFFSET na tej
fizycznie poprawnej bazie, nie na dowolnym szumie.

UWAGA O REALIZMIE: geometria słoneczna i model clearsky SĄ realną fizyką
(ta sama biblioteka, której używa NREL/przemysł). Temperatura otoczenia
jest STYLIZOWANYM modelem sezonowym (sinusoida dopasowana do typowego
klimatu Denver, CO — nie prawdziwym zapisem stacji pogodowej) — jawnie
oznaczone, żeby nie sugerować czegoś więcej niż to jest. Do walidacji na
PRAWDZIWYCH danych (nie stylizowanych) patrz real_pvdaq_test.py.

Próbkowanie: jedna próbka na dzień o **lokalnym południu słonecznym**
(nie co godzinę) — degradacja/soiling działają w skali miesięcy-lat, więc
gęstsze próbkowanie tylko zwiększa czas obliczeń bez dodawania sygnału.
"""

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location
from pvlib.irradiance import get_total_irradiance
from pvlib.temperature import faiman
from pvlib.pvsystem import pvwatts_dc

SCENARIOS = {
    "normal_operation": "Zdrowa praca — 2 lata, brak degradacji/zdarzeń, tylko szum czujnika",
    "gradual_soiling": "Stopniowe zabrudzenie — piłokształtny spadek PR przez 6 miesięcy + czyszczenie (trend + twist przy czyszczeniu)",
    "partial_shading_onset": "Nowe zacienienie (np. wzrost drzewa) — nagły, TRWAŁY spadek PR w jednym momencie (anomalia progowa)",
    "inverter_intermittent_fault": "Przerywana awaria inwertera — rzadkie, izolowane dni z niemal zerową mocą mimo słońca (anomalie punktowe)",
    "long_term_degradation": "Długoterminowa degradacja — 5 lat, wstrzyknięte tempo 1.5%/rok (KONTROLA POZYTYWNA dla degradation_rate_per_year)",
}

DEFAULT_THRESHOLDS = {
    "normal_operation": 0.10,
    "gradual_soiling": 0.10,
    "partial_shading_onset": 0.10,
    "inverter_intermittent_fault": 0.10,
    "long_term_degradation": 0.10,
}

# Wspolne parametry lokalizacji/systemu dla wszystkich scenariuszy
_LOCATION = Location(39.7392, -104.9903, tz="America/Denver", altitude=1609, name="Denver, CO (demo)")
_SURFACE_TILT = 30.0
_SURFACE_AZIMUTH = 180.0
_PDC0 = 5000.0       # W, moc nominalna STC
_GAMMA_PDC = -0.004  # 1/degC, typowe dla c-Si


def _seasonal_ambient_temp(day_of_year, rng):
    """Stylizowany model sezonowy temperatury otoczenia dla Denver, CO -
    NIE prawdziwy zapis stacji (patrz docstring modulu). Min ok. -2 degC
    (styczen), max ok. 23 degC (lipiec), plus szum dobowy."""
    seasonal = 10.5 + 12.5 * np.sin(2 * np.pi * (day_of_year - 100) / 365.25)
    return seasonal + rng.normal(0, 2.0, size=np.shape(day_of_year))


def _solar_noon_series(n_days, start="2020-01-01"):
    """Zwraca (t_days, poa_healthy, temp_cell_healthy, expected_power) dla
    n_days kolejnych dni, po jednej probce w lokalnym poludniu slonecznym,
    fizycznie policzone przez pvlib (clearsky + geometria + Faiman + PVWatts)."""
    dates = pd.date_range(start, periods=n_days, freq="D", tz=_LOCATION.tz)
    # poludnie sloneczne per dzien z pvlib (nie zegarowe 12:00)
    solar_noon_times = []
    for d in dates:
        day_times = pd.date_range(d, d + pd.Timedelta(hours=23, minutes=59), freq="10min", tz=_LOCATION.tz)
        solpos = _LOCATION.get_solarposition(day_times)
        noon_idx = solpos["zenith"].idxmin()
        solar_noon_times.append(noon_idx)
    times = pd.DatetimeIndex(solar_noon_times)

    cs = _LOCATION.get_clearsky(times, model="ineichen")
    solpos = _LOCATION.get_solarposition(times)

    poa = get_total_irradiance(
        _SURFACE_TILT, _SURFACE_AZIMUTH,
        solpos["zenith"], solpos["azimuth"],
        cs["dni"], cs["ghi"], cs["dhi"],
    )["poa_global"].to_numpy()

    doy = times.dayofyear.to_numpy()
    rng_temp = np.random.default_rng(12345)  # ambient temp ma wlasny, staly seed - niezalezny od seed scenariusza
    temp_air = _seasonal_ambient_temp(doy, rng_temp)
    temp_cell = faiman(poa, temp_air, wind_speed=2.0)

    expected_power = pvwatts_dc(poa, temp_cell, _PDC0, _GAMMA_PDC)
    t_days = np.arange(n_days, dtype=float)
    return t_days, poa, temp_cell, expected_power


def normal_operation(seed=0, n_days=730):
    """Zdrowa instalacja: rzeczywista moc = oczekiwana * (1 + szum czujnika
    ~1%). Brak trendu, brak zdarzen - PR(t) powinno oscylowac ciasno
    wokol 1.0 bez wykrytych anomalii/trendu/twist."""
    rng = np.random.default_rng(seed)
    t, poa, temp_cell, expected = _solar_noon_series(n_days)
    power = expected * (1.0 + rng.normal(0, 0.01, n_days))
    return t, {"power": power, "poa_irradiance": poa, "module_temp": temp_cell, "pdc0": _PDC0}


def gradual_soiling(seed=0, n_days=545):
    """Pilokształtny wzorzec typowy dla zabrudzenia: PR spada liniowo od
    1.0 do ok. 0.90 przez 180 dni (kurz osiada), potem SKOKOWY powrot do
    ~0.995 (deszcz/czyszczenie), i tak dwa razy (360 dni), plus 185 dni
    zdrowej pracy na koncu. Test dla trend() (w kazdym segmencie spadku)
    i twist() (przy kazdym czyszczeniu)."""
    rng = np.random.default_rng(seed)
    t, poa, temp_cell, expected = _solar_noon_series(n_days)

    cycle = 180
    n_cycles = 2
    factor = np.ones(n_days)
    for c in range(n_cycles):
        start = c * cycle
        end = min(start + cycle, n_days)
        length = end - start
        factor[start:end] = 1.0 - 0.10 * (np.arange(length) / cycle)
    tail_start = n_cycles * cycle
    factor[tail_start:] = 1.0 - rng.normal(0, 0.003, n_days - tail_start)  # "czyste" po ostatnim myciu

    power = expected * factor * (1.0 + rng.normal(0, 0.01, n_days))
    return t, {"power": power, "poa_irradiance": poa, "module_temp": temp_cell, "pdc0": _PDC0}


def partial_shading_onset(seed=0, n_days=400):
    """200 dni zdrowej pracy, potem TRWAŁY spadek PR o 15% od dnia 200
    (np. sąsiedni budynek/drzewo zaczyna rzucać cień na część stringa) -
    zostaje do końca serii, nie wraca. Test dla anomalies() (poziom
    przesuwa się trwale poza pasmo MAD wokół WCZEŚNIEJSZEJ mediany)."""
    rng = np.random.default_rng(seed)
    t, poa, temp_cell, expected = _solar_noon_series(n_days)
    event_day = 200
    factor = np.ones(n_days)
    factor[event_day:] = 0.85
    power = expected * factor * (1.0 + rng.normal(0, 0.01, n_days))
    return t, {"power": power, "poa_irradiance": poa, "module_temp": temp_cell, "pdc0": _PDC0}


def inverter_intermittent_fault(seed=0, n_days=365, n_faults=6):
    """Rok pracy, w losowe dni (nie na brzegach serii) inwerter "gubi"
    string - moc spada do ~5% oczekiwanej na TEN JEDEN dzien, nastepnego
    dnia wraca do normy. Test dla anomalies() jako izolowanych punktow,
    NIE trend() (brak trwalej zmiany poziomu)."""
    rng = np.random.default_rng(seed)
    t, poa, temp_cell, expected = _solar_noon_series(n_days)
    factor = np.ones(n_days) + rng.normal(0, 0.01, n_days)
    fault_days = rng.choice(np.arange(20, n_days - 20), size=n_faults, replace=False)
    factor[fault_days] = 0.05
    power = expected * factor
    return t, {"power": power, "poa_irradiance": poa, "module_temp": temp_cell, "pdc0": _PDC0}


def long_term_degradation(seed=0, n_days=1826, injected_rate_pct_per_year=1.5):
    """5 lat (1826 dni), rzeczywista moc = oczekiwana * (1 - r*t) gdzie r
    odpowiada WSTRZYKNIĘTEMU tempu degradacji `injected_rate_pct_per_year`
    (domyślnie 1.5%/rok - CELOWO powyżej mediany NREL 0.75%/rok, żeby
    kontrola pozytywna była jednoznaczna, nie na granicy szumu).
    KONTROLA POZYTYWNA: test_demo_scenarios.py sprawdza, że
    degradation_rate_per_year() odzyskuje ten wstrzyknięty procent w
    granicach rozsądnej tolerancji."""
    rng = np.random.default_rng(seed)
    t, poa, temp_cell, expected = _solar_noon_series(n_days)
    yearly_rate = injected_rate_pct_per_year / 100.0
    factor = 1.0 - yearly_rate * (t / 365.25)
    power = expected * factor * (1.0 + rng.normal(0, 0.01, n_days))
    return t, {"power": power, "poa_irradiance": poa, "module_temp": temp_cell, "pdc0": _PDC0}


GENERATORS = {
    "normal_operation": normal_operation,
    "gradual_soiling": gradual_soiling,
    "partial_shading_onset": partial_shading_onset,
    "inverter_intermittent_fault": inverter_intermittent_fault,
    "long_term_degradation": long_term_degradation,
}


def make_demo_data(scenario="normal_operation", seed=0):
    if scenario not in GENERATORS:
        raise ValueError(f"Nieznany scenariusz '{scenario}'. Dostepne: {list(GENERATORS)}")
    return GENERATORS[scenario](seed=seed)
