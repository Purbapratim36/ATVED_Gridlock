import streamlit as st
import sqlite3
import pandas as pd
import json
import streamlit.components.v1 as components

st.set_page_config(page_title="ATVED Citizen Dashboard", layout="wide", initial_sidebar_state="collapsed")

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
    
    # Fetch Drivers for Streamlit Dropdown
    drivers_df = pd.read_sql_query("SELECT id, name, aadhaar_number, traffic_score, phone, bank_name, bank_balance FROM drivers", conn)
    driver_options = drivers_df['name'].tolist()
    
    st.markdown("<h3 style='color: #8a8d9b; margin-top: -30px;'>Select a Driver to View their Citizen Dashboard:</h3>", unsafe_allow_html=True)
    selected_name = st.selectbox("", driver_options, label_visibility="collapsed")
    
    if selected_name:
        driver_row = drivers_df[drivers_df['name'] == selected_name].iloc[0]
        driver_id = driver_row['id']
        
        # Fetch Vehicles
        vehicles_df = pd.read_sql_query(f"SELECT number_plate, make, model FROM vehicles WHERE owner_id = {driver_id}", conn)
        vehicle_plates = vehicles_df['number_plate'].tolist()
        
        # Fetch Fines
        fines_df = pd.read_sql_query(f"SELECT t.*, v.violation_type FROM fine_transactions t LEFT JOIN violation_records v ON t.violation_record_id = v.id WHERE t.driver_id = {driver_id} ORDER BY t.created_at DESC", conn)
        
        # Format for JS
        txns = []
        for _, row in fines_df.iterrows():
            txns.append({
                "created_at": row['created_at'],
                "violation": {"violation_type": row['violation_type'] if pd.notnull(row['violation_type']) else "UNKNOWN"},
                "final_amount": row['final_amount'],
                "multiplier": row['multiplier'],
                "receipt_number": row['receipt_number'],
                "bank_deducted": row['bank_deducted']
            })
            
        driver_data = {
            "name": driver_row['name'],
            "license_number": driver_row['aadhaar_number'],
            "phone": driver_row['phone'],
            "traffic_score": driver_row['traffic_score'],
            "bank_name": driver_row['bank_name'],
            "bank_balance": driver_row['bank_balance'],
            "vehicles": [{"make": vehicles_df.iloc[0]['make'], "model": vehicles_df.iloc[0]['model']}] if not vehicles_df.empty else [],
            "plates": vehicle_plates
        }
        
        # Read the exact UI files
        with open('dashboard/index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        with open('dashboard/css/style.css', 'r', encoding='utf-8') as f:
            css_content = f.read()
            
        # Inject CSS
        html_content = html_content.replace('<link rel="stylesheet" href="css/style.css">', f'<style>{css_content}</style>')
        # Remove original JS
        html_content = html_content.replace('<script src="js/app.js"></script>', '')
        
        # Inject dynamic JS to bypass login and populate the exact DOM elements
        mock_js = f"""
        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            // Bypass Login Screen
            document.getElementById('loginSection').style.display = 'none';
            document.getElementById('dashboardSection').classList.remove('hidden');
            document.getElementById('navLogout').style.display = 'none';
            
            const driverData = {json.dumps(driver_data)};
            const txns = {json.dumps(txns)};
            
            // Populate Identical UI
            document.getElementById('driverName').innerText = driverData.name;
            document.getElementById('driverAadhaar').innerText = "XXXX XXXX " + String(driverData.license_number).slice(-4);
            document.getElementById('driverPhone').innerText = String(driverData.phone).replace(/\\d(?=\\d{{4}})/g, "*");
            document.getElementById('bankName').innerText = driverData.bank_name;
            document.getElementById('bankBalance').innerText = "₹" + driverData.bank_balance.toLocaleString();
            
            if (driverData.vehicles.length > 0) {{
                document.getElementById('vehicleDetails').innerText = driverData.vehicles[0].make + " " + driverData.vehicles[0].model;
            }} else {{
                document.getElementById('vehicleDetails').innerText = "No registered vehicles";
            }}
            
            const platesDiv = document.getElementById('platesContainer');
            driverData.plates.forEach(p => {{
                const span = document.createElement('span');
                span.className = 'tag';
                span.style.marginRight = '5px';
                span.style.background = 'rgba(255,255,255,0.1)';
                span.style.border = '1px solid rgba(255,255,255,0.2)';
                span.style.color = 'white';
                span.innerText = p;
                platesDiv.appendChild(span);
            }});
            
            // Replicate Dynamic Score Gauge
            const score = driverData.traffic_score;
            document.getElementById('scoreValue').innerText = score;
            
            let cat = "Excellent"; let color = "#00e676"; let mult = 1.0;
            let offset = 220 - (220 * (score / 1000));
            
            if (score < 300) {{ cat = "Suspended"; color = "#ff1744"; mult = 3.0; offset = 220; }}
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
            arc.style.strokeDashoffset = offset;
            arc.style.filter = `drop-shadow(0 0 10px ${{color}})`;
            
            // Replicate Table Exactly
            const tbody = document.querySelector('#transactionsTable tbody');
            txns.forEach(t => {{
                const tr = document.createElement('tr');
                const d = new Date(t.created_at);
                const dateStr = d.toLocaleDateString() + " " + d.toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}});
                const vType = t.violation.violation_type.toUpperCase();
                
                let actionHtml = `<a href="#" style="padding: 6px 12px; background: rgba(255,255,255,0.05); color: #8a8d9b; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; text-decoration: none; font-size: 0.8rem; pointer-events: none;">Paid - Download PDF</a>`;
                if(!t.bank_deducted) {{
                    actionHtml = `<button style="padding: 6px 12px; background: #00f0ff; color: #000; border: none; border-radius: 4px; font-weight: bold;">Pay Challan</button>`;
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
        
        final_html = html_content + mock_js
        components.html(final_html, height=1200, scrolling=True)

except Exception as e:
    st.error(f"Error: {e}")
