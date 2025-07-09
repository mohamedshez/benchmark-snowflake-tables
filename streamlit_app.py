import streamlit as st
from snowflake.snowpark.context import get_active_session
from utils.connection_utils import connect_to_snowflake
import pandas as pd
import time

st.set_page_config(page_title="Snowflake Benchmark App ⚡", layout="wide")

with st.spinner("Connecting to Snowflake..."):
    session = connect_to_snowflake()

if not session:
    st.error("Unable to connect to Snowflake.")
    st.stop()

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

# --- Initialise session ---
session = get_active_session()
session.sql("SELECT 1").collect()  # Warm up the warehouse

# --- Cached metadata queries ---
@st.cache_data
def get_hierarchical_table_map():
    rows = session.sql("""
        SELECT table_catalog AS db, table_schema AS schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
        ORDER BY db, schema, table_name
    """).collect()

    # Build nested structure: {db: {schema: [tables]}}
    tree = {}
    fq_list = []
    for r in rows:
        db, schema, table = r["DB"], r["SCHEMA"], r["TABLE_NAME"]
        fq = f"{db}.{schema}.{table}"
        fq_list.append(fq)
        tree.setdefault(db, {}).setdefault(schema, []).append(fq)
    return tree, fq_list

@st.cache_data
def get_columns_fq(fq_table_name):
    parts = fq_table_name.split(".")
    if len(parts) != 3:
        return []
    db, schema, table = parts
    rows = session.sql(f"SHOW COLUMNS IN {db}.{schema}.{table}").collect()
    return [r["column_name"] for r in rows]

# --- Get hierarchical structure and table list ---
table_tree, all_fq_tables = get_hierarchical_table_map()

# --- Widen multiselect dropdown ---
st.markdown("""
    <style>
    .stMultiSelect > div > div {
        width: 100% !important;
        min-width: 500px;
    }
    </style>
""", unsafe_allow_html=True)

# --- Optional filter ---
filter_text = st.text_input("🔍 Filter tables (by name, db, or schema)", "")

flat_table_options = []
for db, schemas in table_tree.items():
    for schema, tables in schemas.items():
        for fq in tables:
            if filter_text.lower() in fq.lower():
                flat_table_options.append(fq)

# --- Table selection ---
selected_tables = st.multiselect(
    "Select up to 6 fully qualified tables (db.schema.table)",
    flat_table_options,
    default=st.session_state.get("selected_tables", []),
    max_selections=6,
    key="selected_tables"
)

# --- Summary Display ---
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

# --- Query type ---
query_type = st.selectbox(
    "Query type", ["SIMPLE COUNT", "MINUS", "LEFT JOIN", "HASH JOIN"],
    index=None, key="query_type"
)

# --- Join key (only for LEFT JOIN) ---
join_key = None
if query_type == "LEFT JOIN" and selected_tables:
    example_table = selected_tables[0]
    join_key_options = get_columns_fq(example_table)
    join_key = st.selectbox("Join key", join_key_options, index=None, key="join_key")

# --- Benchmark function ---
def benchmark_table(fq_table, query_type, join_key, trials=3):
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

# --- Session state ---
if "stop_benchmark" not in st.session_state:
    st.session_state.stop_benchmark = False

# --- Side-by-side buttons ---
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
    for fq_table in selected_tables:
        if st.session_state.stop_benchmark:
            st.warning("Benchmark stopped by user.")
            break
        with st.spinner(f"Benchmarking {fq_table}..."):
            try:
                duration = benchmark_table(fq_table, query_type, join_key)
                row_count = session.table(fq_table).count()
                results.append({
                    "Table": fq_table,
                    "Row Count": row_count,
                    "Query Type": query_type,
                    "Join Key": join_key or "",
                    "Duration (s)": duration
                })
            except Exception as e:
                st.error(f"Error benchmarking {fq_table}: {e}")
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
