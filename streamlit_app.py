import streamlit as st
import sqlite3
import pandas as pd
import json
import streamlit.components.v1 as components

st.set_page_config(page_title="ATVED GridLock Portals", layout="wide", initial_sidebar_state="expanded")

st.sidebar.markdown("## ATVED GridLock Demo")
st.sidebar.markdown("This Streamlit app provides a static cloud snapshot of the local system for presentation purposes.")
portal = st.sidebar.radio("Select Portal:", ["Citizen Dashboard", "Authority Control Room"])

# Custom CSS for Streamlit hiding
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stApp { background-color: #07090f; }
</style>
""", unsafe_allow_html=True)

try:
    conn = sqlite3.connect('atved.db')

    # Read common UI files
    with open('dashboard/css/style.css', 'r', encoding='utf-8') as f:
        css_content = f.read()

    if portal == "Citizen Dashboard":
        drivers_df = pd.read_sql_query("SELECT id, name, aadhaar_number, traffic_score, phone, bank_name, bank_balance, vehicle_make, vehicle_model, vehicle_color, bank_account_masked FROM drivers", conn)
        driver_options = drivers_df['name'].tolist()
        
        st.markdown("<h3 style='color: #8a8d9b; margin-top: -30px;'>Select a Driver to View their Citizen Dashboard:</h3>", unsafe_allow_html=True)
        selected_name = st.selectbox("", driver_options, label_visibility="collapsed")
        
        if selected_name:
            driver_row = drivers_df[drivers_df['name'] == selected_name].iloc[0]
            driver_id = driver_row['id']
            
            fines_df = pd.read_sql_query(f"SELECT t.*, v.violation_type FROM fine_transactions t LEFT JOIN violation_records v ON t.violation_record_id = v.id WHERE t.driver_id = '{driver_id}' ORDER BY t.created_at DESC", conn)
            
            # --- Dynamic Score Logic ---
            dynamic_score = 190  # Base POOR score as requested
            txns = []
            for _, row in fines_df.iterrows():
                if row['bank_deducted'] == 1:
                    dynamic_score += 100
                else:
                    dynamic_score -= 20
                    
                txns.append({
                    "id": str(row['id']),
                    "created_at": row['created_at'],
                    "violation": {"violation_type": row['violation_type'] if pd.notnull(row['violation_type']) else "UNKNOWN"},
                    "final_amount": float(row['final_amount']),
                    "multiplier": row['multiplier'],
                    "receipt_number": row['receipt_number'],
                    "bank_deducted": int(row['bank_deducted'])
                })
                
            dynamic_score = max(0, min(1000, dynamic_score)) # clamp
            
            driver_data = {
                "name": driver_row['name'],
                "license_number": driver_row['aadhaar_number'],
                "phone": driver_row['phone'],
                "traffic_score": int(dynamic_score),
                "bank_name": driver_row['bank_name'],
                "bank_balance": float(driver_row['bank_balance']),
                "vehicles": [{"make": str(driver_row['vehicle_make']), "model": str(driver_row['vehicle_model'])}],
                "plates": ["AS 03 PM 7823"]
            }
            
            with open('dashboard/index.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
                
            html_content = html_content.replace('<link rel="stylesheet" href="css/style.css">', f'<style>{css_content}</style>')
            html_content = html_content.replace('<script src="js/app.js"></script>', '')
            
            # Interactive Citizen JS
            mock_js = f"""
            <script>
            // Global state for live interaction
            let globalDriver = {json.dumps(driver_data)};
            
            function updateScoreUI(score) {{
                document.getElementById('scoreValue').innerText = score;
                
                let cat = "Excellent"; let color = "#00e676"; let mult = 1.0;
                let offset = 220 - (220 * (score / 1000));
                
                if (score < 300) {{ cat = "SUSPENDED"; color = "#ff1744"; mult = 3.0; offset = 220; }}
                else if (score < 500) {{ cat = "POOR"; color = "#ff1744"; mult = 2.0; }}
                else if (score < 700) {{ cat = "WARNING"; color = "#ffb300"; mult = 1.5; }}
                
                const catElem = document.getElementById('scoreCategory');
                catElem.innerText = cat;
                catElem.style.background = color + '33';
                catElem.style.color = color;
                catElem.style.border = '1px solid ' + color;
                document.getElementById('scoreMultiplier').innerText = mult + "x";
                
                const arc = document.getElementById('scoreGaugeArc');
                arc.style.stroke = color;
                arc.style.transition = "all 1s cubic-bezier(0.4, 0, 0.2, 1)";
                arc.style.strokeDashoffset = offset;
                arc.style.filter = `drop-shadow(0 0 10px ${{color}})`;
            }}
            
            window.payChallan = function(id, amount, btn) {{
                // Simulate Payment
                globalDriver.bank_balance -= amount;
                globalDriver.traffic_score += 100;
                if(globalDriver.traffic_score > 1000) globalDriver.traffic_score = 1000;
                
                // Update UI instantly
                document.getElementById('bankBalance').innerText = "₹" + globalDriver.bank_balance.toLocaleString();
                updateScoreUI(globalDriver.traffic_score);
                
                // Update button
                const td = btn.parentElement;
                td.innerHTML = `<a href="#" style="padding: 6px 12px; background: rgba(255,255,255,0.05); color: #8a8d9b; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; text-decoration: none; font-size: 0.8rem; pointer-events: none;">Paid - Download PDF</a>`;
                
                // Animate row
                td.parentElement.style.background = "rgba(0, 230, 118, 0.1)";
                setTimeout(() => td.parentElement.style.background = "", 1000);
            }};

            document.addEventListener("DOMContentLoaded", function() {{
                document.getElementById('loginSection').style.display = 'none';
                document.getElementById('dashboardSection').classList.remove('hidden');
                if (document.getElementById('navLogout')) document.getElementById('navLogout').style.display = 'none';
                
                const txns = {json.dumps(txns)};
                
                document.getElementById('driverName').innerText = globalDriver.name;
                document.getElementById('driverAadhaar').innerText = "XXXX XXXX " + String(globalDriver.license_number).slice(-4);
                document.getElementById('driverPhone').innerText = String(globalDriver.phone).replace(/\\d(?=\\d{{4}})/g, "*");
                document.getElementById('bankName').innerText = globalDriver.bank_name;
                document.getElementById('bankBalance').innerText = "₹" + globalDriver.bank_balance.toLocaleString();
                
                if (globalDriver.vehicles.length > 0) {{
                    document.getElementById('vehicleDetails').innerText = globalDriver.vehicles[0].make + " " + globalDriver.vehicles[0].model;
                }} else {{
                    document.getElementById('vehicleDetails').innerText = "No registered vehicles";
                }}
                
                const platesDiv = document.getElementById('platesContainer');
                globalDriver.plates.forEach(p => {{
                    const span = document.createElement('span');
                    span.className = 'tag';
                    span.style.marginRight = '5px';
                    span.style.background = 'rgba(255,255,255,0.1)';
                    span.style.border = '1px solid rgba(255,255,255,0.2)';
                    span.style.color = 'white';
                    span.innerText = p;
                    platesDiv.appendChild(span);
                }});
                
                updateScoreUI(globalDriver.traffic_score);
                
                const tbody = document.querySelector('#transactionsTable tbody');
                txns.forEach(t => {{
                    const tr = document.createElement('tr');
                    const d = new Date(t.created_at);
                    const dateStr = d.toLocaleDateString() + " " + d.toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}});
                    const vType = t.violation.violation_type.toUpperCase();
                    
                    let actionHtml = `<a href="#" style="padding: 6px 12px; background: rgba(255,255,255,0.05); color: #8a8d9b; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; text-decoration: none; font-size: 0.8rem; pointer-events: none;">Paid - Download PDF</a>`;
                    if(!t.bank_deducted) {{
                        actionHtml = `<button onclick="payChallan('${{t.id}}', ${{t.final_amount}}, this)" style="padding: 6px 12px; background: #00f0ff; color: #000; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; transition: 0.2s;">Pay Challan</button>`;
                    }}
                    
                    tr.innerHTML = `
                        <td>${{dateStr}}</td>
                        <td><span class="tag" style="background: rgba(255,23,68,0.2); color: #ff1744; border: 1px solid #ff1744;">${{vType}}</span></td>
                        <td style="font-weight: bold;">- ₹${{t.final_amount.toLocaleString()}}</td>
                        <td>${{t.multiplier}}x</td>
                        <td style="font-family: monospace; color: #00f0ff;">${{t.receipt_number}}</td>
                        <td>${{actionHtml}}</td>
                    `;
                    tbody.appendChild(tr);
                }});
            }});
            </script>
            """
            
            components.html(html_content + mock_js, height=1200, scrolling=True)

    elif portal == "Authority Control Room":
        df = pd.read_sql_query('SELECT * FROM fine_transactions ORDER BY created_at DESC', conn)
        drivers = pd.read_sql_query('SELECT id, name, traffic_score FROM drivers', conn)
        
        fines_issued = len(df)
        revenue = df[df['bank_deducted'] == 1]['final_amount'].sum() if not df.empty else 0
        pending = df[df['bank_deducted'] == 0]['final_amount'].sum() if not df.empty else 0
        total_drivers = len(drivers)
        
        stats = {
            "total_fines_issued": fines_issued,
            "total_revenue": revenue,
            "pending_collection": pending,
            "registered_drivers": total_drivers
        }
        
        # Build enriched fines
        driver_map = {row['id']: {"name": row['name'], "traffic_score": row['traffic_score']} for _, row in drivers.iterrows()}
        violation_types = pd.read_sql_query('SELECT id, violation_type FROM violation_records', conn)
        v_map = {row['id']: row['violation_type'] for _, row in violation_types.iterrows()}
        
        fines = []
        for _, row in df.head(50).iterrows():
            fines.append({
                "created_at": row['created_at'],
                "driver": driver_map.get(row['driver_id'], {"name": "Unknown", "traffic_score": 0}),
                "violation": {"violation_type": v_map.get(row['violation_record_id'], "UNKNOWN")},
                "violation_record_id": row['violation_record_id']
            })
            
        with open('dashboard/authority.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        html_content = html_content.replace('<link rel="stylesheet" href="css/style.css">', f'<style>{css_content}</style>')
        html_content = html_content.replace('<script src="js/authority.js"></script>', '')
        
        # Authority JS Injection
        auth_js = f"""
        <script>
        // Animate counter
        function animateValue(id, start, end, duration, prefix) {{
            if (start === end) return;
            var range = end - start;
            var current = start;
            var increment = end > start ? 1 : -1;
            var stepTime = Math.abs(Math.floor(duration / range));
            if (stepTime < 5) stepTime = 5;
            
            var obj = document.getElementById(id);
            var timer = setInterval(function() {{
                current += increment;
                if (current >= end || current > end) {{ current = end; clearInterval(timer); }}
                obj.innerText = prefix + current.toLocaleString('en-IN');
            }}, stepTime);
        }}
        
        document.addEventListener("DOMContentLoaded", function() {{
            const stats = {json.dumps(stats)};
            const fines = {json.dumps(fines)};
            
            animateValue('statFines', 0, stats.total_fines_issued || 0, 1000, '');
            animateValue('statRevenue', 0, stats.total_revenue || 0, 1000, '₹');
            animateValue('statPending', 0, stats.pending_collection || 0, 1000, '₹');
            animateValue('statDrivers', 0, stats.registered_drivers || 0, 1000, '');
            
            const ctx = document.getElementById('violationsChart').getContext('2d');
            const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Today"];
            const baseData = [45, 52, 38, 65, 48, 55];
            const todayCount = stats.total_fines_issued || 14;
            const data = [...baseData, todayCount];

            const gradient = ctx.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, 'rgba(0, 240, 255, 0.4)');
            gradient.addColorStop(1, 'rgba(0, 240, 255, 0.0)');

            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: 'Total Violations',
                        data: data,
                        borderColor: '#00f0ff',
                        backgroundColor: gradient,
                        borderWidth: 3,
                        pointBackgroundColor: '#00f0ff',
                        pointRadius: 6,
                        fill: true,
                        tension: 0.4
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        y: {{ beginAtZero: true, grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#aaa' }} }},
                        x: {{ grid: {{ display: false }}, ticks: {{ color: '#aaa' }} }}
                    }}
                }}
            }});
            
            const tbody = document.querySelector('#violationsTable tbody');
            fines.forEach(f => {{
                const tr = document.createElement('tr');
                const d = new Date(f.created_at);
                const dName = f.driver ? f.driver.name : "Unknown";
                const score = f.driver ? f.driver.traffic_score : "--";
                const vType = f.violation ? f.violation.violation_type.toUpperCase() : "UNKNOWN";
                
                tr.innerHTML = `
                    <td style="color: var(--text-muted); font-size: 0.9rem;">${{d.toLocaleTimeString()}}</td>
                    <td>${{dName}}</td>
                    <td style="font-family: monospace; color: #00f0ff; font-weight: bold;">${{score}}</td>
                    <td><span class="tag" style="background: rgba(255,23,68,0.2); color: #ff1744; border: 1px solid #ff1744;">${{vType}}</span></td>
                    <td><a href="#" style="padding: 4px 8px; background: rgba(0, 240, 255, 0.1); color: #00f0ff; border: 1px solid #00f0ff; border-radius: 4px; text-decoration: none; font-size: 0.8rem;">View PDF</a></td>
                `;
                tbody.appendChild(tr);
            }});
        }});
        </script>
        """
        
        components.html(html_content + auth_js, height=1200, scrolling=True)

except Exception as e:
    st.error(f"Error: {e}")
