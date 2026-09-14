"""
real_pvdaq_test.py — walidacja na PRAWDZIWYCH danych NREL PVDAQ
================================================================================
UCZCIWE ZASTRZEŻENIE (przeczytaj przed użyciem): ten skrypt NIE ZOSTAŁ
URUCHOMIONY na prawdziwych danych PVDAQ w środowisku, w którym powstał —
sandbox miał dostęp tylko do github.com i PyPI (przez które zweryfikowano
demo_scenarios.py/testy syntetyczne, patrz README.md), a bucket danych
PVDAQ (oedi-data-lake na S3, dziesiątki-setki MB/system) był
niedostępny przez tamten proxy. Kod poniżej został napisany na
podstawie oficjalnej dokumentacji schematu
(github.com/openEDI/documentation/blob/main/pvdaq.md — format
long-format, tabela `pvdaq_pvdata` z `metric_id` odsyłającym do
`pvdaq_metrics` po nazwę/jednostki kanału), NIE na podstawie
przetestowania na realnym pliku. Zanim zaufasz wynikom, uruchom
`pytest test_real_pvdaq_ingest.py` na SWOIM pobranym pliku i sprawdź,
czy `ingest_pvdaq_csv()` faktycznie rozpoznaje Twoje kolumny (patrz
funkcja `describe_columns()` niżej — wypisze, co znalazła).

## Jak pobrać dane (bucket publiczny, bez logowania/klucza)

1. Lista systemów: https://oedi-data-lake.s3.amazonaws.com/pvdaq/csv/systems_20250729.csv
   (kolumny: system_id, dataset_size_mb, years, qa_status - wybierz mały,
   `qa_status=pass`, kilkuletni system, np. kilkadziesiąt MB, nie kilka GB).
2. AWS CLI (bez podpisywania, nie trzeba konta AWS):
   `aws s3 cp --no-sign-request s3://oedi-data-lake/pvdaq/csv/<system_id>/ ./pvdaq_raw/ --recursive`
   (dane są partycjonowane po roku/miesiącu/dniu - to ściągnie cały system).
3. Albo przez przeglądarkę: https://data.openei.org/s3_viewer?bucket=oedi-data-lake&prefix=pvdaq%2Fcsv%2F

## Co ten skrypt robi

`ingest_pvdaq_csv(path)` czyta plik(i) CSV, PRÓBUJE rozpoznać kolumny
mocy/naświetlenia POA/temperatury modułu po WZORCACH NAZW (nie sztywnych
nazwach — schemat PVDAQ różni się między systemami, patrz dokumentacja),
i zwraca dict gotowy do `TIMDRSolarFusion.fuse()`. Jeśli auto-detekcja
zawiedzie, `describe_columns()` pokaże wszystkie kolumny, żebyś mógł
ręcznie podać `power_col=`, `poa_col=`, `temp_col=` do `ingest_pvdaq_csv()`.
"""

import glob
import os

import numpy as np
import pandas as pd

# Wzorce nazw kolumn (case-insensitive substring match), w kolejnosci
# preferencji - PVDAQ common_name w pvdaq_metrics uzywa m.in. tych fraz
# (patrz dokumentacja schematu, sekcja pvdaq_metrics.common_name).
POWER_PATTERNS = ["ac_power", "dc_power", "power_ac", "power_dc", "poa_to_ac", "inv_power"]
POA_PATTERNS = ["poa_irradiance", "irradiance_poa", "poa_", "gpoa", "plane_of_array"]
TEMP_PATTERNS = ["module_temp", "cell_temp", "temp_module", "temp_cell", "back_of_module"]
TIME_PATTERNS = ["measured_on", "timestamp", "date_time", "datetime"]


def _find_column(columns, patterns):
    lower = {c: c.lower() for c in columns}
    for pat in patterns:
        for col, col_lower in lower.items():
            if pat in col_lower:
                return col
    return None


def describe_columns(path):
    """Wypisuje wszystkie kolumny znalezionego pliku/plikow - uzyj tego
    PIERWSZE, zanim zawolasz ingest_pvdaq_csv(), zeby sprawdzic co
    faktycznie jest w Twoim pobranym pliku."""
    files = sorted(glob.glob(path)) if "*" in path else [path]
    if not files:
        raise FileNotFoundError(f"brak plikow pasujacych do: {path}")
    df = pd.read_csv(files[0], nrows=5)
    print(f"Plik: {files[0]}")
    print(f"Kolumny ({len(df.columns)}):")
    for c in df.columns:
        print(f"  - {c}  (przyklad: {df[c].iloc[0] if len(df) else '?'})")
    return list(df.columns)


