"""
tests/conftest.py
-----------------
Shared pytest fixtures for the Ask-N-Seek test suite.
"""
import pytest
from backend.query.query_parser import QueryParser


@pytest.fixture(scope="session")
def parser():
    """
    Session-scoped QueryParser instance.
    spaCy loads en_core_web_sm once per test session — avoids 1-2 s overhead
    on every test function that needs it.
    """
    return QueryParser()
