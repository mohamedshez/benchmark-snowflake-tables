import streamlit as st
from snowflake.snowpark.context import get_active_session
import pandas as pd
import time

st.title("Snowflake Benchmark App ⚡")
st.write("""
Benchmark up to 6 Snowflake tables using `SIMPLE COUNT`, `MINUS`, `LEFT JOIN`, or `HASH JOIN`.
Select the `Query type` and `Join key`, then view results and trends.
""")
st.markdown("""
**Query Types Explained**  
- **SIMPLE COUNT**: Measures raw scan performance by counting all rows in a table. Useful for I/O benchmarking without comparisons.  
- **MINUS**: Compares two identical datasets and returns rows from the first that are **not present** in the second. Ideal for detecting changes or mismatches between snapshots.  
- **LEFT JOIN**: Joins two versions of the same table using a specified key (e.g., `GUID` or `PATIENT_ID`) and filters for rows **missing in the right table**. Great for tracking unmatched records.  
- **HASH JOIN**: Compares tables by generating a hash of each row and checking for differences. Efficient for deep row comparisons without inspecting individual columns.
""")

# --- Initialise session ---
session = get_active_session()
session.sql("SELECT 1").collect()  # Warm up the warehouse

# --- Cached metadata queries ---
@st.cache_data
def get_databases():
    rows = session.sql("SHOW DATABASES").collect()
    return sorted([r["name"] for r in rows])

@st.cache_data
def get_schemas(database):
    rows = session.sql(f"SHOW SCHEMAS IN DATABASE {database}").collect()
    return sorted([r["name"] for r in rows])

@st.cache_data
def get_tables(database, schema):
    query = f"""
        SELECT table_name 
        FROM {database}.information_schema.tables 
        WHERE table_schema = '{schema}'
        ORDER BY table_name
    """
    rows = session.sql(query).collect()
    return [r["TABLE_NAME"] for r in rows]

@st.cache_data
def get_columns(database, schema, table):
    if not (database and schema and table):
        return []
    rows = session.sql(f"SHOW COLUMNS IN {database}.{schema}.{table}").collect()
    return [r["column_name"] for r in rows]

# Database selection
databases = get_databases()
selected_db = st.selectbox("Select Database", databases, index=None, key="selected_db")

# Schema selection
schemas = get_schemas(selected_db) if selected_db else []
selected_schema = st.selectbox("Select Schema", schemas, index=None, key="selected_schema")

# Table selection
tables = get_tables(selected_db, selected_schema) if selected_db and selected_schema else []
selected_tables = st.multiselect(
    "Select up to 6 tables", tables,
    default=st.session_state.get("selected_tables", []),
    max_selections=6,
    key="selected_tables"
)

# Query type
query_type = st.selectbox(
    "Query type", ["SIMPLE COUNT", "MINUS", "LEFT JOIN", "HASH JOIN"],
    index=None, key="query_type"
)

# Join key selection (only if LEFT JOIN)
join_key = None
if query_type == "LEFT JOIN" and selected_tables and selected_db and selected_schema:
    join_key_options = get_columns(selected_db, selected_schema, selected_tables[0])
    join_key = st.selectbox("Join key", join_key_options, index=None, key="join_key")

# --- Benchmark function ---
def benchmark_table(database, schema, table, query_type, join_key, trials=3):
    full_table = f"{database}.{schema}.{table}"

    if query_type == "MINUS":
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT * FROM {full_table}
                WHERE UNIFORM(0, 1, RANDOM()) < 0.999999
                MINUS
                SELECT * FROM {full_table}
            )
        """
    elif query_type == "LEFT JOIN":
        query = f"""
            SELECT COUNT(*) FROM {full_table} t1
            LEFT JOIN {full_table} t2
              ON t1.{join_key} = t2.{join_key}
            WHERE t2.{join_key} IS NULL
        """
    elif query_type == "HASH JOIN":
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT HASH(*) FROM {full_table}
                MINUS
                SELECT HASH(*) FROM {full_table}
            )
        """
    elif query_type == "SIMPLE COUNT":
        query = f"SELECT COUNT(*) FROM {full_table}"
    else:
        raise ValueError("Unsupported query type")

    durations = []
    for _ in range(trials):
        start = time.time()
        _ = session.sql(query).collect()
        end = time.time()
        durations.append(end - start)

    avg_duration = round(sum(durations) / trials, 2)
    return avg_duration

# --- Ensure session state initialised
if "stop_benchmark" not in st.session_state:
    st.session_state.stop_benchmark = False

# --- Add Buttons side by side ---
col1, col2 = st.columns(2)

with col1:
    run_clicked = st.button("🚀 Run Benchmark")

with col2:
    stop_clicked = st.button("🛑 Stop Benchmark")
    if stop_clicked:
        st.session_state.stop_benchmark = True

# --- Run Benchmark ---
if run_clicked and selected_tables:
    st.session_state.stop_benchmark = False
    results = []
    for table in selected_tables:
        if st.session_state.stop_benchmark:
            st.warning("Benchmark stopped by user.")
            break
        with st.spinner(f"Benchmarking {table}..."):
            try:
                duration = benchmark_table(
                    selected_db, selected_schema, table,
                    query_type, join_key
                )
                row_count = session.table(f"{selected_db}.{selected_schema}.{table}").count()
                results.append({
                    "Table": table,
                    "Row Count": row_count,
                    "Query Type": query_type,
                    "Duration (s)": duration
                })
            except Exception as e:
                st.error(f"Error benchmarking {table}: {e}")
                continue

    if results:
        df_results = pd.DataFrame(results)
        st.subheader("Benchmark Table")
        st.dataframe(df_results, use_container_width=True)

        st.subheader("Benchmark Duration Chart")
        chart_data = df_results[["Row Count", "Duration (s)"]].set_index("Row Count")
        st.line_chart(chart_data)

        st.download_button("Download CSV", df_results.to_csv(index=False), "benchmark_results.csv")
else:
    st.info("Select table(s) and click ***Run Benchmark***.")
