# Shared Contract Fixtures

JSON test fixtures that both `packages/python/` and `packages/js/` test suites validate against. These define the protocol contract — any implementation, regardless of language, must conform to these response shapes and semantics.

## Fixture Files

| File | Contract |
|------|----------|
| `list.json` | Tool discovery: shape, hidden tools, descriptions |
| `explain.json` | Schema on demand: shape, not_found, error cases |
| `run.json` | Tool execution: shape, required fields, errors |
| `hints.json` | CRUD for hints: methods, idempotent CREATE, UPDATE, DELETE |
| `hidden-tools.json` | Hidden tools are runnable but not listable |
| `error-responses.json` | All error cases produce uniform shape |

## Usage

### Python

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"

def load_fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())

data = load_fixture("list")
# validate shape, test cases against implementation
```

### JavaScript

```typescript
import * as path from 'node:path';
import * as fs from 'node:fs';

const FIXTURES = path.join(__dirname, '..', '..', 'fixtures');

function loadFixture(name: string) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, `${name}.json`), 'utf-8'));
}
```

## Adding New Test Cases

1. Add the case to the appropriate fixture file under `test_cases`
2. Implement the corresponding test in both `packages/python/tests/` and `packages/js/test/`
3. Both must pass independently — this is the contract
