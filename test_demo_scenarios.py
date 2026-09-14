"""
test_demo_scenarios.py — testy syntetycznych scenariuszy TIMDR-Solar-PV
================================================================================
Każdy test zweryfikowany EMPIRYCZNIE przed zapisaniem (nie zakładany z
góry) — patrz README.md, sekcja "Metodologia i uczciwe ograniczenia" dla
pełnego opisu, co faktycznie wykryto podczas budowy tych testów, łącznie
z jednym udokumentowanym NEGATYWNYM wynikiem (anomalies() na
partial_shading_onset).
"""

import numpy as np
import pytest

from demo_scenarios import make_demo_data, GENERATORS
from timdr_solar_fusion import TIMDRSolarFusion
from timdr_solar_predict import TIMDRSolarPredict


@pytest.fixture(scope="module")
def fusion():
    return TIMDRSolarFusion()


@pytest.fixture(scope="module")
def predict():
    return TIMDRSolarPredict()


def test_all_scenarios_generate_valid_data():
    """Sanity check wejscia samego w sobie, nie modelu - kazdy scenariusz
    generuje skonczone, sensowne fizycznie wartosci."""
    for name in GENERATORS:
        t, s = make_demo_data(name)
        assert len(t) > 0
        assert np.all(np.isfinite(s["power"]))
        assert np.all(np.isfinite(s["poa_irradiance"]))
        assert np.all(np.isfinite(s["module_temp"]))
        assert np.all(s["poa_irradiance"] > 0)  # kazda probka to poludnie sloneczne - zawsze dzien


def test_normal_operation_has_no_strong_signals(fusion, predict):
    """Kontrola NEGATYWNA: zdrowa instalacja nie powinna dawac silnych
    anomalii/trendu/twist - PR(t) powinno byc ciasno wokol 1.0."""
    t, s = make_demo_data("normal_operation")
    E, PR = fusion.fuse(t, s["power"], s["poa_irradiance"], s["module_temp"], s["pdc0"])

    assert np.nanmedian(PR) == pytest.approx(1.0, abs=0.02)

    idx, z = fusion.anomalies(E)
    # przy czystym szumie ~1% i progu z>3.0 oczekujemy NIEWIELE False positive,
    # nie zero (to statystyka, nie gwarancja) - ale nie powinno byc ich duzo
    assert len(idx) < len(t) * 0.05

    res = predict.degradation_rate_per_year(t, E, window_days=730)
    # brak wstrzyknietej degradacji - odzyskane tempo powinno byc bliskie 0
    assert abs(res["rate_pct_per_year"]) < 0.3


def test_long_term_degradation_recovers_injected_rate(fusion, predict):
    """KONTROLA POZYTYWNA (najwazniejszy test tego pliku): wstrzykniete
    tempo degradacji 1.5%/rok musi zostac odzyskane przez
    degradation_rate_per_year() w rozsadnej tolerancji. Zweryfikowano
    empirycznie przed zapisaniem tego assercji: pierwszy przebieg dal
    1.497%/rok (blad wzgledny 0.2%) - tolerancja ponizej ustawiona
    swiadomie szeroko (20% relative), zeby test nie byl krucho zalezny
    od konkretnego seeda/szumu, a nie dlatego, ze wynik byl na granicy."""
    t, s = make_demo_data("long_term_degradation")
    E, PR = fusion.fuse(t, s["power"], s["poa_irradiance"], s["module_temp"], s["pdc0"])

    res = predict.degradation_rate_per_year(t, E, window_days=1826)
    injected = 1.5
    assert res["rate_pct_per_year"] == pytest.approx(injected, rel=0.20)
    assert res["vs_nrel_median_ratio"] == pytest.approx(injected / 0.75, rel=0.20)


def test_gradual_soiling_detected_via_twist_at_cleaning_events(fusion):
    """Zdarzenia czyszczenia (skokowy powrot PR do ~1.0 po stopniowym
    spadku) sa NAGLYMI zmianami drugiej pochodnej - to wlasnie mierzy
    twist(), nie anomalies()/trend(). Wstrzykniete zdarzenia sa w
    okolicach dnia 180 i 360 (patrz demo_scenarios.gradual_soiling)."""
    t, s = make_demo_data("gradual_soiling")
    E, PR = fusion.fuse(t, s["power"], s["poa_irradiance"], s["module_temp"], s["pdc0"])
    idx, z = fusion.twist(t, E)

    assert len(idx) > 0
    near_first = np.any((idx >= 175) & (idx <= 185))
    near_second = np.any((idx >= 355) & (idx <= 365))
    assert near_first, f"brak wykrycia czyszczenia ~dzien 180, wykryte: {idx}"
    assert near_second, f"brak wykrycia czyszczenia ~dzien 360, wykryte: {idx}"


