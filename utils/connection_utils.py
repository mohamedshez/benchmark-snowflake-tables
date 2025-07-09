import streamlit as st
from snowflake.snowpark import Session


def connect_to_snowflake():
    if 'session' in st.session_state:
        return st.session_state.session
    try:
        session = Session.builder.getOrCreate()
    except Exception as e1:
        try:
            section = st.secrets["account"]
            connection_parameters = {
                "account": section["account"],
                "authenticator": section["authenticator"],
                "user": section["user"],
                "database": section["database"],
                "schema": section["schema"],
                "role": section["role"],
                "warehouse": section["warehouse"]
            }
            session = Session.builder.configs(connection_parameters).create()
        except Exception as e2:
            st.error(f"Failed to connect to Snowflake. Initial error: {e1}. Secondary error: {e2}")
            return None
    st.session_state.session = session
    return session
