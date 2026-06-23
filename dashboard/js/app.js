const API_BASE = window.location.origin + "/api/v1";
let currentAadhaar = "";
let chartInstance = null;

// Utility to format Aadhaar/Phone on the fly
function formatAadhaar(raw) {
    // Just return the raw string so it works for both 10-digit mobile and 12-digit Aadhaar
    return raw.trim();
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
            document.getElementById('loginError').innerText = data.detail || "ID not found in database.";
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
        
        // Remove all badge colors first
        catElem.classList.remove('badge-success', 'badge-warning', 'badge-danger');
        
        let color = "var(--success)";
        if (driver.traffic_score < 400) {
            color = "var(--danger)";
            catElem.classList.add('badge-danger');
        }
        else if (driver.traffic_score < 600) {
            color = "var(--warning)";
            catElem.classList.add('badge-warning');
        }
        else {
            color = "var(--success)";
            catElem.classList.add('badge-success');
        }

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
                // Base row HTML without action column
                tr.innerHTML = `
                    <td>${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</td>
                    <td><span class="badge badge-danger">${t.violation_type.replace('_', ' ')}</span></td>
                    <td style="font-weight:bold; color: ${t.bank_deducted ? 'var(--text-muted)' : 'var(--danger)'};">${t.bank_deducted ? '-' : ''} ₹${t.final_amount.toLocaleString('en-IN')}</td>
                    <td>${t.multiplier}x</td>
                    <td style="font-family:monospace; color:var(--accent-primary);">${t.receipt_number}</td>
                `;

                // Action Column
                const tdAction = document.createElement('td');
                if (t.bank_deducted) {
                    tdAction.innerHTML = `<a href="${window.location.origin}/pdf/${t.violation_record_id}.pdf" target="_blank" style="padding: 6px 12px; background: var(--glass-border); color: var(--text-muted); border: 1px solid var(--text-muted); border-radius: 4px; text-decoration: none; font-size: 0.8rem; font-weight: bold; pointer-events: none; opacity: 0.7;">Paid - Download PDF</a>`;
                } else {
                    const payBtn = document.createElement('button');
                    payBtn.textContent = 'Pay Challan';
                    payBtn.style.padding = '8px 16px';
                    payBtn.style.background = 'var(--accent-primary)';
                    payBtn.style.color = 'var(--bg-dark)';
                    payBtn.style.border = 'none';
                    payBtn.style.borderRadius = '4px';
                    payBtn.style.fontSize = '0.85rem';
                    payBtn.style.fontWeight = 'bold';
                    payBtn.style.cursor = 'pointer';
                    payBtn.style.boxShadow = '0 0 10px rgba(0, 240, 255, 0.4)';
                    payBtn.style.transition = 'transform 0.2s';
                    
                    // Specific user request: use event listeners
                    payBtn.addEventListener('click', () => {
                        payChallan(t.id);
                    });

                    tdAction.appendChild(payBtn);
                }
                tr.appendChild(tdAction);
                
                tbody.appendChild(tr);
            });
        }

    } catch (err) {
        console.error("Dashboard error:", err);
    }
}

function drawGauge(score, color) {
    const gaugeArc = document.getElementById('scoreGaugeArc');
    if (!gaugeArc) return;

    // Circumference of the arc is roughly 220
    const maxDash = 220;
    // Calculate how much of the arc should be empty
    const offset = maxDash - (score / 1000) * maxDash;
    
    // Animate via CSS
    gaugeArc.style.stroke = color;
    gaugeArc.style.filter = `drop-shadow(0 0 15px ${color})`;
    
    // Small delay to allow CSS transition to kick in on initial load
    setTimeout(() => {
        gaugeArc.style.strokeDashoffset = offset;
    }, 100);
}

// Auto-login check
window.onload = () => {
    if (localStorage.getItem("atved_aadhaar")) {
        loadDashboard();
    }
};

// Pay Challan feature
async function payChallan(transactionId) {
    try {
        const res = await fetch(`${API_BASE}/fines/${transactionId}/pay`, {
            method: 'POST'
        });
        
        if (res.ok) {
            const data = await res.json();
            // Animate score boost locally before reload
            const scoreVal = document.getElementById('scoreValue');
            if (scoreVal) {
                scoreVal.style.color = "var(--success)";
                scoreVal.style.textShadow = "0 0 20px var(--success)";
            }
            // Reload the dashboard to show new state
            setTimeout(() => {
                loadDashboard();
            }, 800);
        } else {
            const err = await res.json();
            alert("Payment failed: " + (err.detail || "Unknown error"));
        }
    } catch (err) {
        console.error("Payment error:", err);
        alert("Failed to connect to server.");
    }
}
