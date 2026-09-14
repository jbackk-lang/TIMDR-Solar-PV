"""
api.py — TIMDR Solar PV, lokalne REST API
================================================================
Serwer Flask udostepniajacy:
  GET  /api/health        -> healthcheck samego API
  GET  /api/scenarios     -> lista dostepnych scenariuszy demo
  GET  /api/demo          -> syntetyczny zestaw danych (?scenario=<nazwa>)
  POST /api/analyze       -> pelna analiza TIMDR (fuse + twist/trend/anomalies/rhythm
                              + degradation_rate/time_to_threshold/health_score)

Uruchomienie: `python api.py` (albo `run.bat` na Windows), potem
http://127.0.0.1:5001 .

PODLACZALNOSC DO INNYCH REPO (to jest ten "operator", o ktory pytales):
`TIMDRSolarFusion`/`TIMDRSolarPredict` maja DOKLADNIE ten sam ksztalt
API co `TIMDRBatteryFusion`/`TIMDRBatteryPredict` w TIMDR-Battery-Predict
(fuse -> E,cos; twist/trend/anomalies/rhythm na E; fusion_score) - mozna
skopiowac (zwendorowac, z naglowkiem "ZWENDOROWANE" jak reszta
ekosystemu - patrz KATEGORIE.md w jbackk-lang.github.io) `timdr_solar_fusion.py`
i `timdr_solar_predict.py` do dowolnego innego repo bez zmiany reszty
kodu wywolujacego - jedyna rzecz specyficzna dla PV to argumenty
`fuse()` (power/poa_irradiance/module_temp/pdc0 zamiast
voltage/current/temperature/resistance).
"""

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from demo_scenarios import DEFAULT_THRESHOLDS, SCENARIOS, make_demo_data
from timdr_solar_fusion import TIMDRSolarFusion
from timdr_solar_predict import TIMDRSolarPredict

app = Flask(__name__, static_folder="static", static_url_path="")

fusion = TIMDRSolarFusion()
predict = TIMDRSolarPredict()

REQUIRED_FIELDS = ["power", "poa_irradiance", "module_temp"]


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/scenarios")
def api_scenarios():
    return jsonify([
        {"id": name, "description": desc, "default_threshold": DEFAULT_THRESHOLDS[name]}
        for name, desc in SCENARIOS.items()
    ])


@app.route("/api/demo")
def api_demo():
    scenario = request.args.get("scenario", "normal_operation")
    try:
        t, sensors = make_demo_data(scenario)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "scenario": scenario,
        "default_threshold": DEFAULT_THRESHOLDS.get(scenario, 0.10),
        "t_days": t.tolist(),
        "power": sensors["power"].tolist(),
        "poa_irradiance": sensors["poa_irradiance"].tolist(),
        "module_temp": sensors["module_temp"].tolist(),
        "pdc0": sensors["pdc0"],
    })


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    Body (JSON):
      t_days: [..]      - znaczniki czasu w DNIACH (nie sekundach/epoch)
      power: [..]       - moc DC/AC [W]
      poa_irradiance: [..]  - naswietlenie w plaszczyznie modulu [W/m^2]
      module_temp: [..] - temperatura modulu/ogniwa [degC]
      pdc0: float        - moc nominalna DC (STC) [W]
      gamma_pdc: float=-0.004  - wspolczynnik temperaturowy mocy [1/degC]
      threshold: float=0.10   - prog ostrzegawczy dla E=1-PR
      window_days: int=365    - okno regresji trendu/degradacji

    Zwraca pelny wynik analizy jako JSON.
    """
    body = request.get_json(force=True, silent=True) or {}

    missing_top = [f for f in ["t_days", "pdc0"] + REQUIRED_FIELDS if f not in body]
    if missing_top:
        return jsonify({"error": f"brakujace pola: {missing_top}"}), 400

    try:
        t = np.asarray(body["t_days"], dtype=float)
        power = np.asarray(body["power"], dtype=float)
        poa = np.asarray(body["poa_irradiance"], dtype=float)
        temp = np.asarray(body["module_temp"], dtype=float)
        pdc0 = float(body["pdc0"])
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"niepoprawne dane wejsciowe: {exc}"}), 400

    if len(t) == 0:
        return jsonify({"error": "t_days nie moze byc puste"}), 400

    gamma_pdc = float(body.get("gamma_pdc", -0.004))
    threshold = float(body.get("threshold", 0.10))
    window_days = int(body.get("window_days", 365))

    try:
        E, PR = fusion.fuse(t, power, poa, temp, pdc0, gamma_pdc)
        tw_idx, tw_z = fusion.twist(t, E)
        tr_sl, tr_z = fusion.trend(t, E, window=min(window_days, max(2, len(t))))
        an_idx, an_z = fusion.anomalies(E)
        periods, r_score = fusion.rhythm(E)
        score = fusion.fusion_score(tw_z, tr_z, an_z, r_score)

        degr = predict.degradation_rate_per_year(t, E, window_days=window_days)
        ttd = predict.time_to_threshold(t, E, threshold=threshold, window_days=window_days)
        health = predict.health_score(E, threshold=threshold)
    except Exception as exc:  # noqa: BLE001 - czytelny blad do dashboardu, nie goly 500
        return jsonify({"error": f"blad analizy: {exc}"}), 400

    def clean(x):
        if x is None:
            return None
        x = float(x)
        return None if not np.isfinite(x) else x

    def clean_list(x):
        return [clean(v) for v in np.asarray(x, float)]

    return jsonify({
        "t_days": t.tolist(),
        "E": clean_list(E),
        "PR": clean_list(PR),
        "twist_idx": tw_idx.tolist(),
        "trend_slopes": clean_list(tr_sl),
        "anomaly_idx": an_idx.tolist(),
        "rhythm_periods": periods,
        "rhythm_score": clean(r_score),
        "fusion_score": clean(score),
        "degradation_rate_pct_per_year": clean(degr["rate_pct_per_year"]),
        "degradation_vs_nrel_median_ratio": clean(degr["vs_nrel_median_ratio"]),
        "time_to_threshold_days": clean(ttd) if ttd != np.inf else None,
        "health_score": clean(health),
        "threshold": threshold,
        "window_days": window_days,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
