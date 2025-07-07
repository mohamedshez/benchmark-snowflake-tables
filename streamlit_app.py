import streamlit as st
from snowflake.snowpark.context import get_active_session
import pandas as pd
import time

st.title("Snowflake Benchmark App ⚡")
st.write("""
Benchmark up to 6 Snowflake tables using `MINUS`, `LEFT JOIN`, or `HASH JOIN`.
Select the `Query type` and `Join key`, then view results and trends.
""")

# Active session
session = get_active_session()

# Cache table names
@st.cache_data
def get_table_names():
    rows = session.sql("SHOW TABLES IN MOHAMED_SHEZ").collect()
    return sorted([r["name"] for r in rows if r["name"].startswith("RESPONSE_TIME_")])

tables = get_table_names()
selected_tables = st.multiselect("Select up to 6 benchmark tables", tables, max_selections=6)

# Query type and join key
query_type = st.selectbox("Query type", ["MINUS", "LEFT JOIN", "HASH JOIN"])
join_key = st.selectbox("Join key", ["PATIENT_ID", "GUID"])

# Warm up warehouse
session.sql("SELECT 1").collect()

# Benchmark logic with averaging
def benchmark_table(table, query_type, join_key, trials=3):
    if query_type == "MINUS":
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT * FROM MOHAMED_SHEZ.{table}
                MINUS
                SELECT * FROM MOHAMED_SHEZ.{table}
            )
        """
    elif query_type == "LEFT JOIN":
        query = f"""
            SELECT COUNT(*) FROM MOHAMED_SHEZ.{table} t1
            LEFT JOIN MOHAMED_SHEZ.{table} t2
              ON t1.{join_key} = t2.{join_key}
            WHERE t2.{join_key} IS NULL
        """
    elif query_type == "HASH JOIN":
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT HASH(*) FROM MOHAMED_SHEZ.{table}
                MINUS
                SELECT HASH(*) FROM MOHAMED_SHEZ.{table}
            )
        """
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

# Run benchmark
if st.button("Run Benchmark") and selected_tables:
    results = []
    for table in selected_tables:
        with st.spinner(f"Benchmarking {table}..."):
            duration = benchmark_table(table, query_type, join_key)
            row_count = session.table(f"MOHAMED_SHEZ.{table}").count()

            # Insert into BENCHMARK_RESULTS
            insert_sql = f"""
                INSERT INTO MOHAMED_SHEZ.BENCHMARK_RESULTS
                (table_name, query_type, row_count, duration_seconds, warehouse, run_timestamp)
                SELECT '{table}', '{query_type}', {row_count}, {duration}, CURRENT_WAREHOUSE(), CURRENT_TIMESTAMP()
            """
            session.sql(insert_sql).collect()

            results.append({
                "Table": table,
                "Row Count": row_count,
                "Query Type": query_type,
                "Duration (s)": duration
            })

    df_results = pd.DataFrame(results)

    st.subheader("Benchmark Table")
    st.dataframe(df_results, use_container_width=True)

    st.subheader("Benchmark Duration Chart")
    chart_data = df_results[["Row Count", "Duration (s)"]].set_index("Row Count")
    st.line_chart(chart_data)

    st.download_button("Download CSV", df_results.to_csv(index=False), "benchmark_results.csv")
else:
    st.info("Select tables and click Run Benchmark")
