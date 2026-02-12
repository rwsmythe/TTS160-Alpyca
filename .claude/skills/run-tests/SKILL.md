---
name: run-tests
description: Run unit tests, integration tests, or all with coverage
disable-model-invocation: true
---

# Run Tests

Run the TTS160 Alpyca test suite.

## Arguments

The user may specify which tests to run:
- `unit` or `u` - Unit tests only (default if no argument)
- `integration` or `i` - Integration tests only
- `all` or `a` - Both unit and integration tests
- `coverage` or `c` - Unit tests with coverage report

Multiple arguments can be combined: `/run-tests unit coverage`

## Unit Tests

**Location:** `tests/unit/`
**Framework:** pytest

### Steps

1. Run tests:
```bash
python -m pytest tests/unit/ -v
```

2. Report: number of tests passed/failed/skipped/total

## Integration Tests

**Location:** `tests/integration/`
**Framework:** pytest

### Steps

1. Run tests:
```bash
python -m pytest tests/integration/ -v
```

2. Report: number of tests passed/failed/skipped/total

## All Tests

Run both unit and integration tests:

```bash
python -m pytest tests/ -v
```

## Coverage

Run unit tests with coverage report:

```bash
python -m pytest tests/unit/ -v --cov=. --cov-report=term-missing
```

Report coverage percentages per module.

## Output

Always report:
- Test counts: passed / failed / skipped / total
- Details for any failures
- For coverage: percentage breakdown by module
