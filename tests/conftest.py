"""Make test_app.py's check() calls count under pytest.

The backtest records failures in a counter so it can also run as a script.
Under pytest that counter alone never fails a test, so each test fails here
if it added any.
"""

import pytest


@pytest.fixture(autouse=True)
def fail_on_recorded_checks(request):
    failures = getattr(request.module, "FAILURES", None)
    before = len(failures) if failures is not None else 0
    yield
    if failures is not None and len(failures) > before:
        pytest.fail("\n".join(failures[before:]), pytrace=False)
