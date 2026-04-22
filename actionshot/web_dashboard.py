"""Flask web dashboard for ActionShot.

Provides a lightweight browser UI for viewing sessions, workflow
metrics, and system status.  Start via ``python main.py web``.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string

# ---------------------------------------------------------------------------
# HTML template (single-file, no external assets needed)
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ActionShot Dashboard</title>
<style>
  :root { --bg:#0f1117; --card:#1a1d27; --accent:#6c5ce7; --ok:#00b894;
          --warn:#fdcb6e; --err:#d63031; --txt:#dfe6e9; --dim:#636e72; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg);
         color:var(--txt); padding:2rem; }
  h1 { color:var(--accent); margin-bottom:.5rem; }
  .subtitle { color:var(--dim); margin-bottom:2rem; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
          gap:1rem; margin-bottom:2rem; }
  .card { background:var(--card); border-radius:10px; padding:1.5rem; }
  .card h3 { font-size:.85rem; color:var(--dim); text-transform:uppercase;
             letter-spacing:.05em; margin-bottom:.5rem; }
  .card .value { font-size:2rem; font-weight:700; }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .err { color:var(--err); }
  table { width:100%; border-collapse:collapse; margin-top:1rem; }
  th,td { text-align:left; padding:.6rem .8rem; border-bottom:1px solid #2d3436; }
  th { color:var(--dim); font-size:.8rem; text-transform:uppercase; }
  .badge { display:inline-block; padding:.15rem .5rem; border-radius:4px;
           font-size:.75rem; font-weight:600; }
  .badge-ok { background:rgba(0,184,148,.15); color:var(--ok); }
  .badge-err { background:rgba(214,48,49,.15); color:var(--err); }
  #activity { max-height:400px; overflow-y:auto; }
</style>
</head>
<body>
<h1>ActionShot</h1>
<p class="subtitle">Desktop Interaction Recorder &mdash; Dashboard</p>

<div class="grid">
  <div class="card"><h3>Workflows</h3><div class="value" id="v-workflows">--</div></div>
  <div class="card"><h3>Active Today</h3><div class="value" id="v-active">--</div></div>
  <div class="card"><h3>Avg Success Rate</h3><div class="value" id="v-rate">--</div></div>
  <div class="card"><h3>Sessions</h3><div class="value" id="v-sessions">--</div></div>
</div>

<div class="card">
  <h3>Recent Activity</h3>
  <div id="activity"><p style="color:var(--dim)">Loading&hellip;</p></div>
</div>

<script>
async function load(){
  try{
    const s=await(await fetch('/api/summary')).json();
    document.getElementById('v-workflows').textContent=s.total_workflows;
    document.getElementById('v-active').textContent=s.active_today;
    const r=s.avg_success_rate;
    const el=document.getElementById('v-rate');
    el.textContent=r.toFixed(1)+'%';
    el.className='value '+(r>=90?'ok':r>=70?'warn':'err');
    document.getElementById('v-sessions').textContent=s.session_count||0;
  }catch(e){ console.error(e); }
  try{
    const a=await(await fetch('/api/activity')).json();
    if(!a.length){ document.getElementById('activity').innerHTML='<p style="color:var(--dim)">No activity yet.</p>'; return; }
    let html='<table><tr><th>Time</th><th>Event</th><th>Workflow</th><th>Status</th></tr>';
    a.slice(0,30).forEach(e=>{
      const st=e.status||e.event||'';
      const cls=st==='success'?'badge-ok':'badge-err';
      html+='<tr><td>'+((e.timestamp||'').substring(0,19))+'</td><td>'+
        (e.event||'')+'</td><td>'+(e.workflow_id||'')+'</td><td><span class="badge '+cls+'">'+st+'</span></td></tr>';
    });
    html+='</table>';
    document.getElementById('activity').innerHTML=html;
  }catch(e){ console.error(e); }
}
load(); setInterval(load,15000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Flask application factory
# ---------------------------------------------------------------------------

def create_app(recordings_dir: str = "recordings") -> Flask:
    """Create and return the Flask application."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(INDEX_HTML)

    @app.route("/api/summary")
    def api_summary():
        from actionshot.telemetry import DashboardData
        try:
            dash = DashboardData()
            data = dash.summary()
        except Exception:
            data = {
                "total_workflows": 0,
                "avg_success_rate": 0.0,
                "active_today": 0,
            }
        # Add session count
        session_count = 0
        if os.path.isdir(recordings_dir):
            session_count = sum(
                1 for d in os.listdir(recordings_dir)
                if os.path.isdir(os.path.join(recordings_dir, d))
                and d.startswith("session_")
            )
        data["session_count"] = session_count
        return jsonify(data)

    @app.route("/api/activity")
    def api_activity():
        from actionshot.telemetry import DashboardData
        try:
            dash = DashboardData()
            events = dash.recent_activity(limit=50)
        except Exception:
            events = []
        return jsonify(events)

    @app.route("/api/workflow/<workflow_id>")
    def api_workflow(workflow_id: str):
        from actionshot.telemetry import DashboardData
        try:
            dash = DashboardData()
            details = dash.workflow_details(workflow_id)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify(details)

    @app.route("/api/session/<session_name>")
    def api_session(session_name: str):
        session_path = os.path.join(recordings_dir, session_name)
        summary_file = os.path.join(session_path, "session_summary.json")
        if not os.path.isfile(summary_file):
            return jsonify({"error": "Session not found"}), 404
        with open(summary_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)

    return app
