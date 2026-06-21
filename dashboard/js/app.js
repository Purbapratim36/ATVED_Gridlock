const API_BASE = "http://localhost:8000/api/v1";
let currentAadhaar = "";
let chartInstance = null;

// Utility to format Aadhaar on the fly
function formatAadhaar(raw) {
    const clean = raw.replace(/\s+/g, '');
    let formatted = '';
    for (let i = 0; i < clean.length; i += 4) {
        formatted += clean.substring(i, i + 4) + ' ';
    }
    return formatted.trim();
}

async function requestOTP() {
    const rawInput = document.getElementById('aadhaarInput').value;
    if (!rawInput) return;
    
    const formatted = formatAadhaar(rawInput);
    document.getElementById('loginError').innerText = "";

    try {
        const res = await fetch(`${API_BASE}/auth/aadhaar-login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ aadhaar_number: formatted })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            currentAadhaar = formatted;
            document.getElementById('stepAadhaar').classList.add('hidden');
            document.getElementById('stepOTP').classList.remove('hidden');
            document.getElementById('otpMessage').innerText = `OTP sent securely to ${data.masked_phone}`;
            document.getElementById('demoOtpHint').innerText = data.demo_otp;
        } else {
            document.getElementById('loginError').innerText = data.detail || "Aadhaar not found in database.";
        }
    } catch (err) {
        document.getElementById('loginError').innerText = "Unable to connect to the ATVED API Server.";
    }
}

async function verifyOTP() {
    const otp = document.getElementById('otpInput').value;
    if (!otp) return;

    try {
        const res = await fetch(`${API_BASE}/auth/verify-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ aadhaar_number: currentAadhaar, otp: otp })
        });
        
        const data = await res.json();
        
        if (res.ok && data.driver) {
            // Save to local storage
            localStorage.setItem("atved_aadhaar", currentAadhaar);
            loadDashboard();
        } else {
            alert("Invalid OTP");
        }
    } catch (err) {
        console.error(err);
    }
}

function logout() {
    localStorage.removeItem("atved_aadhaar");
    currentAadhaar = "";
    document.getElementById('dashboardSection').classList.add('hidden');
    document.getElementById('loginSection').classList.remove('hidden');
    document.getElementById('stepOTP').classList.add('hidden');
    document.getElementById('stepAadhaar').classList.remove('hidden');
    document.getElementById('navLogout').classList.add('hidden');
    document.getElementById('aadhaarInput').value = "";
    document.getElementById('otpInput').value = "";
}

async function loadDashboard() {
    const aadhaar = localStorage.getItem("atved_aadhaar");
    if (!aadhaar) return;

    document.getElementById('loginSection').classList.add('hidden');
    document.getElementById('dashboardSection').classList.remove('hidden');
    document.getElementById('navLogout').classList.remove('hidden');

    try {
        // Fetch Profile
        const resProfile = await fetch(`${API_BASE}/drivers/profile?aadhaar=${encodeURIComponent(aadhaar)}`);
        const driver = await resProfile.json();

        // Populate Top Data
        document.getElementById('driverName').innerText = driver.name;
        document.getElementById('driverAadhaar').innerText = driver.aadhaar_masked;
        document.getElementById('driverPhone').innerText = driver.phone;

        // Bank
        document.getElementById('bankName').innerText = driver.bank_name;
        document.getElementById('bankAccount').innerText = driver.bank_account_masked;
        document.getElementById('bankBalance').innerText = `₹${driver.bank_balance.toLocaleString('en-IN')}`;
        
        // Vehicle
        document.getElementById('vehicleDetails').innerText = `${driver.vehicle_make} ${driver.vehicle_model} (${driver.vehicle_color})`;
        
        const platesDiv = document.getElementById('platesContainer');
        platesDiv.innerHTML = "";
        driver.registered_plates.forEach(p => {
            const span = document.createElement('span');
            span.className = 'tag';
            span.style.background = 'rgba(255,255,255,0.1)';
            span.style.border = '1px solid var(--glass-border)';
            span.style.marginRight = '10px';
            span.innerText = p;
            platesDiv.appendChild(span);
        });

        // Score Gauge
        document.getElementById('scoreValue').innerText = driver.traffic_score;
        document.getElementById('scoreMultiplier').innerText = `${driver.current_multiplier}x`;
        const catElem = document.getElementById('scoreCategory');
        catElem.innerText = driver.score_category;
        
        let color = "#00e676";
        if (driver.traffic_score < 400) color = "#ff1744";
        else if (driver.traffic_score < 600) color = "#ffb300";
        else if (driver.traffic_score < 800) color = "#00f0ff";
        
        catElem.style.background = `${color}33`;
        catElem.style.color = color;
        catElem.style.border = `1px solid ${color}`;

        drawGauge(driver.traffic_score, color);

        // Fetch Transactions
        const resTx = await fetch(`${API_BASE}/drivers/transactions?aadhaar=${encodeURIComponent(aadhaar)}`);
        const txns = await resTx.json();
        
        const tbody = document.querySelector('#transactionsTable tbody');
        tbody.innerHTML = "";

        if (txns.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--success);">No fines recorded! Good job!</td></tr>`;
        } else {
            txns.forEach(t => {
                const tr = document.createElement('tr');
                const d = new Date(t.created_at);
                tr.innerHTML = `
                    <td>${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</td>
                    <td><span class="tag" style="background: rgba(255,23,68,0.2); color: var(--danger); border: 1px solid var(--danger);">${t.violation_type.replace('_', ' ')}</span></td>
                    <td style="font-weight:bold; color: var(--danger);">- ₹${t.final_amount.toLocaleString('en-IN')}</td>
                    <td>${t.multiplier}x</td>
                    <td style="font-family:monospace; color:var(--accent-primary);">${t.receipt_number}</td>
                `;
                tbody.appendChild(tr);
            });
        }

    } catch (err) {
        console.error("Dashboard error:", err);
    }
}

function drawGauge(score, color) {
    const ctx = document.getElementById('scoreChart').getContext('2d');
    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [score, 1000 - score],
                backgroundColor: [color, 'rgba(255,255,255,0.05)'],
                borderWidth: 0,
                circumference: 180,
                rotation: 270
            }]
        },
        options: {
            responsive: true,
            cutout: '85%',
            plugins: { tooltip: { enabled: false }, legend: { display: false } },
            animation: { animateRotate: true, animateScale: true }
        }
    });
}

// Auto-login check
window.onload = () => {
    if (localStorage.getItem("atved_aadhaar")) {
        loadDashboard();
    }
};
