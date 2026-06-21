/**
 * ATVED Authority Dashboard
 * Fetches live violation data from the API and renders charts + table.
 */

const API_BASE = 'http://localhost:8000/api/v1';

document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    setupNavigation();
});

function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-links a');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const targetId = e.currentTarget.getAttribute('href').substring(1);
            if (targetId === 'appeals' || targetId === 'overview') {
                e.preventDefault();
                // Update active class
                document.querySelectorAll('.nav-links li').forEach(li => li.classList.remove('active'));
                e.currentTarget.parentElement.classList.add('active');
                
                // Show/hide sections
                document.querySelectorAll('.content-wrapper').forEach(el => el.style.display = 'none');
                document.getElementById(targetId).style.display = 'block';
                
                if (targetId === 'appeals') loadAppeals();
            }
        });
    });
}

Chart.defaults.color = '#8b92a5';
Chart.defaults.font.family = "'Inter', sans-serif";

async function loadDashboard() {
    try {
        const [statsRes, violationsRes] = await Promise.all([
            fetch(`${API_BASE}/stats`),
            fetch(`${API_BASE}/violations`),
        ]);
        const stats = await statsRes.json();
        const violations = await violationsRes.json();

        updateStatCards(stats);
        initCharts(stats);
        populateTable(violations);
    } catch (err) {
        console.error('API fetch failed, loading with empty data:', err);
        initCharts({ by_type: {} });
        populateTable([]);
    }
}

function updateStatCards(stats) {
    const cards = document.querySelectorAll('.stat-card .stat-number');
    if (cards.length >= 4) {
        cards[0].textContent = (stats.total_violations ?? 0).toLocaleString();
        cards[1].textContent = (stats.pending_review ?? 0).toLocaleString();
        cards[2].textContent = (stats.registered_drivers ?? 0).toLocaleString();
        // Card 4 keeps its static "99.7%" accuracy label
    }
}

function initCharts(stats) {
    // Trend Chart (Line) – still uses illustrative weekly data
    const trendCtx = document.getElementById('trendChart').getContext('2d');
    const gradient = trendCtx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

    new Chart(trendCtx, {
        type: 'line',
        data: {
            labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            datasets: [{
                label: 'Violations Detected',
                data: [12, 19, 15, 17, 14, 22, stats.total_violations || 25],
                borderColor: '#3b82f6',
                backgroundColor: gradient,
                borderWidth: 3, tension: 0.4, fill: true,
                pointBackgroundColor: '#0f111a',
                pointBorderColor: '#3b82f6',
                pointBorderWidth: 2, pointRadius: 4, pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, border: { display: false } },
                x: { grid: { display: false }, border: { display: false } }
            }
        }
    });

    // Violation Type Chart (Doughnut) – from real DB stats
    const byType = stats.by_type || {};
    const labels = Object.keys(byType).map(k => k.replace('_', ' '));
    const values = Object.values(byType);
    const colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#64748b', '#ec4899', '#06b6d4'];

    const typeCtx = document.getElementById('typeChart').getContext('2d');
    new Chart(typeCtx, {
        type: 'doughnut',
        data: {
            labels: labels.length ? labels : ['No Data'],
            datasets: [{
                data: values.length ? values : [1],
                backgroundColor: labels.length ? colors.slice(0, labels.length) : ['#334155'],
                borderWidth: 0, hoverOffset: 4
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '75%',
            plugins: { legend: { position: 'right', labels: { boxWidth: 12, usePointStyle: true, padding: 20 } } }
        }
    });
}

function populateTable(violations) {
    const tbody = document.querySelector('#violationsTable tbody');
    tbody.innerHTML = '';

    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 20px;">No violations yet. Run demo_database.py to generate data.</td></tr>';
        return;
    }

    violations.forEach(row => {
        const tr = document.createElement('tr');
        const badgeClass = row.status.includes('PENDING') ? 'pending' : 'confirmed';
        const conf = row.confidence || 0;
        const timeStr = row.detected_at ? new Date(row.detected_at).toLocaleTimeString() : '--';

        tr.innerHTML = `
            <td>${timeStr}</td>
            <td>--</td>
            <td>${row.type.replace('_', ' ')}</td>
            <td>${row.vehicle_type || 'unknown'}</td>
            <td style="font-family: monospace; font-size: 1.05rem;">${row.plate || 'N/A'}</td>
            <td><div style="display: flex; align-items: center; gap: 8px;">
                <div style="width: 50px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                    <div style="width: ${conf * 100}%; height: 100%; background: ${conf > 0.95 ? 'var(--status-success)' : 'var(--accent-primary)'};"></div>
                </div>
                ${(conf * 100).toFixed(1)}%
            </div></td>
            <td><span class="badge ${badgeClass}">${row.status.replace('_', ' ')}</span></td>
            <td><button class="btn" style="padding: 4px 12px; font-size: 0.8rem; background: transparent; border: 1px solid var(--border-color);">Review</button></td>
        `;
        tbody.appendChild(tr);
    });
}

async function loadAppeals() {
    try {
        const res = await fetch(`${API_BASE}/appeals`);
        const appeals = await res.json();
        const tbody = document.querySelector('#appealsTable tbody');
        tbody.innerHTML = '';
        
        if (!appeals.length) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px;">No appeals in queue.</td></tr>';
            return;
        }
        
        appeals.forEach(a => {
            const tr = document.createElement('tr');
            let statusBadge = '';
            if (a.status === 'SUBMITTED') statusBadge = '<span class="badge pending">Pending</span>';
            else if (a.status === 'ACCEPTED') statusBadge = '<span class="badge" style="background:rgba(16,185,129,0.1);color:#10b981;border:1px solid rgba(16,185,129,0.3)">Accepted</span>';
            else statusBadge = '<span class="badge" style="background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3)">Rejected</span>';
            
            let actions = '';
            if (a.status === 'SUBMITTED') {
                actions = `
                    <button class="btn" style="padding: 4px 12px; font-size: 0.8rem; background: #10b981; border: none; margin-right: 5px;" onclick="resolveAppeal('${a.id}', 'ACCEPT')">Accept</button>
                    <button class="btn" style="padding: 4px 12px; font-size: 0.8rem; background: #ef4444; border: none;" onclick="resolveAppeal('${a.id}', 'REJECT')">Reject</button>
                `;
            } else {
                actions = `<span style="color:var(--text-muted);font-size:0.8rem;">Resolved</span>`;
            }
            
            tr.innerHTML = `
                <td style="font-family:monospace;font-size:0.85rem">${a.id.substring(0,8)}</td>
                <td style="font-family:monospace;font-size:0.85rem">${a.violation_id.substring(0,8)}</td>
                <td>${a.reason}</td>
                <td>${statusBadge}</td>
                <td>${actions}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Failed to load appeals', e);
    }
}

async function resolveAppeal(id, action) {
    if(!confirm(`Are you sure you want to ${action} this appeal?`)) return;
    try {
        const res = await fetch(`${API_BASE}/appeals/${id}/resolve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: action, notes: 'Reviewed by admin' })
        });
        if (res.ok) {
            loadAppeals(); // refresh list
        } else {
            alert('Failed to resolve appeal');
        }
    } catch(e) {
        console.error(e);
        alert('Error resolving appeal');
    }
}
