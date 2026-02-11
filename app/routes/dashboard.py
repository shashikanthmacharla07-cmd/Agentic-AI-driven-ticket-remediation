# app/routes/dashboard.py
"""
Dashboard routes for viewing pipeline status and incident processing history.
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/dashboard")


@router.get("/api/summary")
async def dashboard_summary(request: Request):
    """Return aggregate pipeline stats."""
    repo = getattr(request.app.state, "pipeline_repo", None)
    if not repo:
        return JSONResponse({"error": "Pipeline tracking not configured"}, status_code=503)
    summary = await repo.dashboard_summary()
    return summary


@router.get("/api/runs")
async def dashboard_runs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return paginated list of pipeline runs."""
    repo = getattr(request.app.state, "pipeline_repo", None)
    if not repo:
        return JSONResponse({"error": "Pipeline tracking not configured"}, status_code=503)
    runs = await repo.list_runs(limit=limit, offset=offset)
    return {"runs": runs, "limit": limit, "offset": offset}


@router.get("", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve the dashboard HTML page."""
    return HTMLResponse(content=DASHBOARD_HTML)


# ---------------------------------------------------------------------------
#  Inline HTML / CSS / JS for the dashboard
# ---------------------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agentic AI Ops — Pipeline Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface-hover: #22263a;
    --border: #2a2e3e;
    --text: #e4e6ef;
    --text-muted: #8b8fa3;
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,.25);
    --green: #22c55e;
    --green-bg: rgba(34,197,94,.12);
    --red: #ef4444;
    --red-bg: rgba(239,68,68,.12);
    --yellow: #eab308;
    --yellow-bg: rgba(234,179,8,.12);
    --blue: #3b82f6;
    --blue-bg: rgba(59,130,246,.12);
    --radius: 12px;
    --radius-sm: 8px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 0;
  }

  /* ---- header ---- */
  .header {
    background: linear-gradient(135deg, #1e1b4b 0%, #1a1d27 100%);
    border-bottom: 1px solid var(--border);
    padding: 28px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .header h1 {
    font-size: 22px;
    font-weight: 700;
    background: linear-gradient(135deg, #818cf8, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .header .status-pill {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-muted);
  }
  .header .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* ---- container ---- */
  .container { max-width: 1280px; margin: 0 auto; padding: 32px 40px; }

  /* ---- cards row ---- */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    transition: transform .15s, box-shadow .15s;
  }
  .card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,.25);
  }
  .card .label { font-size: 12px; text-transform: uppercase; letter-spacing: .8px; color: var(--text-muted); margin-bottom: 8px; }
  .card .value { font-size: 32px; font-weight: 700; }
  .card .sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
  .card.green .value { color: var(--green); }
  .card.red .value { color: var(--red); }
  .card.yellow .value { color: var(--yellow); }
  .card.blue .value { color: var(--blue); }

  /* ---- table ---- */
  .table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .table-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
    border-bottom: 1px solid var(--border);
  }
  .table-header h2 { font-size: 16px; font-weight: 600; }
  .table-header .refresh-info { font-size: 12px; color: var(--text-muted); }

  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left;
    padding: 12px 16px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .8px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
    background: var(--bg);
    position: sticky; top: 0;
  }
  td {
    padding: 14px 16px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  tr:hover td { background: var(--surface-hover); }
  tr:last-child td { border-bottom: none; }

  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .5px;
  }
  .badge.success { background: var(--green-bg); color: var(--green); }
  .badge.error   { background: var(--red-bg);   color: var(--red); }
  .badge.pending,
  .badge.intake,
  .badge.classifying,
  .badge.planning,
  .badge.executing,
  .badge.validating,
  .badge.closing { background: var(--blue-bg); color: var(--blue); }
  .badge.awaiting_approval { background: var(--yellow-bg); color: var(--yellow); }

  .severity { font-weight: 600; }
  .severity.P1 { color: var(--red); }
  .severity.P2 { color: #f97316; }
  .severity.P3 { color: var(--yellow); }
  .severity.P4 { color: var(--text-muted); }

  .error-msg {
    max-width: 220px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--red);
    font-size: 12px;
    cursor: help;
  }

  .empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-muted);
  }
  .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
  .empty-state p { font-size: 14px; }

  /* ---- loading skeleton ---- */
  .skeleton {
    background: linear-gradient(90deg, var(--surface) 25%, var(--surface-hover) 50%, var(--surface) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: var(--radius-sm);
    height: 40px;
  }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  /* ---- scrollable table ---- */
  .table-scroll { max-height: 600px; overflow-y: auto; }
  .table-scroll::-webkit-scrollbar { width: 6px; }
  .table-scroll::-webkit-scrollbar-track { background: var(--bg); }
  .table-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>

<div class="header">
  <h1>🤖 Agentic AI Ops — Pipeline Dashboard</h1>
  <div class="status-pill">
    <div class="dot"></div>
    <span id="refreshStatus">Auto-refresh: 30s</span>
  </div>
</div>

<div class="container">
  <!-- Summary cards -->
  <div class="cards" id="cards">
    <div class="card"><div class="skeleton" style="height:80px"></div></div>
    <div class="card"><div class="skeleton" style="height:80px"></div></div>
    <div class="card"><div class="skeleton" style="height:80px"></div></div>
    <div class="card"><div class="skeleton" style="height:80px"></div></div>
    <div class="card"><div class="skeleton" style="height:80px"></div></div>
  </div>

  <!-- Pipeline runs table -->
  <div class="table-wrap">
    <div class="table-header">
      <h2>Pipeline Runs</h2>
      <div class="refresh-info" id="lastRefresh">Loading…</div>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>Description</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Stage</th>
            <th>Duration</th>
            <th>Started</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody id="runsBody">
          <tr><td colspan="8"><div class="skeleton"></div></td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<script>
const API_BASE = '/dashboard/api';
const REFRESH_INTERVAL = 30000;

function formatDuration(ms) {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return ms + 'ms';
  const s = (ms / 1000).toFixed(1);
  if (s < 60) return s + 's';
  const m = Math.floor(ms / 60000);
  const rem = ((ms % 60000) / 1000).toFixed(0);
  return m + 'm ' + rem + 's';
}

function timeAgo(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return Math.floor(diff) + 's ago';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

function renderCards(data) {
  const rate = data.total > 0 ? ((data.success / data.total) * 100).toFixed(1) : '0.0';
  document.getElementById('cards').innerHTML = `
    <div class="card">
      <div class="label">Total Runs</div>
      <div class="value">${data.total}</div>
      <div class="sub">All pipeline executions</div>
    </div>
    <div class="card green">
      <div class="label">Successful</div>
      <div class="value">${data.success}</div>
      <div class="sub">${rate}% success rate</div>
    </div>
    <div class="card red">
      <div class="label">Errors</div>
      <div class="value">${data.errors}</div>
      <div class="sub">Failed pipeline runs</div>
    </div>
    <div class="card yellow">
      <div class="label">Awaiting Approval</div>
      <div class="value">${data.awaiting_approval}</div>
      <div class="sub">Human review required</div>
    </div>
    <div class="card blue">
      <div class="label">In Progress</div>
      <div class="value">${data.in_progress}</div>
      <div class="sub">Avg ${formatDuration(data.avg_duration_ms)}</div>
    </div>
  `;
}

function renderRuns(runs) {
  const tbody = document.getElementById('runsBody');
  if (!runs || runs.length === 0) {
    tbody.innerHTML = `
      <tr><td colspan="8">
        <div class="empty-state">
          <div class="icon">📋</div>
          <p>No pipeline runs yet. Incidents from ServiceNow will appear here once processed.</p>
        </div>
      </td></tr>`;
    return;
  }
  tbody.innerHTML = runs.map(r => `
    <tr>
      <td><strong>${r.incident_number || '—'}</strong></td>
      <td style="max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
          title="${(r.short_description || '').replace(/"/g, '&quot;')}">${r.short_description || '—'}</td>
      <td><span class="severity ${r.severity || ''}">${r.severity || '—'}</span></td>
      <td><span class="badge ${r.status}">${r.status}</span></td>
      <td>${r.current_stage || '—'}</td>
      <td>${formatDuration(r.duration_ms)}</td>
      <td title="${r.started_at || ''}">${timeAgo(r.started_at)}</td>
      <td>${r.error_message ? `<span class="error-msg" title="${r.error_message.replace(/"/g, '&quot;')}">${r.error_message}</span>` : '—'}</td>
    </tr>
  `).join('');
}

async function refresh() {
  try {
    const [sumRes, runsRes] = await Promise.all([
      fetch(API_BASE + '/summary'),
      fetch(API_BASE + '/runs?limit=100')
    ]);
    const summary = await sumRes.json();
    const runsData = await runsRes.json();
    renderCards(summary);
    renderRuns(runsData.runs);
    document.getElementById('lastRefresh').textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.error('Dashboard refresh error:', err);
    document.getElementById('lastRefresh').textContent = 'Update failed — retrying…';
  }
}

refresh();
setInterval(refresh, REFRESH_INTERVAL);
</script>
</body>
</html>
"""
