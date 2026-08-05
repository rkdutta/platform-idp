"""Fixtures for teams-operator unit tests.

TeamsOperator.__init__ loads a real kube-config (in-cluster or local
~/.kube/config) as a side effect of construction — fine for the running
operator, useless and environment-dependent for a unit test. Tests here
build an instance via __new__ (skips __init__ entirely) and set only the
attributes the method under test actually reads, the same "test one unit in
isolation" approach as teams-api's tests/conftest.py.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from teams_operator import TeamsOperator  # noqa: E402


@pytest.fixture
def operator():
    op = TeamsOperator.__new__(TeamsOperator)
    op.EVENT_TEAM_LABEL = "teams.example.com/team-id"
    op.OPERATOR_NAMESPACE = "engineering-platform"
    op.k8s_core_v1 = MagicMock()
    return op
