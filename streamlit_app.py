import streamlit as st
from utils.connection_utils import connect_to_snowflake
import pandas as pd
import time
from datetime import datetime

st.set_page_config(page_title="Snowflake Benchmark App ⚡", layout="wide")

# Connect to Snowflake ---
with st.spinner("Connecting to Snowflake..."):
    session = connect_to_snowflake()

if not session:
    st.error("Unable to connect to Snowflake.")
    st.stop()

# Ensure logging table exists
def ensure_benchmark_logs_table():
    try:
        session.sql("""
            CREATE TABLE IF NOT EXISTS BENCHMARK_LOGS (
                timestamp TIMESTAMP,
                table_name STRING,
                row_count INTEGER,
                query_type STRING,
                join_key STRING,
                duration_s FLOAT
            )
        """).collect()
    except Exception as e:
        print("Warning: Could not ensure BENCHMARK_LOGS table:", e)

ensure_benchmark_logs_table()

st.title("Snowflake Benchmark App ⚡")
st.write("""
Benchmark up to 6 Snowflake tables using `SIMPLE COUNT`, `MINUS`, `LEFT JOIN`, or `HASH JOIN`.  
Select the `Query type` and `Join key`, then view results and trends.
""")
st.markdown("""
**Query Types Explained**  
- **SIMPLE COUNT**: Measures raw scan performance by counting all rows in a table.  
- **MINUS**: Returns rows from the first table that are not in the second — useful for detecting mismatches.  
- **LEFT JOIN**: Finds unmatched rows using join keys — great for change detection.  
- **HASH JOIN**: Hashes and compares rows — good for detecting any content-level changes.
""")

# Metadata fetching ---
@st.cache_data(ttl=3600)
def get_all_accessible_fq_tables():
    try:
        db_rows = session.sql("SHOW DATABASES").collect()
        dbs = [r["name"] for r in db_rows if not r["name"].upper().startswith("SNOWFLAKE")]
    except Exception as e:
        st.error(f"❌ Failed to fetch databases: {e}")
        return []

    fq_list = []
    for db in dbs:
        try:
            rows = session.sql(f"""
                SELECT table_catalog AS db, table_schema AS schema, table_name
                FROM {db}.information_schema.tables
                WHERE table_type IN ('BASE TABLE', 'VIEW')
            """).collect()

            for r in rows:
                fq = f"{r['DB']}.{r['SCHEMA']}.{r['TABLE_NAME']}"
                fq_list.append(fq)

        except Exception as e:
            # Skip databases you can't access
            st.warning(f"⚠️ Skipping {db} — {e}")
            continue

    return fq_list

@st.cache_data
def get_columns_fq(fq_table_name):
    db, schema, table = fq_table_name.split(".")
    rows = session.sql(f"SHOW COLUMNS IN {db}.{schema}.{table}").collect()
    return [r["column_name"] for r in rows]

# CSS: widen multiselect - UI Layout ---
st.markdown("""
    <style>
    .stMultiSelect > div > div {
        width: 100% !important;
        min-width: 500px;
    }
    </style>
""", unsafe_allow_html=True)

# Filter input
fq_table_names = get_all_accessible_fq_tables()
filter_text = st.text_input("🔍 Filter tables (by name, db, or schema)", "")
filtered_tables = [t for t in fq_table_names if filter_text.lower() in t.lower()]
valid_selected_tables = [t for t in st.session_state.get("selected_tables", []) if t in filtered_tables]

# Table selection
selected_tables = st.multiselect(
    "Select up to 6 tables (fully qualified)",
    filtered_tables,
    default=valid_selected_tables,
    max_selections=6,
    key="selected_tables"
)

# Table summary ---
if selected_tables:
    st.markdown("### ✅ Selected Tables Summary")
    st.dataframe(
        pd.DataFrame({"Selected Tables": selected_tables})
        .reset_index(drop=True)
        .rename_axis("No.")
        .set_index(pd.Index(range(1, len(selected_tables) + 1))),
        use_container_width=True,
        hide_index=False
    )

