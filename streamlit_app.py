import streamlit as st
import sqlite3
import pandas as pd
import json
import base64
import glob
import os
import streamlit.components.v1 as components

st.set_page_config(page_title="ATVED GridLock Portals", layout="wide", initial_sidebar_state="collapsed")

import hashlib
import uuid

if 'current_page' not in st.session_state:
    st.session_state.current_page = "Citizen Dashboard"
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'driver_id' not in st.session_state:
    st.session_state.driver_id = None

def navigate(page):
    st.session_state.current_page = page

# Top Navigation Bar
st.markdown("<style>.nav-btn { font-size: 16px !important; margin: 0 5px; }</style>", unsafe_allow_html=True)
nav_cols = st.columns([1,1,1,1])
with nav_cols[0]:
    st.button("Citizen Portal", on_click=navigate, args=("Citizen Dashboard",), use_container_width=True)
with nav_cols[1]:
    st.button("Authority Control", on_click=navigate, args=("Authority Control Room",), use_container_width=True)
with nav_cols[2]:
    st.button("E-Challan Directory", on_click=navigate, args=("E-Challan Directory",), use_container_width=True)
with nav_cols[3]:
    if st.session_state.logged_in:
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.driver_id = None
            st.rerun()
    else:
        st.button("Login / Register", on_click=navigate, args=("Login/Register",), use_container_width=True)

st.markdown("---")
portal = st.session_state.current_page

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()




