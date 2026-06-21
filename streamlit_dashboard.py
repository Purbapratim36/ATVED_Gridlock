"""
ATVED Streamlit Citation Dashboard

A beautiful, interactive dashboard for browsing traffic violations,
viewing citation details, and downloading E-Challan PDFs.

Run with:  streamlit run streamlit_dashboard.py
"""

import os
import sys
import io
import uuid
from datetime import datetime, timezone, timedelta

import streamlit as st
import pandas as pd

# Database connection (synchronous for Streamlit)
from sqlalchemy import create_engine, select, desc, func, text
from sqlalchemy.orm import Session, sessionmaker

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from atved.db.models import (
    Base, Driver, RegisteredPlate, ViolationRecord,
    ViolationType, ViolationStatus, Camera,
)

# PDF generation
from fpdf import FPDF

# ---------------------------------------------------------------------------
# Database Setup (synchronous for Streamlit)
# ---------------------------------------------------------------------------
DATABASE_URL = "postgresql://atved:atved_password@localhost:5432/atved_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine, class_=Session)

# ---------------------------------------------------------------------------
# Fine Amount Matrix
# ---------------------------------------------------------------------------
FINE_MATRIX = {
    ViolationType.RED_LIGHT: 1000,
    ViolationType.WRONG_SIDE: 1500,
    ViolationType.SPEEDING: 2000,
    ViolationType.TRIPLE_RIDING: 1000,
    ViolationType.SEATBELT: 500,
    ViolationType.HELMET: 500,
    ViolationType.ILLEGAL_PARKING: 500,
    ViolationType.STOP_LINE: 500,
}

PENALTY_MATRIX = {
    ViolationType.RED_LIGHT: 50,
    ViolationType.WRONG_SIDE: 60,
    ViolationType.SPEEDING: 40,
    ViolationType.TRIPLE_RIDING: 30,
    ViolationType.SEATBELT: 20,
    ViolationType.HELMET: 20,
    ViolationType.ILLEGAL_PARKING: 15,
    ViolationType.STOP_LINE: 10,
}


