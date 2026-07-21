# Database Transaction Rules

## 1. Unclosed Database Connection

Detect database connections that are not properly closed.

### Patterns

- `sqlite3.connect(...)` without `.close()` or `with` statement
- `psycopg2.connect(...)` without `.close()`
- `create_engine(...)` without engine disposal
- `pymongo.MongoClient(...)` without `.close()`

### Severity

- **HIGH**: Connection created in a function without any cleanup
- **MEDIUM**: Connection is eventually closed but in a different code path

### Fix

```python
# Bad
conn = sqlite3.connect("database.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM users")

# Good
with sqlite3.connect("database.db") as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
```

## 2. Missing Transaction Commit / Rollback

Detect transactions that are started but not completed.

### Patterns

- `conn.execute("BEGIN")` without `COMMIT` or `ROLLBACK`
- `conn.execute("BEGIN TRANSACTION")` without completion
- Context manager `conn:` without handling exceptions for rollback

### Severity

- **HIGH**: Transaction is started but not committed or rolled back in all code paths
- **MEDIUM**: Transaction is committed but not rolled back on exception

### Fix

```python
# Bad
conn.execute("BEGIN")
conn.execute("UPDATE accounts SET balance = balance - 100 WHERE id = 1")
conn.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 2")
conn.execute("COMMIT")  # Missing rollback if middle statement fails

# Good
try:
    conn.execute("BEGIN")
    conn.execute("UPDATE accounts SET balance = balance - 100 WHERE id = 1")
    conn.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 2")
    conn.execute("COMMIT")
except Exception:
    conn.execute("ROLLBACK")
    raise
```

## 3. Long-Running Transaction

Detect transactions that span across user interaction or I/O waits.

### Patterns

- `BEGIN` before a long computation or network call before `COMMIT`
- Holding locks or connections while waiting for user input

### Severity

- **MEDIUM**: Transaction spans I/O operations, risk of deadlock
- **LOW**: Transaction is short but could be optimized

### Fix

```python
# Bad
conn.execute("BEGIN")
result = await fetch_from_external_api()  # I/O in transaction
conn.execute("UPDATE ...")
conn.execute("COMMIT")

# Good
result = await fetch_from_external_api()
conn.execute("BEGIN")
conn.execute("UPDATE ...")
conn.execute("COMMIT")
```