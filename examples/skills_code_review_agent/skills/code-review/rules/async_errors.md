# Async Error Rules

## 1. Missing `await`

Detect async functions that call other async functions without `await`.

### Patterns

- `async def foo():` calls `bar()` where `bar` is `async`
- Missing `await` before `bar()`
- `asyncio.create_task(...)` result not stored or awaited

### Severity

- **HIGH**: Async function called without await, coroutine is discarded
- **MEDIUM**: Async function called without await but result is used later

### Fix

```python
# Bad
async def fetch_data():
    result = fetch_from_api()  # Missing await

# Good
async def fetch_data():
    result = await fetch_from_api()
```

## 2. Missing `try-finally` / `async with`

Detect async resources that are not properly cleaned up.

### Patterns

- `async def` opens a resource but no `try-finally` or `async with`
- `await session.get()` without closing the session
- `await lock.acquire()` without `try-finally lock.release()`

### Severity

- **HIGH**: Resource leak in async context
- **MEDIUM**: Missing cleanup but resource is short-lived

### Fix

```python
# Bad
session = await aiohttp.ClientSession()
result = await session.get(url)

# Good
async with aiohttp.ClientSession() as session:
    async with session.get(url) as resp:
        result = await resp.text()
```

## 3. Unhandled Task Exception

Detect `asyncio.create_task` results that are not awaited or caught.

### Patterns

- `task = asyncio.create_task(coro())` without `await task` or `try-except`
- No `task.add_done_callback()` to handle exceptions

### Severity

- **MEDIUM**: Task exception will be silently lost on garbage collection

### Fix

```python
# Bad
asyncio.create_task(background_work())

# Good
task = asyncio.create_task(background_work())
task.add_done_callback(lambda t: t.exception() if t.done() else None)
```