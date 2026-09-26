# Sample Repo

A minimal FastAPI application used as a test fixture for OnboardBob's
Documentation Sync & Drift Detection engine.

---

## API Endpoints

### `GET /health`

Liveness probe. Returns `{"status": "ok"}`.

---

### `GET /users/{user_id}`

Return a single user by their unique integer ID.

| Parameter  | Type  | Required | Description           |
|------------|-------|----------|-----------------------|
| `user_id`  | `int` | Yes      | The user's integer ID |
| `token`    | `str` | No       | Auth token (stale – removed from code) |

**Response:**

```json
{
  "id": 1,
  "name": "Alice",
  "email": "alice@example.com",
  "active": true
}
```

---

### `POST /users/`

Create a new user.

| Parameter  | Type  | Required | Description      |
|------------|-------|----------|------------------|
| `payload`  | body  | Yes      | UserCreate schema |

**Response:** `UserResponse`

---

> **Note:** `/items/` endpoints and `DELETE /users/{user_id}` are not yet documented.
