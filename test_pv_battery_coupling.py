"""
test_pv_battery_coupling.py — testy timdr_pv_battery_coupling.py

Zawiera pre-rejestrowany eksperyment sprzężenia PV+bateria (progi ustalone
PRZED uruchomieniem, patrz docstring w test_shading_frequency_increases_
battery_wear_trend) oraz kontrolę negatywną, kontrolę jednostkowego
zdarzenia (regres poprzedniego testu z sesji), i testy jednostkowe
funkcji pomocniczych.
"""

import numpy as np
import pytest

from _vendor_timdr_battery_fusion import TIMDRBatteryFusion
from timdr_pv_battery_coupling import (
    TIMDRPVBatteryCoupling,
    ah_throughput_cumulative,
    cycle_wear_resistance,
    overcharge_corrosion_addon,
    coupled_battery_current,
)


def test_ah_throughput_cumulative_constant_current():
    """Prad stale rowny 1A przez 10 dni (24h/dzien). Pierwsza probka ma
    zerowy uplyw czasu (dt_hours[0]=0 przez prepend=t[0]), wiec q[0]=0;
    po 9 pelnych krokach dobowych q[-1] = 9*24 = 216 Ah."""
    t = np.arange(10, dtype=float)
    current = np.ones(10)
    q = ah_throughput_cumulative(t, current)
    assert q[0] == pytest.approx(0.0, abs=1e-9)
    assert q[-1] == pytest.approx(216.0, rel=1e-6)


def test_ah_throughput_cumulative_is_monotonic_for_nonzero_current():
    t = np.arange(50, dtype=float)
    rng = np.random.default_rng(0)
    current = 1.0 + 0.1 * rng.standard_normal(50)
    q = ah_throughput_cumulative(t, current)
    assert np.all(np.diff(q) >= 0)


def test_cycle_wear_resistance_increases_with_more_throughput():
    """Wiecej pradu (wiecej throughput) -> wyzsza koncowa rezystancja,
    przy tych samych r0/k."""
    t = np.arange(100, dtype=float)
    low_current = np.full(100, 0.5)
    high_current = np.full(100, 2.0)
    r_low = cycle_wear_resistance(t, low_current)
    r_high = cycle_wear_resistance(t, high_current)
    assert r_high[-1] > r_low[-1]
    assert r_low[0] == pytest.approx(r_high[0])  # ten sam punkt startowy r0


def test_overcharge_corrosion_addon_zero_when_below_threshold():
    t = np.arange(30, dtype=float)
    soc = np.full(30, 0.5)  # nigdy nie osiaga progu 0.95
    addon = overcharge_corrosion_addon(t, soc, high_soc_threshold=0.95)
    assert np.all(addon == 0.0)


def test_overcharge_corrosion_addon_accumulates_above_threshold():
    t = np.arange(30, dtype=float)
    soc = np.full(30, 0.98)  # zawsze powyzej progu
    addon = overcharge_corrosion_addon(t, soc, high_soc_threshold=0.95, corrosion_rate=0.001)
    assert addon[-1] > addon[0]
    assert np.all(np.diff(addon) >= 0)


def test_coupled_current_equals_baseline_when_no_pv_deficit():
    t = np.arange(10, dtype=float)
    baseline = np.full(10, 1.0)
    deficit = np.zeros(10)
    current = coupled_battery_current(t, baseline, deficit, coupling_gain=0.6)
    assert np.allclose(current, baseline)


def test_coupled_current_increases_with_pv_deficit():
    t = np.arange(10, dtype=float)
    baseline = np.full(10, 1.0)
    deficit = np.full(10, 0.4)
    current = coupled_battery_current(t, baseline, deficit, coupling_gain=0.6)
    assert np.allclose(current, 1.0 * (1 + 0.6 * 0.4))


# --- Pre-rejestrowany eksperyment (progi ustalone PRZED uruchomieniem) ---

N_DAYS = 730  # 2 lata


def _make_pv_deficit(n, n_events, event_len=10, depth=0.4, seed=7):
    rng = np.random.default_rng(seed)
    deficit = np.zeros(n)
    if n_events > 0:
        starts = rng.choice(np.arange(0, n - event_len), size=n_events, replace=False)
        for s in starts:
            deficit[s:s + event_len] = depth
    return deficit


def _run_arm(n_events, coupling_gain, seed=11):
    days = np.arange(N_DAYS, dtype=float)
    pv_deficit = _make_pv_deficit(N_DAYS, n_events)
    rng = np.random.default_rng(seed)
    current_baseline = np.abs(1.0 + 0.3 * np.sin(2 * np.pi * days) + rng.normal(0, 0.02, N_DAYS))

    coupling = TIMDRPVBatteryCoupling(coupling_gain=coupling_gain, r0=0.05, k=0.0008)
    current, resistance = coupling.joint_battery_resistance(days, current_baseline, pv_deficit)

    voltage = 3.7 - 0.02 * (current - 1.0) + rng.normal(0, 0.01, N_DAYS)
    temperature = 25.0 + 1.0 * (current - 1.0) + rng.normal(0, 0.3, N_DAYS)

    fusion = TIMDRBatteryFusion()
    result = coupling.analyze(days, voltage, current_baseline, temperature, pv_deficit, fusion)
    return resistance, result


