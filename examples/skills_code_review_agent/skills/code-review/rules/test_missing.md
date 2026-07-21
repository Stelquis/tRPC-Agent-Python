# Test Missing Rules

## 1. New Function Without Test

Detect public functions added to the codebase without corresponding unit tests.

### Patterns

- New `def function_name(...)` in a `.py` file that is not `test_` prefixed
- No corresponding `test_function_name` in the test directory
- New class with methods but no test class
- New module file without a corresponding `test_` module

### Severity

- **MEDIUM**: New public function with no test coverage
- **LOW**: New private function (starting with `_`) with no test (advisory)

### Fix

Add a unit test for the new function:
```python
# In tests/test_<module>.py
def test_function_name():
    result = function_name(input_data)
    assert result == expected_output
```

## 2. New Error Handler Without Test

Detect new exception handling or error paths without test coverage.

### Patterns

- New `except SomeException:` block without a test that triggers it
- New `raise CustomException(...)` without a test catching it
- New `if error:` branch without a test covering the error path

### Severity

- **MEDIUM**: Error handling path added without test coverage

### Fix

Add a test for the error path:
```python
def test_function_name_error():
    with pytest.raises(CustomException):
        function_name(invalid_input)
```

## 3. New CLI Command / Entry Point Without Test

Detect new `main()` or CLI entry points without integration tests.

### Patterns

- New `def main():` or `if __name__ == "__main__":` block
- New `argparse` parser without a test
- New CLI subcommand without a test

### Severity

- **MEDIUM**: CLI entry point without test coverage

### Fix

Use `CliRunner` or similar to test CLI commands:
```python
from click.testing import CliRunner

def test_cli_command():
    runner = CliRunner()
    result = runner.invoke(main, ["--flag"])
    assert result.exit_code == 0
```