# Query type
query_type = st.selectbox("Query type", ["SIMPLE COUNT", "MINUS", "LEFT JOIN", "HASH JOIN"], index=None)

# Per-table join key input
table_join_keys = {}
if query_type == "LEFT JOIN" and selected_tables:
    st.markdown("### 🔑 Join Keys Per Table")
    for table in selected_tables:
        with st.expander(f"Join Key(s) for `{table}`"):
            options = get_columns_fq(table)
            keys = st.multiselect(f"Select join key(s) for {table}", options, key=f"join_key_{table}")
            if keys:
                table_join_keys[table] = keys

# Benchmark function
def benchmark_table(fq_table, query_type, join_keys=None, trials=3):
    db, schema, table = fq_table.split(".")
    full_table = f"{db}.{schema}.{table}"

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
        if not join_keys:
            raise ValueError(f"No join keys for table: {fq_table}")
        join_clause = " AND ".join([f"t1.{k} = t2.{k}" for k in join_keys])
        null_filter = " AND ".join([f"t2.{k} IS NULL" for k in join_keys])
        query = f"""
            SELECT COUNT(*) FROM {full_table} t1
            LEFT JOIN {full_table} t2 ON {join_clause}
            WHERE {null_filter}
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
        session.sql(query).collect()
        end = time.time()
        durations.append(end - start)

    return round(sum(durations) / trials, 2)

# Log benchmark result to Snowflake
def log_result_to_snowflake(row):
    try:
        insert_sql = f"""
            INSERT INTO BENCHMARK_LOGS (
                timestamp, table_name, row_count, query_type, join_key, duration_s
            ) VALUES (
                TO_TIMESTAMP('{row["timestamp"]}'), 
                '{row["table_name"]}', 
                {row["row_count"]}, 
                '{row["query_type"]}', 
                '{row["join_key"].replace("'", "''")}', 
                {row["duration_s"]}
            )
        """
        session.sql(insert_sql).collect()
    except Exception as e:
        print(f"Warning: Failed to log result for {row['table_name']}: {e}")

# Session State ---
if "stop_benchmark" not in st.session_state:
    st.session_state.stop_benchmark = False

col1, col2 = st.columns(2)
with col1:
    run_clicked = st.button("🚀 Run Benchmark")
with col2:
    stop_clicked = st.button("🛑 Stop Benchmark")
    if stop_clicked:
        st.session_state.stop_benchmark = True

# Benchmark Execution ---
if run_clicked and selected_tables:
    st.session_state.stop_benchmark = False
    results = []
    for fq_table in selected_tables:
        if st.session_state.stop_benchmark:
            st.warning("Benchmark stopped.")
            break
        with st.spinner(f"Benchmarking {fq_table}..."):
            try:
                join_keys = table_join_keys.get(fq_table) if query_type == "LEFT JOIN" else None
                duration = benchmark_table(fq_table, query_type, join_keys)
                row_count = session.table(fq_table).count()
                join_key_str = ", ".join(join_keys) if join_keys else ""
                row = {
                    "timestamp": datetime.now(),
                    "table_name": fq_table,
                    "row_count": row_count,
                    "query_type": query_type,
                    "join_key": join_key_str,
                    "duration_s": duration
                }
                results.append(row)
                log_result_to_snowflake(row)
            except Exception as e:
                st.warning(f"Skipped {fq_table} due to an error.")
                print(f"[ERROR] Benchmarking failed for {fq_table}:", e)
                continue

    if results:
        df_results = pd.DataFrame(results)
        st.subheader("📊 Benchmark Results")
        st.dataframe(df_results, use_container_width=True)
        st.download_button("Download CSV", df_results.to_csv(index=False), "benchmark_results.csv")

        st.subheader("📈 Duration Trend")
        trend = df_results[["table_name", "duration_s"]].set_index("table_name")
        st.bar_chart(trend)
