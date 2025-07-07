# Snowflake Benchmark Streamlit App
This is a Streamlit-based benchmarking tool designed to measure query performance on large Snowflake datasets (up to 5M+ rows). It supports common comparison types such as:

- `MINUS`
- `LEFT JOIN`
- `HASH JOIN`

## 🔧 Features
- Select up to 6 `RESPONSE_TIME_*` tables to benchmark
- Toggle between MINUS, LEFT JOIN, and HASH JOIN
- Choose a join key (`PATIENT_ID` or `GUID`)
- View and download benchmark results
- Automatically logs results to a `BENCHMARK_RESULTS` table in Snowflake
- Includes clear dark-mode compatible charts and responsive layout

## 🚀 Getting Started
### Prerequisites
```bash
pip install streamlit snowflake-snowpark-python pandas plotly
```

### 1. Set up your environment
```bash
rm -rf venv                                                     
conda env update --file environment.yml --prune
# OR if you prefer using Python's built-in venv:
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Snowflake credentials
Create a `.streamlit/secrets.toml` file with your Snowflake credentials:
```toml
[snowflake]
account  = "123"
authenticator = "externalbrowser"
user     = "abc@diaceutics.com"
password = "12345"
role     = "DEVELOPER"
database = "RESEARCHER"
schema = "MS"
warehouse = "WAREHOUSE_XS"
```

### 3. Run the app
```bash
streamlit run streamlit_app.py
```