---
name: ecc-tdd-workflow
description: "TDD methodology with Red-Green-Refactor cycle, 80%+ coverage enforcement, mocking patterns. Use when developing new features or fixing bugs."
category: ecc
origin: everything-claude-code
---

# TDD Workflow

Complete test-driven development methodology.

## The Cycle

### 1. RED — Write Failing Test
```python
def test_user_creation_with_valid_data():
    user = create_user(name="Alice", email="alice@example.com")
    assert user.name == "Alice"
    assert user.id is not None
```
Run it. It should FAIL (function doesn't exist yet).

### 2. GREEN — Minimal Implementation
```python
def create_user(name: str, email: str) -> User:
    return User(name=name, email=email, id=generate_id())
```
Run it. It should PASS.

### 3. REFACTOR
Clean up. Tests stay green.

### 4. COMMIT
```bash
git add -A && git commit -m "feat: add user creation with tests"
```

## Coverage Requirements
- Minimum 80% branch coverage
- Minimum 80% function coverage
- 100% coverage on critical paths (auth, payments)

## Test Types

### Unit Tests
- Test individual functions in isolation
- Mock external dependencies
- Fast execution (< 100ms per test)

### Integration Tests
- Test API endpoints with real database
- Test service interactions
- Moderate speed (< 5s per test)

### E2E Tests
- Test critical user flows
- Use Playwright or similar
- Slow but high confidence

## Mocking Patterns

### Python
```python
from unittest.mock import patch, MagicMock

@patch('app.services.email.send_email')
def test_welcome_email_sent(mock_send):
    register_user("alice@example.com")
    mock_send.assert_called_once_with(
        to="alice@example.com",
        template="welcome"
    )
```

### JavaScript/TypeScript
```typescript
jest.mock('./email-service');
const mockSend = emailService.send as jest.Mock;

test('sends welcome email on registration', async () => {
  await registerUser('alice@example.com');
  expect(mockSend).toHaveBeenCalledWith({
    to: 'alice@example.com',
    template: 'welcome'
  });
});
```

## Anti-Patterns
- Writing tests after code (not TDD)
- Testing implementation details
- Shared mutable state between tests
- Over-mocking (testing mocks, not behavior)
- Ignoring failing tests