# ---------------------------------------------------------------------------
# PDF Generator
# ---------------------------------------------------------------------------
def generate_pdf(violation, driver_name, plate_text):
    """Generate a professional E-Challan PDF and return as bytes."""
    pdf = FPDF()
    pdf.add_page()

    # Header border
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

    # Challan Details Table
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(55, 10, "Challan No:", border=1, fill=False)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"  {str(violation.id)[:18]}...", border=1, ln=True)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(55, 10, "Date & Time:", border=1)
    pdf.set_font("helvetica", "", 12)
    detected = violation.detected_at.strftime('%d-%b-%Y  %I:%M:%S %p') if violation.detected_at else "N/A"
    pdf.cell(0, 10, f"  {detected}", border=1, ln=True)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(55, 10, "Location:", border=1)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"  Camera: {violation.camera_id}", border=1, ln=True)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(55, 10, "Vehicle Plate:", border=1)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"  {plate_text}", border=1, ln=True)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(55, 10, "Owner Name:", border=1)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"  {driver_name}", border=1, ln=True)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(55, 10, "Vehicle Type:", border=1)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"  {violation.vehicle_type or 'Unknown'}", border=1, ln=True)

    pdf.ln(8)

    # Violation Box
    pdf.set_fill_color(255, 230, 230)
    pdf.set_draw_color(200, 0, 0)
    pdf.set_line_width(0.8)
    pdf.rect(20, pdf.get_y(), 170, 40, "DF")

    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 12, f"VIOLATION: {violation.violation_type.value}", ln=True, align="C")

    pdf.set_font("helvetica", "", 13)
    pdf.set_text_color(0, 0, 0)
    fine = FINE_MATRIX.get(violation.violation_type, 500)
    pdf.cell(0, 10, f"Fine Amount:  Rs. {fine}/-", ln=True, align="C")

    penalty = PENALTY_MATRIX.get(violation.violation_type, 0)
    pdf.cell(0, 10, f"Traffic Score Penalty:  -{penalty} Points", ln=True, align="C")

    pdf.ln(8)

    # Confidence Score
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"AI Confidence Score: {violation.confidence_score * 100:.1f}%", ln=True, align="C")
    pdf.cell(0, 10, f"Status: {violation.status.value}", ln=True, align="C")

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
# Streamlit Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ATVED - Traffic Citation Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Dark theme overrides */
    .stApp { background-color: #0e1117; }
    
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 15px 20px;
        border-radius: 12px;
        border: 1px solid #2a2a4a;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    
    div[data-testid="stMetric"] label {
        color: #8892b0 !important;
        font-size: 14px !important;
    }
    
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #64ffda !important;
        font-size: 28px !important;
        font-weight: 700 !important;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a192f 0%, #112240 100%) !important;
        border-right: 1px solid #233554;
    }
    
    /* Headers */
    h1 { color: #ccd6f6 !important; }
    h2 { color: #8892b0 !important; }
    h3 { color: #64ffda !important; }
    
    /* Dataframe styling */
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    
    /* Download button */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #0066cc 0%, #0052a3 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 20px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #0077ee 0%, #0066cc 100%) !important;
        box-shadow: 0 4px 15px rgba(0, 102, 204, 0.4) !important;
        transform: translateY(-1px) !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🚦 ATVED Dashboard")
    st.markdown("---")
    
    page = st.radio(
        "Navigation",
        ["📊 Overview", "📋 All Citations", "🔍 Search by Plate", "👤 Driver Profiles"],
        label_visibility="collapsed",
    )
    
    st.markdown("---")
    st.markdown("##### Filters")
    
    violation_filter = st.multiselect(
        "Violation Type",
        [v.value for v in ViolationType],
        default=[],
    )
    
    status_filter = st.multiselect(
        "Status",
        [s.value for s in ViolationStatus],
        default=[],
    )


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=5)
def load_violations():
    """Load all violations from PostgreSQL."""
    with SessionLocal() as db:
        rows = db.execute(
            select(ViolationRecord).order_by(desc(ViolationRecord.detected_at)).limit(500)
        ).scalars().all()
        
        data = []
        for v in rows:
            plate = v.plate_text_encrypted.decode("utf-8") if v.plate_text_encrypted else "N/A"
            data.append({
                "id": str(v.id),
                "type": v.violation_type.value,
                "status": v.status.value,
                "detected_at": v.detected_at,
                "vehicle_type": v.vehicle_type or "Unknown",
                "confidence": round(v.confidence_score * 100, 1),
                "plate": plate,
                "fine": FINE_MATRIX.get(v.violation_type, 500),
                "camera_id": str(v.camera_id),
            })
        return data


@st.cache_data(ttl=5)
def load_stats():
    """Load aggregate statistics."""
    with SessionLocal() as db:
        total = db.execute(select(func.count(ViolationRecord.id))).scalar() or 0
        pending = db.execute(
            select(func.count(ViolationRecord.id))
            .where(ViolationRecord.status == ViolationStatus.PENDING_REVIEW)
        ).scalar() or 0
        drivers = db.execute(select(func.count(Driver.id))).scalar() or 0
        
        total_fines = 0
        breakdown = {}
        for vtype in ViolationType:
            count = db.execute(
                select(func.count(ViolationRecord.id))
                .where(ViolationRecord.violation_type == vtype)
            ).scalar() or 0
            if count > 0:
                breakdown[vtype.value] = count
                total_fines += count * FINE_MATRIX.get(vtype, 500)
        
        return {
            "total": total,
            "pending": pending,
            "drivers": drivers,
            "total_fines": total_fines,
            "breakdown": breakdown,
        }


@st.cache_data(ttl=5)
def load_drivers():
    """Load all drivers."""
    with SessionLocal() as db:
        rows = db.execute(select(Driver).order_by(Driver.traffic_score)).scalars().all()
        data = []
        for d in rows:
            plates = db.execute(
                select(RegisteredPlate).where(RegisteredPlate.driver_id == d.id)
            ).scalars().all()
            data.append({
                "id": str(d.id),
                "name": d.name,
                "email": d.email or "N/A",
                "traffic_score": d.traffic_score,
                "plates": ", ".join([p.plate_text for p in plates]),
                "registered": d.is_registered,
            })
        return data


def get_violation_by_id(vid):
    """Get a single violation record."""
    with SessionLocal() as db:
        return db.execute(
            select(ViolationRecord).where(ViolationRecord.id == vid)
        ).scalar_one_or_none()


def get_driver_for_plate(plate_text):
    """Lookup driver by plate text."""
    with SessionLocal() as db:
        driver = db.execute(
            select(Driver).join(RegisteredPlate).where(RegisteredPlate.plate_text == plate_text)
        ).scalar_one_or_none()
        return driver


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "📊 Overview":
    st.markdown("# 📊 ATVED Command Center")
    st.markdown("Real-time traffic violation monitoring and analytics")
    st.markdown("---")
    
    stats = load_stats()
    
    # Metric Cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Citations", f"{stats['total']}")
    col2.metric("Pending Review", f"{stats['pending']}")
    col3.metric("Registered Drivers", f"{stats['drivers']}")
    col4.metric("Total Fines", f"₹{stats['total_fines']:,}")
    
    st.markdown("---")
    
    # Charts
    if stats["breakdown"]:
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown("### 📈 Violations by Type")
            chart_df = pd.DataFrame(
                list(stats["breakdown"].items()),
                columns=["Violation Type", "Count"]
            )
            st.bar_chart(chart_df.set_index("Violation Type"))
        
        with col_b:
            st.markdown("### 🔄 Recent Activity")
            violations = load_violations()
            if violations:
                recent_df = pd.DataFrame(violations[:10])
                for _, row in recent_df.iterrows():
                    status_icon = "🟡" if row["status"] == "PENDING_REVIEW" else "🟢"
                    st.markdown(
                        f"{status_icon} **{row['type']}** — Plate: `{row['plate']}` — "
                        f"Confidence: {row['confidence']}% — ₹{row['fine']}"
                    )
            else:
                st.info("No violations recorded yet. Run the AI engine to start detecting!")
    else:
        st.info("No violations recorded yet. Run the AI engine to start detecting!")


elif page == "📋 All Citations":
    st.markdown("# 📋 Citation Records")
    st.markdown("Browse, filter, and download E-Challan PDFs for all recorded violations.")
    st.markdown("---")
    
    violations = load_violations()
    
    if not violations:
        st.warning("No citations found in the database. Run the AI engine on a video to generate citations.")
    else:
        # Apply filters
        filtered = violations
        if violation_filter:
            filtered = [v for v in filtered if v["type"] in violation_filter]
        if status_filter:
            filtered = [v for v in filtered if v["status"] in status_filter]
        
        st.markdown(f"**Showing {len(filtered)} citations**")
        
        # Display as cards
        for v in filtered:
            with st.expander(
                f"🚨 {v['type']}  |  Plate: {v['plate']}  |  ₹{v['fine']}  |  "
                f"{v['detected_at'].strftime('%d-%b-%Y %I:%M %p') if v['detected_at'] else 'N/A'}"
            ):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Violation:** {v['type']}")
                c1.markdown(f"**Vehicle:** {v['vehicle_type']}")
                c2.markdown(f"**Plate:** `{v['plate']}`")
                c2.markdown(f"**Confidence:** {v['confidence']}%")
                c3.markdown(f"**Fine:** ₹{v['fine']}")
                c3.markdown(f"**Status:** {v['status']}")
                
                # Download PDF Button
                record = get_violation_by_id(v["id"])
                if record:
                    driver = get_driver_for_plate(v["plate"]) if v["plate"] != "N/A" else None
                    driver_name = driver.name if driver else "UNREGISTERED"
                    
                    pdf_bytes = generate_pdf(record, driver_name, v["plate"])
                    st.download_button(
                        label="📄 Download E-Challan PDF",
                        data=pdf_bytes,
                        file_name=f"ATVED_EChallan_{v['type']}_{v['plate']}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{v['id']}",
                    )


elif page == "🔍 Search by Plate":
    st.markdown("# 🔍 Search by License Plate")
    st.markdown("Look up all violations associated with a specific vehicle registration number.")
    st.markdown("---")
    
    plate_input = st.text_input("Enter License Plate Number", placeholder="e.g. MH12AB1234")
    
    if plate_input:
        violations = load_violations()
        matches = [v for v in violations if plate_input.upper() in v["plate"].upper()]
        
        if matches:
            st.success(f"Found {len(matches)} violation(s) for plate `{plate_input.upper()}`")
            
            # Driver info
            driver = get_driver_for_plate(plate_input.upper())
            if driver:
                st.markdown("### 👤 Owner Details")
                dc1, dc2, dc3 = st.columns(3)
                dc1.metric("Name", driver.name)
                dc2.metric("Traffic Score", f"{driver.traffic_score}/1000")
                dc3.metric("Total Fines", f"₹{sum(m['fine'] for m in matches):,}")
            
            st.markdown("### 📋 Violation History")
            for v in matches:
                with st.expander(f"🚨 {v['type']} — {v['detected_at'].strftime('%d-%b-%Y') if v['detected_at'] else 'N/A'}"):
                    st.markdown(f"**Confidence:** {v['confidence']}% | **Fine:** ₹{v['fine']} | **Status:** {v['status']}")
                    
                    record = get_violation_by_id(v["id"])
                    if record:
                        driver_name = driver.name if driver else "UNREGISTERED"
                        pdf_bytes = generate_pdf(record, driver_name, v["plate"])
                        st.download_button(
                            label="📄 Download E-Challan PDF",
                            data=pdf_bytes,
                            file_name=f"ATVED_EChallan_{v['type']}_{v['plate']}.pdf",
                            mime="application/pdf",
                            key=f"search_pdf_{v['id']}",
                        )
        else:
            st.warning(f"No violations found for plate `{plate_input.upper()}`")


elif page == "👤 Driver Profiles":
    st.markdown("# 👤 Driver Profiles")
    st.markdown("View all registered and auto-detected drivers with their traffic scores.")
    st.markdown("---")
    
    drivers = load_drivers()
    
    if not drivers:
        st.info("No driver profiles yet. They are automatically created when a license plate is detected.")
    else:
        # Score distribution
        st.markdown("### 📊 Traffic Score Distribution")
        score_df = pd.DataFrame(drivers)
        st.bar_chart(score_df.set_index("name")["traffic_score"])
        
        st.markdown("---")
        st.markdown("### 📋 All Drivers")
        
        for d in drivers:
            score_color = "🟢" if d["traffic_score"] >= 800 else "🟡" if d["traffic_score"] >= 500 else "🔴"
            with st.expander(f"{score_color} {d['name']}  |  Score: {d['traffic_score']}/1000  |  Plates: {d['plates']}"):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Name:** {d['name']}")
                c2.markdown(f"**Email:** {d['email']}")
                c3.markdown(f"**Registered:** {'Yes' if d['registered'] else 'No (Auto-detected)'}")
                c1.markdown(f"**Traffic Score:** {d['traffic_score']}/1000")
                c2.markdown(f"**Plates:** `{d['plates']}`")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #4a5568; font-size: 12px;'>"
    "ATVED - Automated Traffic Violation Enforcement & Detection System | "
    "Powered by YOLOv8 + ByteTrack + PostgreSQL"
    "</div>",
    unsafe_allow_html=True,
)
