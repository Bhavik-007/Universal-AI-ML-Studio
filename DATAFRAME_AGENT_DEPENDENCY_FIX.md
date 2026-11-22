# Shared DataFrame-agent dependency fix

## Root cause
Both File Q&A and API Analyzer use LangChain's pandas DataFrame agent. LangChain renders DataFrame samples as Markdown during agent construction; this path requires the optional `tabulate` package. The missing package caused File Q&A to show a misleading file-read error and API Analyzer to show a misleading API-request error even after the API response was successfully received.

## Platform-wide correction
- `tabulate>=0.9,<1.0` is declared in the root `requirements.txt`.
- A shared factory at `universal_ai_studio/ai_platform/dataframe_agent.py` checks the dependency and creates the LangChain DataFrame agent.
- File Q&A and API Analyzer now use that same factory.
- If agent initialization fails, the uploaded file/API response remains available and the UI reports an AI-analysis initialization problem rather than claiming the file/API request failed.
- New future modules that pass pandas DataFrames to LangChain agents should call `create_dataframe_agent()` instead of importing `create_pandas_dataframe_agent` directly.

## Apply the dependency in an existing environment
Run from the project root and the same virtual environment used to launch Streamlit:

```powershell
python -m pip install "tabulate>=0.9,<1.0"
python -m pip install -r requirements.txt
```

Restart the Streamlit process after installation.

## Validation
- 5 focused regression tests passed.
- Modified Python modules compiled successfully.
- ZIP archive integrity checked.
- Live API calls and configured LLM provider execution were not available in the build environment and must be verified in deployment.
