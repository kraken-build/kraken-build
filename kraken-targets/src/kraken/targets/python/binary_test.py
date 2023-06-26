import copy

import pytest

from kraken.targets.core.rulerunner import RuleRunner
from kraken.targets.python.binary import PythonBinary, PythonBinaryRequest


@pytest.fixture
def runner() -> RuleRunner:
    return RuleRunner(["kraken.targets.python.binary"])


def test__get_python_binary(runner: RuleRunner) -> None:
    request = PythonBinaryRequest(interpreter_constraint=">=3.10")
    response = runner.get(PythonBinary, [request])

    # We can't really know where the Python binary is on the system that we run the test on,
    # but at least we can assert that it's not causing any errors.
    assert isinstance(response, PythonBinary)

    # Test that the RuleEngine caching is working.
    assert runner.get(PythonBinary, [copy.deepcopy(request)]) is response
