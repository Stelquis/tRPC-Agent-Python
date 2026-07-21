# Resource Leak Rules

## 1. Unclosed File Handles

Detect file operations without proper closure.

### Patterns

- `open(path)` without `with` statement or `.close()`
- `Path.read_text()` / `Path.write_text()` are safe (auto-close)
- Multiple `open()` calls in a function without tracking

### Severity

- **HIGH**: File opened in a loop or long-lived function without `with`
- **MEDIUM**: File opened but eventually closed in a different code path

### Fix

```python
# Bad
f = open("data.txt")
data = f.read()

# Good
with open("data.txt") as f:
    data = f.read()
```

## 2. Unclosed Network Connections

Detect network connections without proper cleanup.

### Patterns

- `requests.get()` without session context — safe (auto-closes)
- `http.client.HTTPConnection` without `.close()`
- `websocket.connect()` without `close()`
- `aiohttp.ClientSession()` without `async with`

### Severity

- **HIGH**: Connection object created without context manager
- **MEDIUM**: Connection is eventually closed but implicitly

### Fix

```python
# Bad
conn = http.client.HTTPConnection("example.com")
conn.request("GET", "/")
resp = conn.getresponse()

# Good
with http.client.HTTPConnection("example.com") as conn:
    conn.request("GET", "/")
    resp = conn.getresponse()
```

## 3. Unclosed io.BytesIO / StringIO

Detect in-memory stream objects that are not closed.

### Patterns

- `io.BytesIO()` or `io.StringIO()` created without `.close()`
- While these are GC'd, failing to close can mask bugs

### Severity

- **LOW**: Memory will be freed by GC, but close() is still recommended

### Fix

```python
# Bad
buf = io.StringIO()
buf.write("data")

# Good
with io.StringIO() as buf:
    buf.write("data")
```