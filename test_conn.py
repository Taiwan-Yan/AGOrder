import streamlit as st
from streamlit_gsheets import GSheetsConnection

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(worksheet="Products")
    print("✅ Connection Successful!")
    print(df.head())
except Exception as e:
    print("❌ Connection Failed:")
    print(e)
