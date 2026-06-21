/**
 * ATVED Citizen Portal Application
 * Fetches user profile, traffic score, and personal violations.
 */

const API_BASE_URL = 'http://localhost:8000/api/v1';
const MOCK_USER_EMAIL = 'john@example.com'; // Hardcoded for demo

let scoreGauge = null;

document.addEventListener('DOMContentLoaded', () => {
    initGauge();
    refreshData();
});

async function refreshData() {
    try {
        await fetchUserProfile();
        await fetchViolations();
    } catch (err) {
        console.error("Failed to fetch data:", err);
    }
}

async function fetchUserProfile() {
    const res = await fetch(`${API_BASE_URL}/drivers/profile?email=${MOCK_USER_EMAIL}`);
    if (!res.ok) {
        // If not found, score is pending/unknown
        updateGauge(1000); // Default
        return;
    }
    const profile = await res.json();
    
    document.getElementById('userName').textContent = profile.name;
    document.getElementById('userAvatar').textContent = profile.name.split(' ').map(n => n[0]).join('');
    document.getElementById('userPlates').textContent = profile.registered_plates.join(', ');
    
    updateGauge(profile.traffic_score);
}

async function fetchViolations() {
    const res = await fetch(`${API_BASE_URL}/drivers/violations?email=${MOCK_USER_EMAIL}`);
    const tbody = document.querySelector('#challansTable tbody');
    
    if (!res.ok) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px;">Error loading challans.</td></tr>';
        return;
    }
    
    const violations = await res.json();
    tbody.innerHTML = '';
    
    if (violations.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px;">Great job! You have 0 traffic violations.</td></tr>';
        return;
    }
    
    violations.forEach(v => {
        const tr = document.createElement('tr');
        const badgeClass = v.status.includes('PENDING') ? 'pending' : 'confirmed';
        const dateStr = new Date(v.detected_at).toLocaleString();
        let actionBtn = '';
        if (v.status !== 'DISMISSED' && v.status !== 'PENDING_REVIEW') {
            actionBtn = `<button class="btn" style="padding: 6px 12px; font-size: 0.8rem; background: transparent; border: 1px solid var(--border-color);" onclick="openDisputeModal('${v.id}')">Dispute</button>`;
        }
        
        tr.innerHTML = `
            <td>${dateStr}</td>
            <td><span style="font-weight: 500;">${v.type.replace('_', ' ')}</span></td>
            <td style="font-family: monospace;">${v.plate}</td>
            <td><span class="badge ${badgeClass}">${v.status.replace('_', ' ')}</span></td>
            <td>${actionBtn}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Modal Logic
let currentDisputeId = null;

function openDisputeModal(challanId) {
    currentDisputeId = challanId;
    document.getElementById('disputeChallanId').textContent = challanId;
    document.getElementById('disputeReason').value = '';
    document.getElementById('disputeModal').style.display = 'block';
}

function closeDisputeModal() {
    document.getElementById('disputeModal').style.display = 'none';
    currentDisputeId = null;
}

async function submitDispute() {
    const reason = document.getElementById('disputeReason').value;
    if (!reason) { alert("Please provide a reason."); return; }
    
    try {
        const res = await fetch(`${API_BASE_URL}/appeals`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ violation_id: currentDisputeId, reason: reason })
        });
        if (res.ok) {
            closeDisputeModal();
            refreshData();
        } else {
            alert("Failed to submit dispute.");
        }
    } catch (e) {
        console.error(e);
        alert("Error submitting dispute.");
    }
}

function initGauge() {
    const ctx = document.getElementById('scoreGauge').getContext('2d');
    
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = "'Inter', sans-serif";
    
    scoreGauge = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [1000, 0], // Score, Remaining
                backgroundColor: ['#10b981', 'rgba(255,255,255,0.05)'],
                borderWidth: 0,
                circumference: 180,
                rotation: 270,
                cutout: '80%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { tooltip: { enabled: false }, legend: { display: false } }
        }
    });
}

function updateGauge(score) {
    const el = document.getElementById('currentScore');
    
    // Animate score number
    let startScore = parseInt(el.textContent) || 0;
    const duration = 1000;
    const startTime = performance.now();
    
    function animate(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        const current = Math.floor(startScore + (score - startScore) * progress);
        el.textContent = current;
        
        // Color coding
        if (current >= 800) el.style.color = 'var(--status-success)';
        else if (current >= 600) el.style.color = 'var(--status-warning)';
        else el.style.color = 'var(--status-danger)';
        
        if (progress < 1) requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);
    
    // Update chart
    let color = '#ef4444'; // Red
    if (score >= 800) color = '#10b981'; // Green
    else if (score >= 600) color = '#f59e0b'; // Yellow
    
    scoreGauge.data.datasets[0].data = [score, 1000 - score];
    scoreGauge.data.datasets[0].backgroundColor[0] = color;
    scoreGauge.update();
}