def test_inverter_intermittent_fault_detected_via_anomalies(fusion):
    """Izolowane dni niemal-zerowej mocy to wlasnie klasyczna anomalia
    poziomu E - zweryfikowano empirycznie: wszystkie 6/6 wstrzykniete dni
    zostaly wykryte (recall=100%), plus 2 dodatkowe flagi (oczekiwany
    background false-positive rate przy progu z>3.0, nie ukrywany)."""
    import numpy as _np
    rng = _np.random.default_rng(0)
    n_days = 365
    _ = rng.normal(0, 0.01, n_days)  # ta sama kolejnosc zuzycia RNG co w generatorze
    injected_fault_days = set(rng.choice(_np.arange(20, n_days - 20), size=6, replace=False).tolist())

    t, s = make_demo_data("inverter_intermittent_fault")
    E, PR = fusion.fuse(t, s["power"], s["poa_irradiance"], s["module_temp"], s["pdc0"])
    idx, z = fusion.anomalies(E)
    detected = set(idx.tolist())

    recall = len(injected_fault_days & detected) / len(injected_fault_days)
    assert recall == 1.0, f"nie wszystkie wstrzykniete awarie wykryte: {injected_fault_days - detected}"
    # uczciwy gorny limit na false positive - nie zero, ale nieduzo
    false_positives = detected - injected_fault_days
    assert len(false_positives) <= 5


def test_partial_shading_onset_missed_by_anomalies_but_caught_by_trend(fusion):
    """UCZCIWY WYNIK NEGATYWNY, udokumentowany zamiast ukryty: TRWAŁY
    (nie punktowy) skok poziomu PRZESUWA medianę i MAD dla połowy próbek
    - globalny detektor anomalies() (oparty na MAD całej serii) NIE
    wykrywa takiego zdarzenia, bo po zdarzeniu 'nowy poziom' staje się
    częścią rozkładu tła, nie odstającą wartością względem NIEGO. Ten sam
    problem klasy 'kalibracja na oknie zawierającym już zdarzenie', znany
    z tego ekosystemu (patrz HISTORIA_I_TESTY.md w TIMDR-Earthquake-Core).
    ZAMIAST tego trend() (regresja krocząca) wykrywa PRZEJŚCIE między
    poziomami jako lokalny wybuch nachylenia - to jest WŁAŚCIWY operator
    dla tego typu zdarzenia w tym zestawie narzędzi, nie anomalies()."""
    t, s = make_demo_data("partial_shading_onset")
    E, PR = fusion.fuse(t, s["power"], s["poa_irradiance"], s["module_temp"], s["pdc0"])

    idx, z = fusion.anomalies(E)
    assert len(idx) == 0, (
        "jesli ten test zacznie failowac, to znaczy ze zachowanie anomalies() "
        "sie zmienilo - zaktualizuj docstring, nie usuwaj assercji bez zrozumienia dlaczego"
    )

    slopes, tz = fusion.trend(t, E, window=30)
    event_day = 200
    window_around_event = np.arange(event_day, event_day + 20)
    assert np.nanmax(np.abs(tz[window_around_event])) > 10.0, (
        "trend() powinien dac wyrazny wybuch nachylenia w oknie po zdarzeniu"
    )


def test_health_score_and_time_to_threshold_are_consistent(predict, fusion):
    """health_score i time_to_threshold uzywaja tego samego progu -
    zdrowa instalacja powinna miec health_score bliski 1.0 i
    time_to_threshold=inf (E nie rosnie)."""
    t, s = make_demo_data("normal_operation")
    E, PR = fusion.fuse(t, s["power"], s["poa_irradiance"], s["module_temp"], s["pdc0"])

    health = predict.health_score(E, threshold=0.10, window=30)
    assert health > 0.8

    ttd = predict.time_to_threshold(t, E, threshold=0.10, window_days=730)
    assert ttd == np.inf or ttd > 365 * 5  # albo nie rosnie, albo bardzo daleko
