(function() {
  "use strict";

  const API_URL = "/cal/api/analytics/";

  // Chart instances (for destruction on re-render)
  let charts = {};

  // ── Date Range Helpers ──

  function toDateStr(d) {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  function getRange(preset) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    let start, end;

    switch (preset) {
      case 'week':
        const dow = today.getDay();
        const monday = new Date(today);
        monday.setDate(today.getDate() - ((dow + 6) % 7));
        start = monday;
        end = new Date(monday);
        end.setDate(monday.getDate() + 6);
        break;
      case 'month':
        start = new Date(today.getFullYear(), today.getMonth(), 1);
        end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        break;
      case 'quarter':
        const qMonth = Math.floor(today.getMonth() / 3) * 3;
        start = new Date(today.getFullYear(), qMonth, 1);
        end = new Date(today.getFullYear(), qMonth + 3, 0);
        break;
      case 'year':
        start = new Date(today.getFullYear(), 0, 1);
        end = new Date(today.getFullYear(), 11, 31);
        break;
      default:
        start = today;
        end = today;
    }
    return { start: toDateStr(start), end: toDateStr(end) };
  }

  // ── Chart Theme ──

  function isDark() {
    return document.body.classList.contains('dark-theme') ||
           document.documentElement.classList.contains('dark-theme');
  }

  function chartColors() {
    const dark = isDark();
    return {
      text: dark ? '#e2e8f0' : '#495057',
      grid: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
      primary: '#2ea8e5',
      primaryLight: 'rgba(46,168,229,0.6)',
      secondary: '#34d399',
      secondaryLight: 'rgba(52,211,153,0.6)',
      danger: '#f472b6',
      warning: '#fbbf24',
      purple: '#a78bfa',
      muted: dark ? '#a0aec0' : '#6c757d',
    };
  }

  function defaultScales() {
    const c = chartColors();
    return {
      x: { ticks: { color: c.text, font: { size: 11 } }, grid: { color: c.grid } },
      y: { ticks: { color: c.text, font: { size: 11 } }, grid: { color: c.grid }, beginAtZero: true },
    };
  }

  // ── Fetch & Render ──

  async function loadData(start, end) {
    try {
      const resp = await fetch(`${API_URL}?start=${start}&end=${end}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (err) {
      console.error("Analytics API error:", err);
      return null;
    }
  }

  function destroyCharts() {
    Object.values(charts).forEach(c => c.destroy());
    charts = {};
  }

  function updateStats(data) {
    const totalEvents = data.schedule_accuracy.total_events;
    const totalHours = data.track_utilization.reduce((s, t) => s + t.scheduled_hours, 0);
    const avgDelta = data.schedule_accuracy.avg_start_delta_minutes;
    const withActuals = data.schedule_accuracy.events_with_actuals;
    const rate = totalEvents > 0 ? Math.round((withActuals / totalEvents) * 100) : 0;

    document.getElementById('totalEvents').textContent = totalEvents;
    document.getElementById('totalHours').textContent = `${totalHours.toFixed(1)}h`;

    const deltaSign = avgDelta > 0 ? '+' : '';
    document.getElementById('avgAccuracy').textContent =
      withActuals > 0 ? `${deltaSign}${avgDelta.toFixed(1)} min` : 'N/A';

    document.getElementById('trackedRate').textContent = `${rate}%`;
  }

  function updateRangeDisplay(start, end) {
    const fmt = d => {
      const dt = new Date(d + 'T00:00:00');
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };
    document.getElementById('rangeDisplay').textContent = `${fmt(start)} — ${fmt(end)}`;
  }

  function renderCharts(data) {
    destroyCharts();
    const c = chartColors();
    const scales = defaultScales();

    // 1. Track Utilization — grouped bar
    const trackCtx = document.getElementById('trackUtilChart');
    if (data.track_utilization.length > 0) {
      charts.trackUtil = new Chart(trackCtx, {
        type: 'bar',
        data: {
          labels: data.track_utilization.map(t => t.name),
          datasets: [
            { label: 'Scheduled', data: data.track_utilization.map(t => t.scheduled_hours), backgroundColor: c.primaryLight, borderColor: c.primary, borderWidth: 1 },
            { label: 'Actual', data: data.track_utilization.map(t => t.actual_hours), backgroundColor: c.secondaryLight, borderColor: c.secondary, borderWidth: 1 },
          ]
        },
        options: {
          responsive: true,
          plugins: { legend: { labels: { color: c.text } } },
          scales: { ...scales, y: { ...scales.y, title: { display: true, text: 'Hours', color: c.text } } },
        }
      });
    } else {
      trackCtx.parentElement.innerHTML += '<div class="chart-empty">No track data for this period</div>';
    }

    // 2. Booking Volume — line chart
    const trendCtx = document.getElementById('trendChart');
    if (data.usage_trends.counts.some(v => v > 0)) {
      // Format labels as short dates
      const shortLabels = data.usage_trends.labels.map(l => {
        const d = new Date(l + 'T00:00:00');
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      });
      charts.trend = new Chart(trendCtx, {
        type: 'line',
        data: {
          labels: shortLabels,
          datasets: [{
            label: 'Events',
            data: data.usage_trends.counts,
            borderColor: c.primary,
            backgroundColor: 'rgba(46,168,229,0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { labels: { color: c.text } } },
          scales,
        }
      });
    } else {
      trendCtx.parentElement.innerHTML += '<div class="chart-empty">No events in this period</div>';
    }

    // 3. Peak Hours — bar chart
    const peakCtx = document.getElementById('peakHoursChart');
    if (data.peak_hours.length > 0) {
      // Fill all 24 hours
      const hourCounts = new Array(24).fill(0);
      data.peak_hours.forEach(h => { hourCounts[h.hour] = h.count; });
      const hourLabels = hourCounts.map((_, i) => `${String(i).padStart(2,'0')}:00`);
      charts.peak = new Chart(peakCtx, {
        type: 'bar',
        data: {
          labels: hourLabels,
          datasets: [{
            label: 'Events',
            data: hourCounts,
            backgroundColor: hourCounts.map((v, i) => v === Math.max(...hourCounts) ? c.primary : c.primaryLight),
            borderColor: c.primary,
            borderWidth: 1,
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales,
        }
      });
    } else {
      peakCtx.parentElement.innerHTML += '<div class="chart-empty">No data</div>';
    }

    // 4. User Activity — horizontal bar
    const userCtx = document.getElementById('userChart');
    if (data.user_activity.length > 0) {
      charts.user = new Chart(userCtx, {
        type: 'bar',
        data: {
          labels: data.user_activity.map(u => u.username),
          datasets: [
            { label: 'Approved', data: data.user_activity.map(u => u.approved), backgroundColor: c.secondaryLight, borderColor: c.secondary, borderWidth: 1 },
            { label: 'Pending', data: data.user_activity.map(u => u.pending), backgroundColor: 'rgba(251,191,36,0.5)', borderColor: c.warning, borderWidth: 1 },
          ]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          plugins: { legend: { labels: { color: c.text } } },
          scales: {
            x: { ...scales.x, stacked: true },
            y: { ...scales.y, stacked: true },
          },
        }
      });
    } else {
      userCtx.parentElement.innerHTML += '<div class="chart-empty">No user data</div>';
    }

    // 5. Asset Usage — bar chart
    const assetCtx = document.getElementById('assetChart');
    if (data.asset_usage.length > 0) {
      const typeColors = { vehicle: c.primary, operator: c.purple };
      charts.asset = new Chart(assetCtx, {
        type: 'bar',
        data: {
          labels: data.asset_usage.map(a => a.name),
          datasets: [{
            label: 'Hours',
            data: data.asset_usage.map(a => a.total_hours),
            backgroundColor: data.asset_usage.map(a => typeColors[a.type] || c.muted),
            borderWidth: 1,
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: { ...scales, y: { ...scales.y, title: { display: true, text: 'Hours', color: c.text } } },
        }
      });
    } else {
      assetCtx.parentElement.innerHTML += '<div class="chart-empty">No asset data for this period</div>';
    }
  }

  // ── Main ──

  let currentRange = 'week';

  async function refresh() {
    const { start, end } = currentRange === 'custom'
      ? { start: document.getElementById('rangeStart').value, end: document.getElementById('rangeEnd').value }
      : getRange(currentRange);

    updateRangeDisplay(start, end);
    const data = await loadData(start, end);
    if (!data) return;
    updateStats(data);
    renderCharts(data);
  }

  // Range preset buttons
  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRange = btn.dataset.range;

      const customEl = document.getElementById('customRange');
      if (currentRange === 'custom') {
        customEl.classList.remove('hidden');
      } else {
        customEl.classList.add('hidden');
        refresh();
      }
    });
  });

  // Custom range apply
  document.getElementById('applyRange').addEventListener('click', refresh);

  // Initial load
  refresh();

})();
