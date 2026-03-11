"""Localhost web GUI for the propane deasphalting simulator.

Run:
    python3 pda_web_app.py
Then open http://127.0.0.1:8000 in your browser.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pda_simulator import FeedComposition, PDAModelParameters, PDASimulator, sensitivity_analysis


def _float(params: dict[str, list[str]], key: str, default: float) -> float:
    try:
        return float(params.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def build_simulator(params: dict[str, list[str]]) -> tuple[PDASimulator, float]:
    feed = FeedComposition(
        dao_oil=_float(params, "dao_oil", 0.72),
        resins=_float(params, "resins", 0.18),
        asphaltenes=_float(params, "asphaltenes", 0.10),
    )
    model = PDAModelParameters(
        ymax=_float(params, "ymax", 0.85),
        k=_float(params, "k", 0.8),
        a=_float(params, "a", 0.7),
        c_entrain=_float(params, "c_entrain", 0.03),
    )
    so_ratio = _float(params, "so_ratio", 5.0)
    simulator = PDASimulator(feed=feed, params=model)
    return simulator, so_ratio


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>PDA Simulator</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; max-width: 1000px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
    .card { border: 1px solid #ccc; border-radius: 8px; padding: 12px; flex: 1; min-width: 280px; }
    label { display: block; margin-top: 6px; font-size: 13px; }
    input { width: 100%; padding: 5px; }
    button { margin-top: 10px; padding: 8px 12px; cursor: pointer; }
    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f6f6f6; }
    .result { font-size: 14px; }
    pre { background: #f8f8f8; padding: 8px; border-radius: 6px; overflow-x: auto; }
  </style>
</head>
<body>
  <h2>Propane Deasphalting (PDA) Simulator</h2>
  <p>Interactive simplified refinery-correlation model (localhost).</p>

  <div class="row">
    <div class="card">
      <h3>Feed composition (mass fractions)</h3>
      <label>DAO forming oil <input id="dao_oil" value="0.72" /></label>
      <label>Resins <input id="resins" value="0.18" /></label>
      <label>Asphaltenes <input id="asphaltenes" value="0.10" /></label>
    </div>

    <div class="card">
      <h3>Model parameters</h3>
      <label>Ymax <input id="ymax" value="0.85" /></label>
      <label>k <input id="k" value="0.8" /></label>
      <label>a <input id="a" value="0.7" /></label>
      <label>C_entrain <input id="c_entrain" value="0.03" /></label>
    </div>

    <div class="card">
      <h3>Single simulation</h3>
      <label>Solvent/Oil ratio <input id="so_ratio" value="5.0" /></label>
      <button onclick="runSingle()">Run simulation</button>
      <div class="result" id="single_result"></div>
    </div>
  </div>

  <div class="card">
    <h3>Sensitivity analysis</h3>
    <div class="row">
      <label>SO min <input id="so_min" value="1.0" /></label>
      <label>SO max <input id="so_max" value="10.0" /></label>
      <label>SO step <input id="so_step" value="0.5" /></label>
    </div>
    <button onclick="runSweep()">Run sensitivity</button>
    <table id="sweep_table"></table>
  </div>

<script>
function params() {
  return new URLSearchParams({
    dao_oil: document.getElementById('dao_oil').value,
    resins: document.getElementById('resins').value,
    asphaltenes: document.getElementById('asphaltenes').value,
    ymax: document.getElementById('ymax').value,
    k: document.getElementById('k').value,
    a: document.getElementById('a').value,
    c_entrain: document.getElementById('c_entrain').value,
    so_ratio: document.getElementById('so_ratio').value,
    so_min: document.getElementById('so_min').value,
    so_max: document.getElementById('so_max').value,
    so_step: document.getElementById('so_step').value,
  });
}

async function runSingle() {
  const res = await fetch('/api/simulate?' + params().toString());
  const d = await res.json();
  if (d.error) { document.getElementById('single_result').innerText = d.error; return; }
  document.getElementById('single_result').innerHTML = `
    <p><b>DAO yield:</b> ${d.dao_yield_wt_pct.toFixed(2)} wt%</p>
    <p><b>DAO viscosity @100C:</b> ${d.dao_viscosity_cst_100c.toFixed(2)} cSt</p>
    <p><b>Asphaltene ppm:</b> ${d.asphaltene_ppm_in_dao.toFixed(1)} ppm</p>
    <p><b>Color risk:</b> ${d.color_category}</p>`;
}

async function runSweep() {
  const res = await fetch('/api/sweep?' + params().toString());
  const d = await res.json();
  if (d.error) { document.getElementById('sweep_table').innerHTML = `<tr><td>${d.error}</td></tr>`; return; }
  let html = '<tr><th>SO ratio</th><th>DAO yield (wt%)</th><th>Asphaltene ppm</th><th>Viscosity cSt @100C</th><th>Color</th></tr>';
  for (const r of d.results) {
    html += `<tr><td>${r.so_ratio.toFixed(2)}</td><td>${r.dao_yield_wt_pct.toFixed(2)}</td><td>${r.asphaltene_ppm_in_dao.toFixed(1)}</td><td>${r.dao_viscosity_cst_100c.toFixed(2)}</td><td>${r.color_category}</td></tr>`;
  }
  document.getElementById('sweep_table').innerHTML = html;
}
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        params = parse_qs(parsed.query)

        if parsed.path == "/api/simulate":
            try:
                simulator, so_ratio = build_simulator(params)
                result = simulator.simulate(so_ratio)
                self._send_json(
                    {
                        "so_ratio": result.solvent_oil_ratio,
                        "dao_yield_wt_pct": result.dao_yield * 100,
                        "dao_viscosity_cst_100c": result.dao_viscosity_cst_100c,
                        "asphaltene_ppm_in_dao": result.asphaltene_ppm_in_dao,
                        "color_category": result.color_category,
                    }
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
            return

        if parsed.path == "/api/sweep":
            try:
                simulator, _ = build_simulator(params)
                so_min = _float(params, "so_min", 1.0)
                so_max = _float(params, "so_max", 10.0)
                so_step = _float(params, "so_step", 0.5)
                if so_step <= 0:
                    raise ValueError("so_step must be > 0")
                if so_max < so_min:
                    raise ValueError("so_max must be >= so_min")

                ratios: list[float] = []
                x = so_min
                while x <= so_max + 1e-12:
                    ratios.append(round(x, 6))
                    x += so_step

                results = sensitivity_analysis(simulator, ratios)
                payload = {
                    "results": [
                        {
                            "so_ratio": r.solvent_oil_ratio,
                            "dao_yield_wt_pct": r.dao_yield * 100,
                            "dao_viscosity_cst_100c": r.dao_viscosity_cst_100c,
                            "asphaltene_ppm_in_dao": r.asphaltene_ppm_in_dao,
                            "color_category": r.color_category,
                        }
                        for r in results
                    ]
                }
                self._send_json(payload)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
            return

        self._send_json({"error": "Not Found"}, status=404)


def main() -> None:
    host, port = "127.0.0.1", 8000
    print(f"Starting PDA web GUI at http://{host}:{port}")
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