def ingest_pvdaq_csv(path, power_col=None, poa_col=None, temp_col=None, time_col=None, pdc0=None):
    """
    Wczytuje jeden lub wiele plikow CSV (path moze byc wzorcem glob, np.
    'pvdaq_raw/**/*.csv') i zwraca dict {t_days, power, poa_irradiance,
    module_temp, pdc0} gotowy do TIMDRSolarFusion.fuse(*dict.values()).

    Jesli power_col/poa_col/temp_col/time_col=None, probuje auto-detekcji
    po wzorcach nazw (patrz POWER_PATTERNS itd.) - NIEPRZETESTOWANE na
    realnym pliku (patrz naglowek modulu), moze wymagac recznego podania.

    pdc0: jesli None, uzyta zostanie MAX zaobserwowanej mocy jako
    przyblizenie (uczciwe przyblizenie 'z gory' - PR bedzie wtedy <= 1.0
    z definicji, co maskuje faktyczna degradacje ponizej momentu
    najwyzszej historycznie mocy; DOKLADNIEJSZE pdc0 z metadanych systemu
    (pvdaq_system.power) jest lepsze, jesli je masz).
    """
    files = sorted(glob.glob(path)) if "*" in path else [path]
    if not files:
        raise FileNotFoundError(f"brak plikow pasujacych do: {path}")

    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    cols = list(df.columns)
    power_col = power_col or _find_column(cols, POWER_PATTERNS)
    poa_col = poa_col or _find_column(cols, POA_PATTERNS)
    temp_col = temp_col or _find_column(cols, TEMP_PATTERNS)
    time_col = time_col or _find_column(cols, TIME_PATTERNS)

    missing = [name for name, val in [("power", power_col), ("poa_irradiance", poa_col),
                                        ("module_temp", temp_col), ("time", time_col)] if val is None]
    if missing:
        raise ValueError(
            f"nie udalo sie auto-wykryc kolumn: {missing}. Uruchom describe_columns('{path}') "
            f"i podaj je recznie (power_col=, poa_col=, temp_col=, time_col=)."
        )

    t = pd.to_datetime(df[time_col])
    t_days = (t - t.min()).dt.total_seconds().to_numpy() / 86400.0
    power = df[power_col].astype(float).to_numpy()
    poa = df[poa_col].astype(float).to_numpy()
    temp = df[temp_col].astype(float).to_numpy()

    if pdc0 is None:
        pdc0 = float(np.nanmax(power))

    return {"t_days": t_days, "power": power, "poa_irradiance": poa, "module_temp": temp, "pdc0": pdc0}


def run_real_validation(path, **ingest_kwargs):
    """Pelny przebieg: wczytaj realne dane, policz PR/E, tempo degradacji,
    i porownaj z benchmarkiem NREL 0.75%/rok. WYPISUJE wynik, nie
    twierdzi z gory jaki bedzie."""
    from timdr_solar_fusion import TIMDRSolarFusion
    from timdr_solar_predict import TIMDRSolarPredict

    data = ingest_pvdaq_csv(path, **ingest_kwargs)
    fusion = TIMDRSolarFusion()
    predict = TIMDRSolarPredict()

    E, PR = fusion.fuse(data["t_days"], data["power"], data["poa_irradiance"],
                          data["module_temp"], data["pdc0"])

    n_valid = int(np.sum(np.isfinite(PR)))
    print(f"Probek dziennych (POA >= {fusion.irradiance_floor} W/m^2): {n_valid} / {len(data['t_days'])}")
    print(f"PR: mediana={np.nanmedian(PR):.3f}, p10={np.nanpercentile(PR, 10):.3f}, p90={np.nanpercentile(PR, 90):.3f}")

    window_days = int(min(365 * 2, data["t_days"][-1] - data["t_days"][0]))
    degr = predict.degradation_rate_per_year(data["t_days"], E, window_days=window_days)
    print(f"Tempo degradacji (ostatnie {window_days} dni): {degr['rate_pct_per_year']}%/rok "
          f"(NREL median=0.75%/rok, stosunek={degr['vs_nrel_median_ratio']})")

    idx, z = fusion.anomalies(E)
    print(f"Liczba wykrytych anomalii (|MAD-z|>3.0): {len(idx)} / {n_valid}")

    return {"PR": PR, "E": E, "degradation": degr, "anomaly_idx": idx}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUzycie: python real_pvdaq_test.py <sciezka_do_csv_lub_wzorca_glob> [--describe]")
        sys.exit(1)
    path = sys.argv[1]
    if "--describe" in sys.argv:
        describe_columns(path)
    else:
        run_real_validation(path)