def test_negative_control_zero_gain_gives_identical_arms():
    """KONTROLA NEGATYWNA (pre-rejestrowana): przy coupling_gain=0 deficyt
    PV nie ma zadnego wplywu na prad, wiec zacieniane i niezacieniane ramie
    MUSZA wyjsc identyczne (roznica < 1e-9) - to nie jest empiryczne
    odkrycie, to sprawdzenie, ze sprzezenie faktycznie wylacza sie na gain=0."""
    r_shaded, _ = _run_arm(n_events=20, coupling_gain=0.0)
    r_control, _ = _run_arm(n_events=0, coupling_gain=0.0)
    assert np.allclose(r_shaded, r_control, atol=1e-9)


def test_shading_frequency_increases_battery_wear_trend():
    """
    PRE-REJESTRACJA (progi ustalone przed uruchomieniem, patrz
    prereg_experiment.py w historii sesji dla pelnego zapisu):

    Hipoteza: bateria sprzezona (coupling_gain=0.6) z CZESTO zacienianym
    PV (20 zdarzen/2 lata) ma WYZSZA koncowa rezystancje ORAZ wyzszy
    max|trend_z()| niz bateria kontrolna (0 zdarzen), przy tym samym
    coupling_gain.

    UCZCIWE ZASTRZEZENIE (odkryte podczas pierwszego uruchomienia, przed
    zamroezeniem tego testu): globalna regresja liniowa na calej historii
    E_bat dawala WZGLEDNA roznice ~140% miedzy ramionami, ale to byl
    artefakt bliskiego zera mianownika (nachylenie kontrolne bardzo male).
    Realna ABSOLUTNA roznica koncowej rezystancji wyniosla tylko ~2%.
    Dlatego prog powodzenia tego testu jest ABSOLUTNY, nie wzgledny:
    rezystancja koncowa (>=0.5%) i max|trend_z| (>=5%) wyzsze w ramieniu
    zacienianym - male, ale rzeczywiste roznice, zgodnie z tym co
    faktycznie zaobserwowano, nie z gory zalozonym duzym efektem.
    """
    r_shaded, res_shaded = _run_arm(n_events=20, coupling_gain=0.6)
    r_control, res_control = _run_arm(n_events=0, coupling_gain=0.6)

    assert r_shaded[-1] > r_control[-1] * 1.005, (
        f"rezystancja koncowa: zacieniana={r_shaded[-1]:.5f}, "
        f"kontrolna={r_control[-1]:.5f} - oczekiwano >=0.5% roznicy"
    )

    tz_shaded = np.nanmax(np.abs(res_shaded["trend_z"]))
    tz_control = np.nanmax(np.abs(res_control["trend_z"]))
    assert tz_shaded > tz_control * 1.05, (
        f"max|trend_z|: zacieniana={tz_shaded:.2f}, kontrolna={tz_control:.2f} "
        f"- oczekiwano >=5% roznicy"
    )


def test_single_shading_event_does_not_false_alarm_battery():
    """Regres wczesniejszego testu z tej sesji (joint_experiment.py):
    POJEDYNCZE zdarzenie zacienienia (+15% prad kompensacyjny, trwaly
    skok, nie powtarzajacy sie cykl) NIE powinno wywolac anomalii ani
    skretu baterii - efekt jest zbyt maly wzgledem progow MAD-z 3.0/3.5
    wyliczonych na calej historii. To jest oczekiwany, juz zweryfikowany
    wynik negatywny, nie nowa hipoteza."""
    n = 400
    days = np.arange(n, dtype=float)
    event_day = 200
    pv_deficit = np.zeros(n)
    pv_deficit[event_day:] = 0.15  # trwaly skok, nie impuls

    rng = np.random.default_rng(3)
    current_baseline = np.abs(1.0 + rng.normal(0, 0.02, n))

    coupling = TIMDRPVBatteryCoupling(coupling_gain=1.0, r0=0.05, k=0.0008)
    current, resistance = coupling.joint_battery_resistance(days, current_baseline, pv_deficit)
    voltage = 3.7 - 0.02 * (current - 1.0) + rng.normal(0, 0.01, n)
    temperature = 25.0 + 1.5 * (current - 1.0) + rng.normal(0, 0.3, n)

    fusion = TIMDRBatteryFusion()
    result = coupling.analyze(days, voltage, current_baseline, temperature, pv_deficit, fusion)

    window = slice(event_day, event_day + 10)
    assert not any(window.start <= idx < window.stop for idx in result["anomaly_idx"])
    assert not any(window.start <= idx < window.stop for idx in result["twist_idx"])
