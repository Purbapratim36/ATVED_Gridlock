"""
ATVED Streamlit Cloud Dashboard (Self-Contained)

This version uses SQLite instead of PostgreSQL so it can be
deployed directly to Streamlit Community Cloud without Docker.

Run locally:   streamlit run streamlit_app.py
Deploy:        Push to GitHub → connect on share.streamlit.io
"""

import os
import sys
import sqlite3
import uuid
from datetime import datetime, timedelta
import random

import streamlit as st
import pandas as pd
from fpdf import FPDF

# ---------------------------------------------------------------------------
# Database Setup (SQLite - works everywhere)
# ---------------------------------------------------------------------------
DB_PATH = "atved_citations.db"

def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id TEXT PRIMARY KEY,
            violation_type TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING_REVIEW',
            confidence_score REAL,
            vehicle_type TEXT,
            plate_text TEXT,
            fine_amount INTEGER,
            penalty_points INTEGER,
            camera_location TEXT DEFAULT 'DEMO-CAM-01',
            detected_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            traffic_score INTEGER DEFAULT 1000,
            plate_text TEXT UNIQUE,
            is_registered INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def seed_demo_data():
    """Populate the database with realistic demo data if empty."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    count = c.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
    if count > 0:
        conn.close()
        return
    
    # Sample plates and owners
    sample_drivers = [
        ("MH12AB1234", "Rajesh Kumar", "rajesh.kumar@email.com"),
        ("MH14CD5678", "Priya Sharma", "priya.sharma@email.com"),
        ("KA01EF9012", "Amit Patel", "amit.patel@email.com"),
        ("DL03GH3456", "Sunita Verma", "sunita.verma@email.com"),
        ("TN09IJ7890", "Vikram Singh", "vikram.singh@email.com"),
        ("GJ05KL2345", "Neha Gupta", "neha.gupta@email.com"),
        ("UP16MN6789", "Rohit Joshi", "rohit.joshi@email.com"),
        ("RJ14OP0123", "Meera Reddy", "meera.reddy@email.com"),
    ]
    
    violation_types = [
        ("HELMET", 500, 20),
        ("TRIPLE_RIDING", 1000, 30),
        ("SPEEDING", 2000, 40),
        ("RED_LIGHT", 1000, 50),
        ("WRONG_SIDE", 1500, 60),
        ("STOP_LINE", 500, 10),
    ]
    
    vehicle_types = ["motorcycle", "car", "truck", "bus", "auto_rickshaw"]
    statuses = ["PENDING_REVIEW", "CONFIRMED", "CONFIRMED", "PENDING_REVIEW"]
    
    # Insert drivers
    for plate, name, email in sample_drivers:
        score = random.randint(600, 1000)
        c.execute(
            "INSERT INTO drivers (id, name, email, traffic_score, plate_text, is_registered) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), name, email, score, plate, 1)
        )
    
    # Generate 30+ realistic violations
    now = datetime.now()
    for i in range(35):
        plate, owner_name, _ = random.choice(sample_drivers)
        vtype, fine, penalty = random.choice(violation_types)
        
        # Motorcycles for helmet/tripling, cars for others
        if vtype in ("HELMET", "TRIPLE_RIDING"):
            v_type = "motorcycle"
        else:
            v_type = random.choice(["car", "motorcycle", "truck"])
        
        detected = now - timedelta(
            days=random.randint(0, 7),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        
        c.execute(
            "INSERT INTO violations (id, violation_type, status, confidence_score, vehicle_type, plate_text, fine_amount, penalty_points, detected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                vtype,
                random.choice(statuses),
                round(random.uniform(0.75, 0.98), 3),
                v_type,
                plate,
                fine,
                penalty,
                detected.isoformat(),
            )
        )
    
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fine & Penalty Matrix
# ---------------------------------------------------------------------------
FINE_MATRIX = {
    "RED_LIGHT": 1000,
    "WRONG_SIDE": 1500,
    "SPEEDING": 2000,
    "TRIPLE_RIDING": 1000,
    "SEATBELT": 500,
    "HELMET": 500,
    "ILLEGAL_PARKING": 500,
    "STOP_LINE": 500,
}

PENALTY_MATRIX = {
    "RED_LIGHT": 50,
    "WRONG_SIDE": 60,
    "SPEEDING": 40,
    "TRIPLE_RIDING": 30,
    "SEATBELT": 20,
    "HELMET": 20,
    "ILLEGAL_PARKING": 15,
    "STOP_LINE": 10,
}

VIOLATION_LABELS = {
    "HELMET": "🪖 No Helmet",
    "TRIPLE_RIDING": "🏍️ Triple Riding",
    "SPEEDING": "💨 Overspeeding",
    "RED_LIGHT": "🔴 Red Light Violation",
    "WRONG_SIDE": "↩️ Wrong Side Driving",
    "STOP_LINE": "🛑 Stop Line Violation",
    "SEATBELT": "🪢 No Seatbelt",
    "ILLEGAL_PARKING": "🅿️ Illegal Parking",
}


# ---------------------------------------------------------------------------
# PDF E-Challan Generator
# ---------------------------------------------------------------------------
def generate_pdf(violation_row):
    """Generate a professional E-Challan PDF and return as bytes."""
    pdf = FPDF()
    pdf.add_page()

    # Border
    pdf.set_draw_color(0, 102, 204)
    pdf.set_line_width(1.5)
    pdf.rect(10, 10, 190, 277)

    # Header
    pdf.set_font("helvetica", "B", 28)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 15, "ATVED TRAFFIC POLICE", ln=True, align="C")
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 12, "OFFICIAL E-CHALLAN", ln=True, align="C")
    pdf.set_draw_color(0, 51, 102)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y() + 2, 190, pdf.get_y() + 2)
    pdf.ln(8)

    # Details Table
    fields = [
        ("Challan No:", str(violation_row["id"])[:20] + "..."),
        ("Date & Time:", violation_row["detected_at"][:19] if violation_row["detected_at"] else "N/A"),
        ("Location:", violation_row.get("camera_location", "DEMO-CAM-01")),
        ("Vehicle Plate:", violation_row["plate_text"] or "UNKNOWN"),
        ("Vehicle Type:", violation_row["vehicle_type"] or "Unknown"),
    ]

    for label, value in fields:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(55, 10, label, border=1)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(0, 10, f"  {value}", border=1, ln=True)

    pdf.ln(8)

    # Violation Box
    pdf.set_fill_color(255, 230, 230)
    pdf.set_draw_color(200, 0, 0)
    pdf.set_line_width(0.8)
    pdf.rect(20, pdf.get_y(), 170, 40, "DF")

    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(200, 0, 0)
    vtype = violation_row["violation_type"]
    pdf.cell(0, 12, f"VIOLATION: {vtype}", ln=True, align="C")

    pdf.set_font("helvetica", "", 13)
    pdf.set_text_color(0, 0, 0)
    fine = violation_row.get("fine_amount", FINE_MATRIX.get(vtype, 500))
    pdf.cell(0, 10, f"Fine Amount:  Rs. {fine}/-", ln=True, align="C")

    penalty = violation_row.get("penalty_points", PENALTY_MATRIX.get(vtype, 0))
    pdf.cell(0, 10, f"Traffic Score Penalty:  -{penalty} Points", ln=True, align="C")

    pdf.ln(8)

    # Confidence
    pdf.set_font("helvetica", "", 12)
    conf = violation_row["confidence_score"]
    pdf.cell(0, 10, f"AI Confidence Score: {conf * 100:.1f}%", ln=True, align="C")
    pdf.cell(0, 10, f"Status: {violation_row['status']}", ln=True, align="C")

    pdf.ln(20)

    # Footer
    pdf.set_draw_color(0, 51, 102)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)
    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "This is a computer-generated E-Challan by the ATVED Automated Traffic Enforcement System.", ln=True, align="C")
    pdf.cell(0, 8, "No physical signature required. For disputes, file an appeal through the ATVED portal.", ln=True, align="C")

    return pdf.output()


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------
def load_violations():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM violations ORDER BY detected_at DESC", conn
    )
    conn.close()
    return df


def load_drivers():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM drivers ORDER BY traffic_score ASC", conn
    )
    conn.close()
    return df


def get_driver_by_plate(plate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    row = c.execute("SELECT * FROM drivers WHERE plate_text = ?", (plate,)).fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "email": row[2], "traffic_score": row[3], "plate_text": row[4]}
    return None


# ---------------------------------------------------------------------------
# Initialize
# ---------------------------------------------------------------------------
init_db()
seed_demo_data()


# ---------------------------------------------------------------------------
# Streamlit Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ATVED - Traffic Violation Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 15px 20px;
        border-radius: 12px;
        border: 1px solid #2a2a4a;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetric"] label { color: #8892b0 !important; font-size: 14px !important; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: #64ffda !important; font-size: 28px !important; font-weight: 700 !important; }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a192f 0%, #112240 100%) !important;
        border-right: 1px solid #233554;
    }

    h1 { color: #ccd6f6 !important; }
    h2 { color: #8892b0 !important; }
    h3 { color: #64ffda !important; }

    .stDownloadButton > button {
        background: linear-gradient(135deg, #0066cc 0%, #0052a3 100%) !important;
        color: white !important; border: none !important; border-radius: 8px !important;
        padding: 8px 20px !important; font-weight: 600 !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #0077ee 0%, #0066cc 100%) !important;
        box-shadow: 0 4px 15px rgba(0, 102, 204, 0.4) !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🚦 ATVED")
    st.markdown("**Automated Traffic Violation**")
    st.markdown("**Enforcement & Detection**")
    st.markdown("---")

    page = st.radio(
        "Navigate",
        ["📊 Overview", "📋 All Citations", "🔍 Search by Plate", "👤 Driver Profiles"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("##### Filters")

    all_types = ["HELMET", "TRIPLE_RIDING", "SPEEDING", "RED_LIGHT", "WRONG_SIDE", "STOP_LINE"]
    violation_filter = st.multiselect("Violation Type", all_types, default=[])

    all_statuses = ["PENDING_REVIEW", "CONFIRMED", "DISMISSED"]
    status_filter = st.multiselect("Status", all_statuses, default=[])
    
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; color:#4a5568; font-size:11px;'>"
        "Powered by YOLOv8 + ByteTrack<br>© 2026 ATVED Project</div>",
        unsafe_allow_html=True
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "📊 Overview":
    st.markdown("# 📊 ATVED Command Center")
    st.markdown("Real-time traffic violation monitoring and analytics")
    st.markdown("---")

    df = load_violations()

    if df.empty:
        st.info("No violations recorded yet. Run the AI engine to start detecting!")
    else:
        # Metrics
        total = len(df)
        pending = len(df[df["status"] == "PENDING_REVIEW"])
        total_fines = df["fine_amount"].sum()
        drivers_df = load_drivers()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Citations", f"{total}")
        c2.metric("Pending Review", f"{pending}")
        c3.metric("Registered Drivers", f"{len(drivers_df)}")
        c4.metric("Total Fines", f"₹{total_fines:,}")

        st.markdown("---")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("### 📈 Violations by Type")
            type_counts = df["violation_type"].value_counts()
            chart_df = pd.DataFrame({"Type": type_counts.index, "Count": type_counts.values})
            st.bar_chart(chart_df.set_index("Type"))

        with col_b:
            st.markdown("### 🕐 Recent Violations")
            for _, row in df.head(8).iterrows():
                icon = "🟡" if row["status"] == "PENDING_REVIEW" else "🟢"
                label = VIOLATION_LABELS.get(row["violation_type"], row["violation_type"])
                st.markdown(
                    f"{icon} **{label}** — `{row['plate_text']}` — "
                    f"{row['confidence_score']*100:.0f}% — ₹{row['fine_amount']}"
                )

        st.markdown("---")
        
        # Status breakdown
        st.markdown("### 📊 Status Breakdown")
        sc1, sc2, sc3 = st.columns(3)
        confirmed = len(df[df["status"] == "CONFIRMED"])
        dismissed = len(df[df["status"] == "DISMISSED"])
        sc1.metric("🟡 Pending", f"{pending}")
        sc2.metric("🟢 Confirmed", f"{confirmed}")
        sc3.metric("🔴 Dismissed", f"{dismissed}")


elif page == "📋 All Citations":
    st.markdown("# 📋 Citation Records")
    st.markdown("Browse, filter, and download E-Challan PDFs for all recorded violations.")
    st.markdown("---")

    df = load_violations()

    if df.empty:
        st.warning("No citations found.")
    else:
        # Apply filters
        if violation_filter:
            df = df[df["violation_type"].isin(violation_filter)]
        if status_filter:
            df = df[df["status"].isin(status_filter)]

        st.markdown(f"**Showing {len(df)} citation(s)**")

        for _, row in df.iterrows():
            label = VIOLATION_LABELS.get(row["violation_type"], row["violation_type"])
            detected = row["detected_at"][:16] if row["detected_at"] else "N/A"
            status_icon = "🟡" if row["status"] == "PENDING_REVIEW" else "🟢" if row["status"] == "CONFIRMED" else "🔴"

            with st.expander(
                f"{status_icon} {label}  |  Plate: {row['plate_text']}  |  "
                f"₹{row['fine_amount']}  |  {detected}"
            ):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Violation:** {label}")
                c1.markdown(f"**Vehicle:** {row['vehicle_type']}")
                c2.markdown(f"**Plate:** `{row['plate_text']}`")
                c2.markdown(f"**Confidence:** {row['confidence_score']*100:.1f}%")
                c3.markdown(f"**Fine:** ₹{row['fine_amount']}")
                c3.markdown(f"**Status:** {row['status']}")

                # PDF Download
                pdf_bytes = generate_pdf(row.to_dict())
                st.download_button(
                    label="📄 Download E-Challan PDF",
                    data=pdf_bytes,
                    file_name=f"ATVED_EChallan_{row['violation_type']}_{row['plate_text']}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{row['id']}",
                )


elif page == "🔍 Search by Plate":
    st.markdown("# 🔍 Search by License Plate")
    st.markdown("Look up all violations for a specific vehicle registration number.")
    st.markdown("---")

    plate_input = st.text_input("Enter License Plate Number", placeholder="e.g. MH12AB1234")

    if plate_input:
        df = load_violations()
        matches = df[df["plate_text"].str.upper().str.contains(plate_input.upper(), na=False)]

        if not matches.empty:
            st.success(f"Found {len(matches)} violation(s) for `{plate_input.upper()}`")

            # Driver info
            driver = get_driver_by_plate(plate_input.upper())
            if driver:
                st.markdown("### 👤 Owner Details")
                dc1, dc2, dc3 = st.columns(3)
                dc1.metric("Name", driver["name"])
                dc2.metric("Traffic Score", f"{driver['traffic_score']}/1000")
                dc3.metric("Total Fines", f"₹{matches['fine_amount'].sum():,}")

            st.markdown("### 📋 Violation History")
            for _, row in matches.iterrows():
                label = VIOLATION_LABELS.get(row["violation_type"], row["violation_type"])
                with st.expander(f"🚨 {label} — {row['detected_at'][:10] if row['detected_at'] else 'N/A'}"):
                    st.markdown(
                        f"**Confidence:** {row['confidence_score']*100:.1f}% | "
                        f"**Fine:** ₹{row['fine_amount']} | **Status:** {row['status']}"
                    )
                    pdf_bytes = generate_pdf(row.to_dict())
                    st.download_button(
                        label="📄 Download E-Challan PDF",
                        data=pdf_bytes,
                        file_name=f"EChallan_{row['violation_type']}_{row['plate_text']}.pdf",
                        mime="application/pdf",
                        key=f"search_{row['id']}",
                    )
        else:
            st.warning(f"No violations found for `{plate_input.upper()}`")


elif page == "👤 Driver Profiles":
    st.markdown("# 👤 Driver Profiles")
    st.markdown("View all registered and auto-detected drivers with their traffic scores.")
    st.markdown("---")

    drivers_df = load_drivers()

    if drivers_df.empty:
        st.info("No driver profiles yet.")
    else:
        # Score chart
        st.markdown("### 📊 Traffic Score Distribution")
        st.bar_chart(drivers_df.set_index("name")["traffic_score"])

        st.markdown("---")
        st.markdown("### 📋 All Drivers")

        for _, d in drivers_df.iterrows():
            score = d["traffic_score"]
            icon = "🟢" if score >= 800 else "🟡" if score >= 500 else "🔴"
            reg = "Registered" if d["is_registered"] else "Auto-detected"

            with st.expander(f"{icon} {d['name']}  |  Score: {score}/1000  |  Plate: {d['plate_text']}"):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Name:** {d['name']}")
                c2.markdown(f"**Email:** {d['email'] or 'N/A'}")
                c3.markdown(f"**Status:** {reg}")
                c1.markdown(f"**Traffic Score:** {score}/1000")
                c2.markdown(f"**Plate:** `{d['plate_text']}`")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #4a5568; font-size: 12px;'>"
    "ATVED - Automated Traffic Violation Enforcement & Detection System<br>"
    "Powered by YOLOv8 + ByteTrack | © 2026"
    "</div>",
    unsafe_allow_html=True,
)
