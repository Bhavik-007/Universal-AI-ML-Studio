# GraphQL Explorer

This Streamlit application provides an in-process Strawberry GraphQL explorer
for approved tables in the bundled SQLite database. The GraphQL schema executes
inside the Streamlit process, so a separate FastAPI/Uvicorn service is not needed.

## Run

From the repository root:

```bash
streamlit run app.py
```

Choose **GraphQL Explorer** from the main navigation.

## Configuration

- `config.toml` defines the SQLite database file and approved table names.
- `database.py` resolves the database file relative to this application folder.
- Table access is allow-listed; do not accept arbitrary table names from users.

## Query example

```graphql
query GetTableData($tableName: String!, $limit: Int!) {
  tableData(tableName: $tableName, limit: $limit) {
    tableName
    columns { name dataType }
    rows
  }
}
```
