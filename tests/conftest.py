"""Shared pytest policy.

A test that needs an optional external program (LibreOffice, 7-Zip, ...) must not
fail on a machine that does not have it. When Kumquat's ``BackendMissing`` error
escapes a test, report a skip that carries the message: the missing check stays
visible in the summary and is never counted as a pass.

Tests that assert the error with ``pytest.raises`` are unaffected, because the
exception never reaches this hook. (Several modules define their own
``BackendMissing`` class, so it is matched by name.)
"""

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    try:
        return (yield)
    except Exception as exc:
        if any(cls.__name__ == "BackendMissing" for cls in type(exc).__mro__):
            pytest.skip(str(exc))
        raise
