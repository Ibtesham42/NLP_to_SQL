"""
NL2SQL Clinic - Production UI
Streamlit frontend for NL2SQL API
"""

import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

# Page config
st.set_page_config(
    page_title="NL2SQL Clinic",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API configuration
API_URL = "http://localhost:8000"

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_confirm" not in st.session_state:
    st.session_state.pending_confirm = None
if "pending_sql" not in st.session_state:
    st.session_state.pending_sql = None
if "pending_result" not in st.session_state:
    st.session_state.pending_result = None

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background-color: #f5f5f5;
    }
    .main-header {
        background-color: #1e3a5f;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #1e3a5f;
        color: white;
    }
    .assistant-message {
        background-color: white;
        border: 1px solid #ddd;
    }
    .sql-block {
        background-color: #1e1e1e;
        color: #d4d4d4;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: monospace;
        font-size: 0.85rem;
        overflow-x: auto;
    }
    .risk-low {
        color: #28a745;
        font-weight: bold;
    }
    .risk-medium {
        color: #ffc107;
        font-weight: bold;
    }
    .risk-high {
        color: #dc3545;
        font-weight: bold;
    }
    .confirmation-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Header
col1, col2 = st.columns([1, 4])
with col1:
    st.markdown("### NL2SQL")
with col2:
    st.markdown("### Clinic - Natural Language to SQL Interface")

st.divider()

# Sidebar
with st.sidebar:
    st.markdown("### Example Queries")
    
    example_queries = [
        "How many patients do we have?",
        "Show me top 5 patients by total spending",
        "What is total revenue?",
        "List all doctors",
        "Show unpaid invoices",
        "How many appointments last month?",
        "Show me patient email addresses"
    ]
    
    for query in example_queries:
        if st.button(query, key=query, use_container_width=True):
            st.session_state.question_input = query
            st.rerun()
    
    st.divider()
    
    st.markdown("### System Status")
    try:
        health_response = requests.get(f"{API_URL}/health", timeout=5)
        if health_response.status_code == 200:
            health_data = health_response.json()
            st.success(f"API Status: {health_data.get('status', 'unknown')}")
            st.info(f"Cache Size: {health_data.get('cache_size', 0)}")
            if health_data.get('pending_confirm'):
                st.warning("Pending Confirmation: Yes")
    except Exception:
        st.error("API Server: Offline")
        st.stop()
    
    st.divider()
    
    st.markdown("### Features")
    st.markdown("- Intent Classification")
    st.markdown("- Risk Assessment")
    st.markdown("- Sensitive Data Protection")
    st.markdown("- Audit Logging")
    st.markdown("- Query Caching")
    st.markdown("- Rate Limiting")

# Main chat area
chat_container = st.container()

with chat_container:
    # Display chat history
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>You:</strong><br>{msg["content"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-message assistant-message">
                <strong>Assistant:</strong><br>{msg["content"]}
            </div>
            """, unsafe_allow_html=True)
            
            if msg.get("sql"):
                with st.expander("View SQL Query"):
                    st.code(msg["sql"], language="sql")
            
            if msg.get("df") is not None:
                st.dataframe(msg["df"], use_container_width=True)
                st.caption(f"Rows: {len(msg['df'])} | Latency: {msg.get('latency', 0)}ms")
            
            if msg.get("intent"):
                risk_class = f"risk-{msg.get('risk', 'low').lower()}"
                st.markdown(f'<span class="{risk_class}">Intent: {msg["intent"]} | Risk: {msg.get("risk", "LOW")}</span>', unsafe_allow_html=True)

# Confirmation dialog
if st.session_state.pending_confirm:
    with st.container():
        st.markdown("""
        <div class="confirmation-box">
            <strong>⚠️ Confirmation Required</strong><br>
            This query accesses sensitive data. Please confirm to proceed.
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.pending_sql:
            st.code(st.session_state.pending_sql, language="sql")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Confirm", type="primary", use_container_width=True):
                try:
                    confirm_response = requests.post(
                        f"{API_URL}/confirm",
                        json={"confirm": True},
                        timeout=30
                    )
                    if confirm_response.status_code == 200:
                        confirm_data = confirm_response.json()
                        if confirm_data.get("status") == "executed":
                            result = confirm_data.get("result", {})
                            
                            # Add assistant response to chat
                            df = None
                            if result.get("rows") and result.get("columns"):
                                df = pd.DataFrame(result["rows"], columns=result["columns"])
                            
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": result.get("message", "Query executed successfully"),
                                "sql": result.get("sql_query"),
                                "df": df,
                                "intent": st.session_state.pending_result.get("intent") if st.session_state.pending_result else None,
                                "risk": "MEDIUM",
                                "latency": 0
                            })
                            
                            st.session_state.pending_confirm = None
                            st.session_state.pending_sql = None
                            st.session_state.pending_result = None
                            st.rerun()
                except Exception as e:
                    st.error(f"Confirmation failed: {e}")
        
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pending_confirm = None
                st.session_state.pending_sql = None
                st.session_state.pending_result = None
                st.rerun()

# Input area
st.divider()
question_input = st.text_input(
    "Ask a question about your data:",
    key="question_input",
    placeholder="Example: How many patients do we have?",
    label_visibility="collapsed"
)

col1, col2, col3 = st.columns([6, 1, 1])
with col2:
    send_button = st.button("Send", type="primary", use_container_width=True)
with col3:
    clear_button = st.button("Clear", use_container_width=True)

if clear_button:
    st.session_state.messages = []
    st.session_state.pending_confirm = None
    st.rerun()

if send_button and question_input:
    # Add user message to chat
    st.session_state.messages.append({
        "role": "user",
        "content": question_input
    })
    
    with st.spinner("Processing your query..."):
        try:
            start_time = time.time()
            response = requests.post(
                f"{API_URL}/chat",
                json={"question": question_input},
                timeout=60
            )
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if confirmation required
                if "sensitive data" in data.get("message", "").lower():
                    st.session_state.pending_confirm = True
                    st.session_state.pending_sql = data.get("sql_query")
                    st.session_state.pending_result = data
                    st.rerun()
                else:
                    # Normal response
                    df = None
                    if data.get("rows") and data.get("columns"):
                        df = pd.DataFrame(data["rows"], columns=data["columns"])
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": data.get("message", "Query executed successfully"),
                        "sql": data.get("sql_query"),
                        "df": df,
                        "intent": data.get("intent"),
                        "risk": data.get("risk", "LOW"),
                        "latency": latency_ms
                    })
                    
                    st.rerun()
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Error: {response.status_code} - {response.text}"
                })
                st.rerun()
                
        except requests.exceptions.ConnectionError:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Error: Cannot connect to API server. Make sure it's running on port 8000."
            })
            st.rerun()
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Error: {str(e)}"
            })
            st.rerun()

# Footer
st.divider()
st.caption("Powered by Groq LLM + Ibtcode Decision Engine | Version 5.0.0")