# Custom CSS for Streamlit hiding and brutalist sidebar
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');
.stApp { background-color: #f4f4f0; color: #111; font-family: 'Space Mono', monospace; }
.stSidebar { background-color: #fff; border-right: 4px solid #111; }
h1, h2, h3, p, label, span { color: #111 !important; font-family: 'Space Mono', monospace !important; }
.stButton>button { background: #ffea00; color: #111; border: 4px solid #111; border-radius: 0; box-shadow: 4px 4px 0 #111; text-transform: uppercase; font-weight: bold; }

    .glass-panel, .glow-card { transition: all 0.3s ease-in-out !important; }
    .glass-panel:hover, .glow-card:hover { 
        box-shadow: 0 0 20px rgba(0, 240, 255, 0.4) !important; 
        border-color: #00f0ff !important;
        transform: translateY(-2px);
    }
    button:hover, a:hover {
        box-shadow: 0 0 15px rgba(255, 234, 0, 0.5) !important;
    }
    /* Compensate for removed icon nodes */
    h1, h2, h3 { padding-left: 5px; }
</style>
""", unsafe_allow_html=True)

try:
    conn = sqlite3.connect('atved.db')

    brutalist_css = """
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');
    body { background-color: #f4f4f0 !important; color: #111 !important; font-family: 'Space Mono', monospace !important; }
    svg { display: none !important; }
    .blob { display: none !important; }
    .glass-panel, .glow-card { background: #fff !important; border: 4px solid #111 !important; border-radius: 0 !important; box-shadow: 8px 8px 0px #111 !important; margin-bottom: 30px !important; backdrop-filter: none !important; -webkit-backdrop-filter: none !important; padding: 30px !important; }
    nav { background: #fff !important; border-bottom: 4px solid #111 !important; margin-bottom: 40px !important; padding: 20px !important; }
    .logo { font-size: 30px !important; font-weight: 700 !important; color: #111 !important; text-transform: uppercase !important; letter-spacing: -1px; }
    h1, h2, h3, p { font-family: 'Space Mono', monospace !important; color: #111 !important; text-transform: uppercase; font-weight: 700; margin-bottom: 10px; }
    .tag, .badge { border: 2px solid #111 !important; background: #ffea00 !important; color: #111 !important; border-radius: 0 !important; box-shadow: 2px 2px 0px #111; font-weight: bold; display: inline-block; padding: 5px 10px; margin: 2px; }
    table { border-collapse: collapse; width: 100%; border: 4px solid #111; margin-top: 20px; }
    th, td { border: 2px solid #111 !important; padding: 15px !important; color: #111 !important; text-align: left; }
    th { background: #111 !important; color: #fff !important; }
    tr:nth-child(even) { background: #f4f4f0 !important; }
    tr { background: #fff !important; }
    button, a { background: #ffea00 !important; color: #111 !important; border: 3px solid #111 !important; border-radius: 0 !important; box-shadow: 4px 4px 0px #111 !important; text-transform: uppercase; font-weight: bold; padding: 10px 20px; cursor: pointer; text-decoration: none !important; transition: none !important; }
    button:active, a:active { transform: translate(4px, 4px); box-shadow: 0 0 0 #111 !important; }
    #scoreValue { font-size: 80px !important; -webkit-text-fill-color: #111 !important; background: none !important; margin-bottom: 20px; line-height: 1; }
    #bankBalance, #statRevenue, #statPending { font-size: 40px !important; -webkit-text-fill-color: #111 !important; background: none !important; }
    .gauge-container { border: 4px solid #111; padding: 40px; background: #fff; box-shadow: 8px 8px 0 #111; position: relative; margin-top: 20px; }
    .gauge-container svg { display: none !important; } /* explicitly hide SVG gauge */
    .metric-value { font-size: 40px !important; -webkit-text-fill-color: #111 !important; background: none !important; font-weight: bold; }
    #scoreCategory { margin-top: 10px; display: inline-block; }
    .glass-panel, .glow-card { transition: all 0.3s ease-in-out !important; }
    .glass-panel:hover, .glow-card:hover { 
        box-shadow: 0 0 20px rgba(0, 240, 255, 0.4) !important; 
        border-color: #00f0ff !important;
        transform: translateY(-2px);
    }
    button:hover, a:hover {
        box-shadow: 0 0 15px rgba(255, 234, 0, 0.5) !important;
    }
    /* Compensate for removed icon nodes */
    h1, h2, h3 { padding-left: 5px; }

    """
    css_content = brutalist_css

    if portal == "Login/Register":
        st.markdown("## Secure Authentication")
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            st.markdown("### Citizen Login")
            with st.form("login_form"):
                login_email = st.text_input("Email / Phone")
                login_pass = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", use_container_width=True)
                if submitted:
                    cursor = conn.cursor()
                    hashed = hash_password(login_pass)
                    cursor.execute("SELECT id FROM drivers WHERE (email=? OR phone=?) AND password_hash=?", (login_email, login_email, hashed))
                    res = cursor.fetchone()
                    if res:
                        st.session_state.logged_in = True
                        st.session_state.driver_id = res[0]
                        st.session_state.current_page = "Citizen Dashboard"
                        st.rerun()
                    else:
                        st.error("Invalid credentials!")
                    
        with tab2:
            st.markdown("### Register New Citizen")
            with st.form("register_form"):
                reg_name = st.text_input("Full Name")
                reg_aadhaar = st.text_input("Aadhaar Number (e.g. 1234 5678 9012)")
                reg_phone = st.text_input("Phone Number")
                reg_email = st.text_input("Email Address")
                reg_pass = st.text_input("Create Password", type="password")
                submitted = st.form_submit_button("Register", use_container_width=True)
                if submitted:
                    if reg_name and reg_email and reg_pass:
                        cursor = conn.cursor()
                        hashed = hash_password(reg_pass)
                        new_id = str(uuid.uuid4())
                        try:
                            cursor.execute("INSERT INTO drivers (id, name, aadhaar_number, phone, email, password_hash, traffic_score, bank_balance, is_registered) VALUES (?, ?, ?, ?, ?, ?, 1000, 50000.0, 1)", 
                                          (new_id, reg_name, reg_aadhaar, reg_phone, reg_email, hashed))
                            conn.commit()
                            st.success("Registration successful! Please login.")
                        except Exception as e:
                            st.error(f"Registration failed (Email or Aadhaar may already exist): {e}")
                    else:
                        st.error("Please fill all required fields.")

    elif portal == "Citizen Dashboard":
        if not st.session_state.logged_in:
            st.warning("Please login to view your secure Citizen Dashboard.")
            if st.button("Go to Login"):
                st.session_state.current_page = "Login/Register"
                st.rerun()
        else:
            driver_id = st.session_state.driver_id
            drivers_df = pd.read_sql_query(f"SELECT id, name, aadhaar_number, traffic_score, phone, bank_name, bank_balance, vehicle_make, vehicle_model, vehicle_color, bank_account_masked FROM drivers WHERE id='{driver_id}'", conn)
            
            if not drivers_df.empty:
                driver_row = drivers_df.iloc[0]
            
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
            
            # Traffic Animation Injection with Creative SVGs
            traffic_anim_html = """
            <style>
            @keyframes scrollRoad { from { transform: translateX(0); } to { transform: translateX(-50%); } }
            @keyframes driveCar { 0% { left: -150px; } 100% { left: 100%; } }
            @keyframes driveBike { 0% { left: -100px; } 100% { left: 100%; } }
            svg.brutal-car { display: block !important; position: absolute; }
            .traffic-animation { border-bottom: 6px solid #222; border-top: 6px solid #222; background: #607d8b; overflow: hidden; position: relative; height: 80px; margin-bottom: 30px; box-shadow: 0px 8px 0px #111; }
            .traffic-animation::before { content: ""; position: absolute; top: 50%; width: 200%; border-top: 4px dashed #fff; animation: scrollRoad 1.5s linear infinite; }
            </style>
            <div class="traffic-animation">
                <!-- Sleek Car -->
                <svg class="brutal-car" style="animation: driveCar 5s linear infinite; top: 35px; z-index: 3;" width="80" height="40" viewBox="0 0 80 40">
                    <path d="M10,25 L15,10 L35,10 L50,15 L70,18 L75,30 L5,30 Z" fill="#ff1744" stroke="#111" stroke-width="2"/>
                    <path d="M20,12 L32,12 L45,17 L20,17 Z" fill="#81d4fa" stroke="#111" stroke-width="1.5"/>
                    <circle cx="20" cy="30" r="7" fill="#333" stroke="#eee" stroke-width="2"/>
                    <circle cx="60" cy="30" r="7" fill="#333" stroke="#eee" stroke-width="2"/>
                    <circle cx="72" cy="22" r="2" fill="#fff"/> <!-- Headlight -->
                </svg>
                <!-- Sport Bike -->
                <svg class="brutal-car" style="animation: driveBike 3.5s linear infinite; animation-delay: 1.5s; top: 15px; z-index: 4;" width="55" height="35" viewBox="0 0 55 35">
                    <circle cx="15" cy="25" r="8" fill="#222" stroke="#aaa" stroke-width="2"/>
                    <circle cx="40" cy="25" r="8" fill="#222" stroke="#aaa" stroke-width="2"/>
                    <path d="M15,25 L25,10 L35,10 L40,25" fill="none" stroke="#00e5ff" stroke-width="4" stroke-linejoin="round"/>
                    <path d="M25,10 L30,5 L35,10" fill="none" stroke="#111" stroke-width="3" stroke-linejoin="round"/>
                    <circle cx="28" cy="4" r="4" fill="#ffea00"/> <!-- Rider Helmet -->
                </svg>
            </div>
            """
            
            with open('dashboard/index.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
                
            html_content = html_content.replace('<link rel="stylesheet" href="css/style.css">', f'<style>{css_content}</style>')
            html_content = html_content.replace('<script src="js/app.js"></script>', '')
            html_content = html_content.replace('</nav>', '</nav>' + traffic_anim_html)
            
            # Interactive Citizen JS
            mock_js = f"""
            <script>
            // Global state for live interaction
            let globalDriver = {json.dumps(driver_data)};
            
            function updateScoreUI(score) {{
                document.getElementById('scoreValue').innerText = score;
                
                let cat = "EXCELLENT"; let color = "#00e676"; let mult = 1.0;
                
                if (score < 300) {{ cat = "SUSPENDED"; color = "#ff1744"; mult = 3.0; }}
                else if (score < 500) {{ cat = "POOR"; color = "#ff1744"; mult = 2.0; }}
                else if (score < 700) {{ cat = "WARNING"; color = "#ffea00"; mult = 1.5; }}
                
                const catElem = document.getElementById('scoreCategory');
                catElem.innerText = cat;
                catElem.style.background = color;
                catElem.style.color = '#111';
                catElem.style.border = '2px solid #111';
                catElem.style.boxShadow = '4px 4px 0px #111';
                document.getElementById('scoreMultiplier').innerText = mult + "x";
                document.getElementById('scoreValue').style.textShadow = '4px 4px 0px ' + color;
                
                // Traffic Light Logic
                const lightRed = document.getElementById('lightRed');
                const lightYellow = document.getElementById('lightYellow');
                const lightGreen = document.getElementById('lightGreen');
                
                lightRed.style.background = '#444';
                lightYellow.style.background = '#444';
                lightGreen.style.background = '#444';
                
                lightRed.style.boxShadow = 'none';
                lightYellow.style.boxShadow = 'none';
                lightGreen.style.boxShadow = 'none';

                if (score < 500) {{
                    lightRed.style.background = '#ff1744';
                    lightRed.style.boxShadow = '0 0 20px #ff1744';
                }} else if (score < 700) {{
                    lightYellow.style.background = '#ffea00';
                    lightYellow.style.boxShadow = '0 0 20px #ffea00';
                }} else {{
                    lightGreen.style.background = '#00e676';
                    lightGreen.style.boxShadow = '0 0 20px #00e676';
                }}
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
        with st.expander("Edge Node Configuration"):
            st.caption("Control the local YOLOv8 processing node.")
            stream_type = st.radio("Select Video Source:", ["Pre-recorded Video (test2.mp4)", "Live IP Camera Stream"])
            if stream_type == "Live IP Camera Stream":
                ip_url = st.text_input("Enter IP Camera URL:", "http://192.168.1.100:8080/video")
            if st.button("Start ATVED"):
                source = "IP Camera" if stream_type == "Live IP Camera Stream" else "test2.mp4"
                st.success("System has started detecting.")
        
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
                    "violation": {"violation_type": v_map.get(row['violation_record_id'], "UNKNOWN")},
                "violation_record_id": row['violation_record_id']
            })
            
        traffic_anim_html = """
        <style>
        @keyframes scrollRoad { from { transform: translateX(0); } to { transform: translateX(-50%); } }
        @keyframes driveBus { 0% { left: -200px; } 100% { left: 100%; } }
        @keyframes driveCar { 0% { left: -150px; } 100% { left: 100%; } }
        @keyframes driveBike { 0% { left: -100px; } 100% { left: 100%; } }
        svg.brutal-car { display: block !important; position: absolute; }
        .traffic-animation { border-bottom: 6px solid #222; border-top: 6px solid #222; background: #607d8b; overflow: hidden; position: relative; height: 90px; margin-bottom: 30px; box-shadow: 0px 8px 0px #111; }
        .traffic-animation::before { content: ""; position: absolute; top: 50%; width: 200%; border-top: 4px dashed #fff; animation: scrollRoad 1.5s linear infinite; }
        </style>
        <div class="traffic-animation">
            <!-- Modern City Bus -->
            <svg class="brutal-car" style="animation: driveBus 8s linear infinite; top: 15px; z-index: 2;" width="140" height="50" viewBox="0 0 140 50">
                <rect x="5" y="5" width="130" height="35" rx="4" fill="#00e5ff" stroke="#111" stroke-width="2"/>
                <rect x="15" y="10" width="20" height="15" rx="2" fill="#e1f5fe" stroke="#111" stroke-width="1.5"/>
                <rect x="40" y="10" width="20" height="15" rx="2" fill="#e1f5fe" stroke="#111" stroke-width="1.5"/>
                <rect x="65" y="10" width="20" height="15" rx="2" fill="#e1f5fe" stroke="#111" stroke-width="1.5"/>
                <rect x="90" y="10" width="20" height="15" rx="2" fill="#e1f5fe" stroke="#111" stroke-width="1.5"/>
                <rect x="115" y="10" width="15" height="15" rx="2" fill="#81d4fa" stroke="#111" stroke-width="1.5"/> <!-- Driver window -->
                <circle cx="30" cy="40" r="8" fill="#333" stroke="#eee" stroke-width="2"/>
                <circle cx="110" cy="40" r="8" fill="#333" stroke="#eee" stroke-width="2"/>
                <rect x="130" y="25" width="5" height="5" fill="#ffea00"/> <!-- Headlight -->
            </svg>
            <!-- Sleek Car -->
            <svg class="brutal-car" style="animation: driveCar 4.5s linear infinite; animation-delay: 2s; top: 40px; z-index: 4;" width="80" height="40" viewBox="0 0 80 40">
                <path d="M10,25 L15,10 L35,10 L50,15 L70,18 L75,30 L5,30 Z" fill="#ffea00" stroke="#111" stroke-width="2"/>
                <path d="M20,12 L32,12 L45,17 L20,17 Z" fill="#81d4fa" stroke="#111" stroke-width="1.5"/>
                <circle cx="20" cy="30" r="7" fill="#333" stroke="#eee" stroke-width="2"/>
                <circle cx="60" cy="30" r="7" fill="#333" stroke="#eee" stroke-width="2"/>
                <circle cx="72" cy="22" r="2" fill="#fff"/>
            </svg>
            <!-- Sport Bike -->
            <svg class="brutal-car" style="animation: driveBike 3s linear infinite; animation-delay: 1s; top: 30px; z-index: 5;" width="55" height="35" viewBox="0 0 55 35">
                <circle cx="15" cy="25" r="8" fill="#222" stroke="#aaa" stroke-width="2"/>
                <circle cx="40" cy="25" r="8" fill="#222" stroke="#aaa" stroke-width="2"/>
                <path d="M15,25 L25,10 L35,10 L40,25" fill="none" stroke="#ff1744" stroke-width="4" stroke-linejoin="round"/>
                <path d="M25,10 L30,5 L35,10" fill="none" stroke="#111" stroke-width="3" stroke-linejoin="round"/>
                <circle cx="28" cy="4" r="4" fill="#00e5ff"/> <!-- Rider Helmet -->
            </svg>
        </div>
        """

        with open('dashboard/authority.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        html_content = html_content.replace('<link rel="stylesheet" href="css/style.css">', f'<style>{css_content}</style>')
        html_content = html_content.replace('<script src="js/authority.js"></script>', '')
        html_content = html_content.replace('</nav>', '</nav>' + traffic_anim_html)
        
        # Authority JS Injection
        auth_js = f"""
        <script>
        // Slideshow logic
        function startSlideshow() {{
            let slides = document.getElementsByClassName("det-slide");
            if(slides.length === 0) return;
            let slideIndex = 0;
            setInterval(() => {{
                for (let i = 0; i < slides.length; i++) {{ slides[i].style.display = "none"; }}
                slideIndex++;
                if (slideIndex > slides.length) {{ slideIndex = 1; }}
                slides[slideIndex-1].style.display = "block";
            }}, 2000);
            slides[0].style.display = "block";
        }}
        
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
            
            startSlideshow();
        }});
        </script>
        """
        
        # Load Images from demo_images folder
        image_files = glob.glob("demo_images/*.jpg") + glob.glob("demo_images/*.png") + glob.glob("demo_images/*.jpeg")
        slideshow_html = ""
        if image_files:
            slideshow_html += "<div class='glass-panel' style='margin-bottom: 30px;'><h3>Live Detection</h3><div style='background: #111; padding: 10px; border: 4px solid #111; text-align: center; height: 300px; display: flex; align-items: center; justify-content: center; overflow: hidden;'>"
            for img_path in image_files:
                try:
                    with open(img_path, "rb") as img_file:
                        b64_str = base64.b64encode(img_file.read()).decode()
                        ext = img_path.split('.')[-1]
                        slideshow_html += f"<img class='det-slide' src='data:image/{ext};base64,{b64_str}' style='display:none; max-width: 100%; max-height: 280px;'>"
                except Exception:
                    pass
            slideshow_html += "</div></div>"
        
        # Inject slideshow above the grid-2
        html_content = html_content.replace('<div class="grid-2">', slideshow_html + '<div class="grid-2">')
        
        components.html(html_content + auth_js, height=1500, scrolling=True)


    elif portal == "E-Challan Directory":
        st.markdown("<h1>E-Challan Directory</h1>", unsafe_allow_html=True)
        st.markdown("View all officially generated E-Challan PDF documents.")
        
        pdf_files = glob.glob("demo_output/challans/*.pdf")
        if not pdf_files:
            st.info("No E-Challans have been generated yet.")
        else:
            st.success(f"Found {len(pdf_files)} Generated E-Challans.")
            
            # Create a grid layout
            cols = st.columns(3)
            for idx, pdf_path in enumerate(pdf_files):
                filename = os.path.basename(pdf_path)
                with cols[idx % 3]:
                    st.markdown(f"**{filename}**")
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    
                    st.download_button(label=f"Download {filename}",
                                       data=pdf_bytes,
                                       file_name=filename,
                                       mime='application/pdf',
                                       key=f"dl_{idx}")
                    
                    # Optional: Inline preview using iframe and base64
                    b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="400" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                    st.markdown("---")

except Exception as e:
    st.error(f"Error: {e}")
