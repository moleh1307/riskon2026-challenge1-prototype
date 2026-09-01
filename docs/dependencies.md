# Dependency inventory

The versions below are resolved in `uv.lock`; the ranges in `pyproject.toml`
are bounded to the major version requested for M0.

| Package | Resolved version | Purpose | Lane | License note |
| --- | ---: | --- | --- | --- |
| pydantic | 2.13.4 | Validated public data contracts | runtime | Verify before any external-data deployment |
| beautifulsoup4 | 4.15.0 | Local HTML parsing | runtime | Verify before any external-data deployment |
| lxml | 6.1.2 | BeautifulSoup parser backend | runtime | Verify before any external-data deployment |
| openpyxl | 3.1.5 | Local XLSX manifest parsing | runtime | Verify before any external-data deployment |
| defusedxml | 0.7.1 | XML safety dependency available to ingestion | runtime | Verify before any external-data deployment |
| scikit-learn | 1.9.0 | Deterministic TF-IDF retrieval | runtime | Verify before any external-data deployment |
| pytest | 9.1.1 | Test runner | dev | Development-only |
| pytest-cov | 7.1.0 | Branch coverage reporting | dev | Development-only |
| pytest-socket | 0.8.1 | Network-disabled test enforcement | dev | Development-only |
| ruff | 0.16.4 | Formatting and linting | dev | Development-only |
| mypy | 2.3.1 | Strict static typing | dev | Development-only |
| python-pptx | 1.0.2 | Editable ER-C PowerPoint generation | dev | Development-only; not a runtime service |

This inventory is a build-time record, not a legal licence opinion. A later
milestone must re-check commercial-use and approved-provider requirements
against the exact event-day deployment. `python-pptx` is intentionally kept
in the dev dependency group: ER-C generation is a local build step and does
not add a production runtime, presentation service, cloud renderer, API or
PowerPoint automation dependency.
