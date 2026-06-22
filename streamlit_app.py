import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="ATVED GridLock Dashboard", layout="wide")

st.title('ATVED GridLock Cloud Dashboard')
st.markdown("This is a static cloud snapshot of the local GridLock Database.")

try:
    conn = sqlite3.connect('atved.db')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.header('Recent Fines')
        df = pd.read_sql_query('SELECT receipt_number, driver_id, final_amount, created_at FROM fine_transactions ORDER BY created_at DESC LIMIT 50', conn)
        st.dataframe(df, use_container_width=True)
        
    with col2:
        st.header('Driver Traffic Scores')
        scores = pd.read_sql_query('SELECT name, license_number, traffic_score FROM drivers ORDER BY traffic_score ASC', conn)
        st.dataframe(scores, use_container_width=True)
except Exception as e:
    st.error(f"Could not load database: {e}")
