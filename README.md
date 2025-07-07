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

## Why the different Query types for the benchmark?:
### 1. 🔄 LEFT JOIN
Purpose:
Finds records in one table (t1) that do not have a matching row in another table (t2) based on a key (e.g. PATIENT_ID).

#### Query Logic:
```sql
Copy
Edit
SELECT COUNT(*)
FROM table t1
LEFT JOIN table t2
  ON t1.PATIENT_ID = t2.PATIENT_ID
WHERE t2.PATIENT_ID IS NULL
```

#### Usage:
- Ideal for asymmetric comparisons — i.e., "what's in A but not in B?"
- Often used for record-level diffing
- Performance depends on join key cardinality and indexing

### 2. ➖ MINUS
Purpose:
Returns rows from the first query that do not appear in the second — based on full row equality.

#### Query Logic:
```sql
sql
Copy
Edit
SELECT COUNT(*)
FROM (
  SELECT * FROM table
  MINUS
  SELECT * FROM table
)
```

#### Usage:
- Best for full-table equality checks
- Detects any difference across all columns
- Can be more expensive due to row-wise hashing and deduplication

### 3. 🔐 HASH JOIN (using HASH(*))
Purpose:
Generates a hash signature for each row and compares those — useful for quickly detecting row-level changes.

#### Query Logic:
```sql
Copy
Edit
SELECT COUNT(*)
FROM (
  SELECT HASH(*) FROM table
  MINUS
  SELECT HASH(*) FROM table
)
```

#### Usage:
- Useful when rows are large (many columns) but comparisons can be simplified
- Efficient way to diff content without needing to list each column
- May produce false negatives if hashes collide (rare but possible)
- Performance can vary based on data distribution and hash function efficiency

### 4. 📊 Benchmark Results
The results of the benchmarks are stored in a Snowflake table called `BENCHMARK_RESULTS`. You can view and download these results directly from the Streamlit app or from the confluence document.
### Query Type Comparison Table
#### This table summarizes the different query types used in the benchmark, their comparison logic, and performance notes.

| Query Type   | Compares On          | Best For                               | Performance Notes                          |
|--------------|----------------------|----------------------------------------|--------------------------------------------|
| LEFT JOIN   | One or more columns  | Key-based record matching              | Fast if join keys are indexed               |
| MINUS       | All columns          | Full row diffing (structural match)   | Slower due to full row comparison           |
| HASH JOIN   | Row hash (HASH(*))  | Lightweight full row comparison        | Faster than MINUS but depends on hash logic |

### 5. 📈 Visualisations
The app includes interactive charts to visualize the benchmark results, making it easy to compare performance across different query types and datasets.

## 🧪 Testing
### Unit Tests
Run the unit tests to ensure the app functions correctly.