# Dynamic module registration

Universal AI Studio keeps the 18 existing application modules in the built-in registry. Administrators can also register an existing Streamlit page without editing `app.py` or the built-in registry.

## Register through the UI

1. Sign in with an administrator account.
2. Open **Feature Management**.
3. Expand **Register an existing application page**.
4. Enter a unique lowercase module key, display name, relative page path under `pages/`, category, and comma-separated Python import names.
5. Select **Register module**.
6. The module is discovered from a JSON manifest and remains disabled by default.
7. Install its dependencies, then enable it in Feature Management.

The application must already exist in the repository. The registration UI does not upload or execute arbitrary code during discovery.

## Manifest format

A manifest is stored as `config/modules/<module_key>.json`:

```json
{
  "key": "customer_insights",
  "name": "Customer Insights",
  "path": "pages/customer_insights/app.py",
  "category": "Analytics",
  "required_permission": "applications.use",
  "dependencies": ["streamlit", "pandas", "plotly"]
}
```

Rules:

- `key` must be unique and lowercase; it becomes the navigation route.
- `path` must be a relative `.py` file under the repository's `pages/` directory.
- The entry point must exist inside the repository. Path traversal and external paths are rejected.
- Dependencies use Python import names, not necessarily PyPI distribution names (`sklearn`, not `scikit-learn`).
- Newly discovered modules are disabled by default.
- Discovery reads JSON metadata only. The page's Python code runs only when the user navigates to that registered page.
- Invalid manifests are skipped and reported in Feature Management.

## Removing a custom module

Disable the module in Feature Management, then remove its manifest from `config/modules/`. Do not delete source files or data unless you have confirmed they are no longer needed. Built-in modules are maintained in `universal_ai_studio/applications/registry.py` and should not be removed through the custom manifest mechanism.
