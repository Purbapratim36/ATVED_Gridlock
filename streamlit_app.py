import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="ATVED GridLock Control Room", layout="wide", initial_sidebar_state="collapsed")

# Inject Custom Glassmorphism CSS exactly matching the dashboard
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');

/* Hide Streamlit Default Elements */
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stApp {
    background: radial-gradient(circle at top right, #110022, #07090f);
    color: #f0f0f5;
    font-family: 'Outfit', sans-serif;
}

/* Glass Panels */
.glass-panel {
    background: rgba(20, 25, 40, 0.6);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
    margin-bottom: 20px;
}

/* Typography & Colors */
h1, h2, h3 { color: #f0f0f5 !important; font-family: 'Outfit', sans-serif !important; }
.metric-value {
    font-size: 2.5rem;
    font-weight: 800;
    margin: 10px 0;
    background: linear-gradient(90deg, #fff, #00f0ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.revenue { background: linear-gradient(90deg, #fff, #00e676); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.pending { background: linear-gradient(90deg, #fff, #ffb300); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

/* Custom Table */
table { width: 100%; border-collapse: separate; border-spacing: 0; color: #f0f0f5; margin-top: 15px; }
th { text-align: left; padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.08); color: #8a8d9b; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; }
td { padding: 12px 15px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.95rem; }
tr:hover { background: rgba(255,255,255,0.02); }

.tag { padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
.tag-helmet { background: rgba(0,240,255,0.2); color: #00f0ff; border: 1px solid #00f0ff; }
</style>
""", unsafe_allow_html=True)

# Top Header
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; margin-top: -30px; margin-bottom: 30px;">
    <div>
        <h1 style="font-size: 32px; margin-bottom: 5px;">Live Control Room</h1>
        <p style="color: #8a8d9b;">Real-time monitoring, analytics, and network health.</p>
    </div>
    <span class="tag tag-helmet">Live Connection Active</span>
</div>
""", unsafe_allow_html=True)

try:
    conn = sqlite3.connect('atved.db')
    
    # Calculate Metrics
    df = pd.read_sql_query('SELECT * FROM fine_transactions ORDER BY created_at DESC', conn)
    drivers = pd.read_sql_query('SELECT * FROM drivers', conn)
    
    fines_issued = len(df)
    revenue = df[df['bank_deducted'] == 1]['final_amount'].sum() if not df.empty else 0
    pending = df[df['bank_deducted'] == 0]['final_amount'].sum() if not df.empty else 0
    total_drivers = len(drivers)

    # Render KPI Cards in a Glass Grid
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="glass-panel"><h3>Fines Issued</h3><div class="metric-value">{fines_issued}</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="glass-panel"><h3>Revenue Generated</h3><div class="metric-value revenue">₹{revenue:,.0f}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="glass-panel"><h3>Pending Collection</h3><div class="metric-value pending">₹{pending:,.0f}</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="glass-panel"><h3>Registered Drivers</h3><div class="metric-value">{total_drivers}</div></div>', unsafe_allow_html=True)

    # Render Glass Tables
    col_left, col_right = st.columns([1.5, 1])
    
    with col_left:
        st.markdown('<div class="glass-panel"><h3>🚨 Live Violation Feed</h3>', unsafe_allow_html=True)
        if not df.empty:
            html = "<table><tr><th>Time</th><th>Receipt ID</th><th>Amount</th><th>Status</th></tr>"
            for _, row in df.head(15).iterrows():
                status = "Paid" if row['bank_deducted'] else "Pending"
                color = "#00e676" if row['bank_deducted'] else "#ffb300"
                html += f"<tr><td>{row['created_at'][:19]}</td><td>{row['receipt_number']}</td><td>₹{row['final_amount']}</td><td><span style='color:{color}; font-weight:bold; background:rgba(255,255,255,0.05); padding: 4px 8px; border-radius:4px;'>{status}</span></td></tr>"
            html += "</table></div>"
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.markdown("<p style='color:#8a8d9b'>No violations recorded yet.</p></div>", unsafe_allow_html=True)
            
    with col_right:
        st.markdown('<div class="glass-panel"><h3>🚦 Driver Traffic Scores</h3>', unsafe_allow_html=True)
        if not drivers.empty:
            html = "<table><tr><th>Name</th><th>Score</th></tr>"
            for _, row in drivers.sort_values('traffic_score').head(15).iterrows():
                html += f"<tr><td>{row['name']}</td><td style='font-family:monospace; color:#00f0ff; font-weight:bold;'>{row['traffic_score']}</td></tr>"
            html += "</table></div>"
            st.markdown(html, unsafe_allow_html=True)

except Exception as e:
    st.error(f"Could not load database: {e}")
