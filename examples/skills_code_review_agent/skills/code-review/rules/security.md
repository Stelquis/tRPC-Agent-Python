# Security Rules

## 1. Hardcoded Secrets / Credentials

Detect hardcoded API keys, tokens, passwords, and private keys in source code.

### Patterns

- `API_KEY = "..."` or `api_key = '...'`
- `password = "..."` or `PASSWORD = '...'`
- `secret = "..."` or `SECRET = '...'`
- `token = "..."` or `TOKEN = '...'`
- `-----BEGIN RSA PRIVATE KEY-----`
- `sk-...` (OpenAI API key pattern)
- `ghp_...` (GitHub personal access token)

### Severity

- **HIGH**: Static string literal containing credential-like patterns
- **MEDIUM**: Variable name suggests credential but value is an environment variable reference

### Fix

Replace hardcoded values with environment variables or a secrets manager:
```python
# Bad
API_KEY = "sk-abc123..."

# Good
import os
API_KEY = os.getenv("API_KEY")
```

## 2. Command Injection

Detect unsafe construction of shell commands.

### Patterns

- `os.system(f"rm {user_input}")`
- `subprocess.run(f"grep {pattern} file", shell=True)`
- `eval(user_input)` or `exec(user_input)`
- `os.popen(user_input)`

### Severity

- **CRITICAL**: Direct user input passed to shell execution
- **HIGH**: User input used in shell command after minimal sanitization

### Fix

Use subprocess with argument list instead of shell string:
```python
# Bad
subprocess.run(f"grep {pattern} file", shell=True)

# Good
subprocess.run(["grep", pattern, "file"])
```

## 3. Path Traversal

Detect unsafe file path construction from user input.

### Patterns

- `open(f"/path/{user_input}")`
- `Path("/base/" + user_input)`
- No validation of `..` or absolute paths

### Severity

- **HIGH**: User-controlled path without sanitization
- **MEDIUM**: Path constructed with user input but has basic validation

### Fix

Use `os.path.abspath()` and verify the resolved path is within allowed directory:
```python
import os
base = "/safe/directory"
path = os.path.abspath(os.path.join(base, user_input))
if not path.startswith(base):
    raise ValueError("Path traversal detected")
```