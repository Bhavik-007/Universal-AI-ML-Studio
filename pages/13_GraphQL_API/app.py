import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from auth.login_manager import login_manager
from auth.auth_guard import protect_page

st.set_page_config(
    page_title="GraphQL Explorer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
login_manager()
protect_page()

# Execute the GraphQL schema directly in this Streamlit process.
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from database import get_allowed_tables
from graphql_api import schema


def graphql_request(query: str, variables: dict | None = None):
    try:
        result = schema.execute_sync(query, variable_values=variables or {})
        if result.errors:
            st.error("GraphQL Error: " + "\n".join(str(error) for error in result.errors))
            return None
        return result.data
    except Exception as exc:
        st.error(f"Unable to execute GraphQL query: {exc}")
        return None


# ============================================================
# GET AVAILABLE TABLES
# ============================================================

def get_tables():
    try:
        return get_allowed_tables()
    except Exception as exc:
        st.error(f"Unable to read approved tables: {exc}")
        return []


# ============================================================
# GET TABLE DATA
#
# IMPORTANT:
# This matches your CURRENT GraphQL schema.
#
# TableData contains:
#   tableName
#   columns
#   rows
#
# NOT:
#   data
# ============================================================

def get_table_data(
    table_name,
    limit
):

    query = """

    query GetTableData(
        $tableName: String!,
        $limit: Int!
    ) {

        tableData(
            tableName: $tableName,
            limit: $limit
        ) {

            tableName

            columns {
                name
                dataType
            }

            rows

        }

    }

    """

    result = graphql_request(

        query,

        {
            "tableName": table_name,
            "limit": limit
        }
    )


    if not result:

        return pd.DataFrame(), []


    table_data = result["tableData"]


    # --------------------------------------------------------
    # Get column metadata
    # --------------------------------------------------------

    columns = table_data["columns"]


    column_names = [
        column["name"]
        for column in columns
    ]


    # --------------------------------------------------------
    # Get rows
    # --------------------------------------------------------

    raw_rows = table_data["rows"]


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Your GraphQL API returns rows as JSON objects.
    # Handle both dictionary and JSON-string formats.
    # --------------------------------------------------------

    processed_rows = []


    for row in raw_rows:

        if isinstance(row, dict):

            processed_rows.append(
                row
            )

        elif isinstance(row, str):

            try:

                processed_rows.append(
                    json.loads(row)
                )

            except json.JSONDecodeError:

                processed_rows.append(
                    {}
                )


    # --------------------------------------------------------
    # Create dataframe
    # --------------------------------------------------------

    df = pd.DataFrame(
        processed_rows
    )


    # --------------------------------------------------------
    # Make sure all GraphQL columns exist
    # --------------------------------------------------------

    for column in column_names:

        if column not in df.columns:

            df[column] = None


    # --------------------------------------------------------
    # Preserve database column order
    # --------------------------------------------------------

    df = df[
        column_names
    ]


    return df, columns


# ============================================================
# APPLICATION HEADER
# ============================================================

st.title("GraphQL Explorer")

st.caption(
    "In-process Strawberry GraphQL access to approved SQLite data"
)


# ============================================================
# LOAD TABLE LIST
# ============================================================

tables = get_tables()


if not tables:

    st.error(
        "No approved tables found from GraphQL API."
    )

    st.stop()


# ============================================================
# DATA SELECTION
# ============================================================

st.subheader("Data Selection")


table_col, row_col, load_col, reset_col = st.columns(
    [4, 2, 1.4, 1.2]
)


with table_col:

    selected_table = st.selectbox(
        "Select Table",
        options=tables
    )


with row_col:

    row_options = [
        100,
        500,
        1000,
        5000,
        10000,
        0
    ]

    selected_limit = st.selectbox(

        "Records",

        options=row_options,

        index=0,

        format_func=lambda x:
            "Unlimited"
            if x == 0
            else f"{x:,}"
    )

    st.caption(
        "Unlimited uses the existing GraphQL API limit setting."
    )


with load_col:

    st.write("")

    load_clicked = st.button(
        "Load Table",
        type="primary",
        width="stretch"
    )


with reset_col:

    st.write("")

    reset_clicked = st.button(
        "Reset",
        width="stretch"
    )


# ============================================================
# RESET
# ============================================================

if reset_clicked:

    for key in [
        "loaded_table",
        "loaded_limit",
        "loaded_df",
        "loaded_columns"
    ]:

        st.session_state.pop(
            key,
            None
        )

    st.rerun()


# ============================================================
# LOAD DATA
# ============================================================

if load_clicked:

    with st.spinner(
        f"Loading {selected_table}..."
    ):

        loaded_df, loaded_columns = (
            get_table_data(
                selected_table,
                selected_limit
            )
        )


    if loaded_df is not None:

        st.session_state.loaded_table = (
            selected_table
        )

        st.session_state.loaded_limit = (
            selected_limit
        )

        st.session_state.loaded_df = (
            loaded_df
        )

        st.session_state.loaded_columns = (
            loaded_columns
        )


# ============================================================
# CHECK DATA
# ============================================================

if st.session_state.get("loaded_df") is None:

    st.info(
        "Select a table and click "
        "'Load Table' to begin."
    )

    st.stop()


# ============================================================
# GET LOADED DATA
# ============================================================

df = st.session_state.loaded_df.copy()

loaded_table = (
    st.session_state.loaded_table
)

loaded_limit = (
    st.session_state.loaded_limit
)


# ============================================================
# EMPTY DATA
# ============================================================

if df.empty:

    st.warning(
        f"No records found in {loaded_table}."
    )

    st.stop()


# ============================================================
# DATA TYPE DETECTION
# ============================================================

for column in df.columns:

    if df[column].dtype == "object":

        numeric_values = pd.to_numeric(
            df[column],
            errors="coerce"
        )


        if (
            numeric_values.notna().mean()
            >= 0.95
        ):

            df[column] = numeric_values


# ============================================================
# OVERVIEW
# ============================================================

st.markdown(
    '<div class="section-title">Overview</div>',
    unsafe_allow_html=True
)

card1, card2, card3, card4 = st.columns(4)

with card1:
    st.metric(
        "Table",
        loaded_table
    )

with card2:
    st.metric(
        "Loaded Records",
        f"{len(df):,}"
    )

with card3:
    st.metric(
        "Columns",
        f"{len(df.columns):,}"
    )

with card4:
    limit_text = (
        "Unlimited"
        if loaded_limit == 0
        else f"{loaded_limit:,}"
    )

    st.metric(
        "Load Limit",
        limit_text
    )


# ============================================================
# COLUMN SELECTION
#
# UI ONLY:
# Select which existing columns are shown in the grid/CSV.
# No row/data filters are applied.
# ============================================================

st.subheader("Columns")

available_columns = list(df.columns)

selected_columns = st.multiselect(
    "Select columns",
    options=available_columns,
    default=available_columns,
    key=f"column_selector_{loaded_table}"
)

if selected_columns:

    display_df = df[selected_columns]

else:

    display_df = pd.DataFrame()


# ============================================================
# RESULT INFORMATION
# ============================================================

st.divider()


result_col, download_col = st.columns(
    [5, 1]
)


with result_col:

    st.caption(
        f"Showing {len(display_df):,} "
        f"of {len(df):,} loaded records"
    )


with download_col:

    csv_data = (
        display_df
        .to_csv(index=False)
        .encode("utf-8")
    )


    st.download_button(

        "Download CSV",

        data=csv_data,

        file_name=(
            f"{loaded_table}.csv"
        ),

        mime="text/csv",

        width="stretch"
    )


# ============================================================
# DATA TABLE
# ============================================================

st.subheader("Data")


st.dataframe(

    display_df,

    width="stretch",

    height=620,

    hide_index=True
)
