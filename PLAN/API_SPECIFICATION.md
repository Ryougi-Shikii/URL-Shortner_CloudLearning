# API_SPECIFICATION.md

# API Specification — Distributed URL Shortener

## 1. Purpose

This document defines the external and internal API contracts for the URL-shortening platform.

The platform has three primary HTTP services:

1. URL Management API
2. Redirect Service
3. Analytics API

The analytics workers communicate through SQS rather than synchronous HTTP requests.

## 2. API architecture

| Service | Responsibility | Primary consumers |
|---|---|---|
| URL Management API | Create and manage short URLs | React frontend |
| Redirect Service | Resolve short codes and redirect visitors | Browsers, applications, crawlers |
| Analytics API | Retrieve URL performance and reports | React dashboard |
| Analytics Workers | Process click events | SQS |

### Service routing

Proposed public routes:

| Route | Destination |
|---|---|
| `api.example.com` | URL Management API |
| `r.example.com` | Redirect Service |
| `analytics.example.com` | Analytics API |
| `example.com` | React frontend |

These are logical hostnames. The actual domain configuration will be decided during deployment.

The three APIs can initially share an ALB while using separate target groups and ECS services.

---

# 3. API conventions

## 3.1 Base paths

| Service | Base path |
|---|---|
| URL Management | `/api/v1` |
| Analytics | `/api/v1` |
| Redirect | `/{short_code}` |

Versioning is explicit for application APIs.

The redirect URL should remain short and stable. It does not need to expose the internal API version.

## 3.2 Content type

JSON requests use:

`Content-Type: application/json`

JSON responses use:

`Content-Type: application/json`

Redirect responses use HTTP redirect status codes and a `Location` header.

## 3.3 Timestamp format

Use ISO 8601 timestamps in UTC for API responses.

Example:

`2026-11-06T10:30:00Z`

Use Unix timestamps internally where required by DynamoDB TTL.

## 3.4 Identifier conventions

- `short_code`: Base62-generated code or user-defined alias.
- `url_id`: Optional future internal identifier; the initial design can use `short_code` as the URL identifier.
- `user_id`: Cognito subject identifier (`sub`).
- `event_id`: Unique click-event identifier.

Do not expose DynamoDB partition keys or internal infrastructure identifiers unnecessarily.

---

# 4. Authentication and authorization

## 4.1 Authentication provider

Amazon Cognito handles user authentication.

The React frontend obtains an access token after authentication and sends it to protected API endpoints.

Header:

`Authorization: Bearer <access_token>`

## 4.2 Token validation

The FastAPI services must validate:

- JWT signature.
- Token issuer (`iss`).
- Expiration (`exp`).
- Token type and intended use.
- Audience or client identifier as applicable to the configured Cognito token.
- Required scopes or groups, if the application uses them.

The API must not merely decode a JWT and trust its contents.

## 4.3 User identity

The backend derives the authenticated user identity from the validated token.

Never trust a client-supplied `user_id` to determine ownership.

For example, when creating a URL, the client does not get to choose the owner.

## 4.4 Authorization rules

| Operation | Authorization |
|---|---|
| Create URL | Authenticated user |
| List URLs | Authenticated user; own records only |
| Retrieve URL details | Owner only |
| Update URL | Owner only |
| Deactivate URL | Owner only |
| View URL analytics | Owner only |
| Public redirect | No user authentication required |

Administrative access should be introduced separately using explicit roles and permissions.

---

# 5. URL Management API

Base URL:

`https://api.example.com/api/v1`

All endpoints in this section require authentication unless explicitly stated otherwise.

## 5.1 Create a short URL

**Endpoint**

`POST /urls`

**Purpose**

Creates a short URL for the authenticated user.

**Request**

```json
{
  "original_url": "https://example.com/articles/distributed-systems",
  "custom_alias": null,
  "expires_at": null
}
```

**Field definitions**

| Field | Type | Required | Description |
|---|---|---|---|
| `original_url` | string | Yes | Destination URL |
| `custom_alias` | string/null | No | User-requested short code |
| `expires_at` | datetime/null | No | Optional expiration |

**Response — 201 Created**

```json
{
  "short_code": "aB91xYz2",
  "short_url": "https://r.example.com/aB91xYz2",
  "original_url": "https://example.com/articles/distributed-systems",
  "created_at": "2026-11-06T10:30:00Z",
  "expires_at": null,
  "is_active": true
}
```

**Possible errors**

| Status | Meaning |
|---|---|
| 400 | Invalid request |
| 401 | Missing or invalid authentication |
| 409 | Custom alias already exists |
| 422 | Invalid URL or field validation failure |
| 429 | Rate limit exceeded |
| 500 | Unexpected server error |

Generated short-code collisions should be retried internally. A collision is not normally exposed as a client error.

### Idempotency

Support an optional `Idempotency-Key` request header.

Example:

`Idempotency-Key: 6f5b7c...`

If the same authenticated user repeats the same operation with the same key, the API should return the original result rather than create another URL.

Reusing the same key with a different request body should return `409 Conflict`.

The retention period for idempotency records must be documented and configured.

## 5.2 List the authenticated user's URLs

**Endpoint**

`GET /urls`

**Purpose**

Returns URLs owned by the authenticated user.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | 20 | Maximum records per page |
| `cursor` | string | null | Continuation token |
| `status` | string | `all` | `all`, `active`, or `inactive` |
| `sort` | string | `newest` | `newest` or `oldest` |

Example:

`GET /api/v1/urls?limit=20&sort=newest`

**Response — 200 OK**

```json
{
  "items": [
    {
      "short_code": "aB91xYz2",
      "short_url": "https://r.example.com/aB91xYz2",
      "original_url": "https://example.com/article",
      "created_at": "2026-11-06T10:30:00Z",
      "is_active": true,
      "expires_at": null
    }
  ],
  "next_cursor": "opaque-continuation-token",
  "has_more": true
}
```

The cursor is opaque to the client. It represents the backend's pagination state and must not be treated as a trusted authorization mechanism.

The backend must still enforce ownership using the authenticated user identity.

## 5.3 Retrieve URL details

**Endpoint**

`GET /urls/{short_code}`

**Purpose**

Returns metadata for a URL owned by the authenticated user.

**Response — 200 OK**

```json
{
  "short_code": "aB91xYz2",
  "short_url": "https://r.example.com/aB91xYz2",
  "original_url": "https://example.com/article",
  "created_at": "2026-11-06T10:30:00Z",
  "updated_at": "2026-11-06T10:30:00Z",
  "expires_at": null,
  "is_active": true
}
```

Return `404 Not Found` when the URL does not exist or is not accessible to the authenticated user. This avoids revealing another user's URL ownership.

## 5.4 Update a URL

**Endpoint**

`PATCH /urls/{short_code}`

**Purpose**

Updates supported URL properties.

**Request**

```json
{
  "original_url": "https://example.com/new-destination",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

All fields are optional, but at least one updateable field must be provided.

Do not allow clients to modify:

- `user_id`
- `short_code`
- `created_at`

These fields are controlled by the backend.

**Response — 200 OK**

Returns the updated URL representation.

After a successful update, the backend invalidates the corresponding Redis cache entry.

## 5.5 Deactivate a URL

**Endpoint**

`DELETE /urls/{short_code}`

**Purpose**

Deactivates a URL without immediately deleting its record.

**Response — 204 No Content**

A deactivated URL returns `410 Gone` from the redirect service.

This is a soft-delete operation. Permanent deletion and retention rules are separate concerns.

---

# 6. Redirect Service API

Base domain:

`https://r.example.com`

This service is performance-critical and publicly accessible.

## 6.1 Resolve a short URL

**Endpoint**

`GET /{short_code}`

Example:

`GET https://r.example.com/aB91xYz2`

**Purpose**

Finds the destination URL and redirects the visitor.

### Successful response

**302 Found**

Header:

`Location: https://example.com/articles/distributed-systems`

The browser follows the `Location` header.

### Error behavior

| Condition | Status |
|---|---|
| Unknown short code | 404 Not Found |
| Inactive URL | 410 Gone |
| Expired URL | 410 Gone |
| Invalid code format | 404 Not Found |
| Temporary dependency failure | 503 Service Unavailable |

### Why 302 instead of 301?

Use `302 Found` initially.

A permanent `301` redirect can be cached by browsers and intermediary systems. That makes later destination changes harder to enforce and can interfere with accurate click collection.

A `302` keeps redirect behavior more controllable.

A later product decision could introduce `307` for method-preserving redirects, but this platform's primary use case is browser navigation through GET requests.

### Redirect processing sequence

1. Receive short code.
2. Validate code format.
3. Check Redis.
4. On cache miss, retrieve the mapping from DynamoDB.
5. Check active state and expiration.
6. Publish a click event to SQS.
7. Return the redirect response.

The redirect service must not wait for analytics aggregation or Athena.

The event enqueue step must have a strict timeout and a defined failure policy. If SQS is unavailable, the initial design favors redirect availability over analytics completeness, while raising monitoring signals for lost events.

This trade-off should be revisited if click-count completeness becomes a contractual requirement.

## 6.2 Health endpoints

**Endpoint**

`GET /health`

Returns basic service health.

**Endpoint**

`GET /ready`

Indicates whether the service is ready to receive traffic.

These endpoints should not expose secrets, credentials, or detailed internal infrastructure state.

Readiness checks should be designed carefully: a temporary Redis failure should not necessarily make the redirect service entirely unavailable if DynamoDB fallback is working.

---

# 7. Analytics API

Base URL:

`https://analytics.example.com/api/v1`

All analytics endpoints require authentication and URL ownership authorization.

## 7.1 URL overview

**Endpoint**

`GET /urls/{short_code}/analytics/overview`

**Purpose**

Returns high-level performance metrics.

**Query parameters**

| Parameter | Type | Default |
|---|---|---|
| `start_date` | date | 7 days ago |
| `end_date` | date | Today |

**Response — 200 OK**

```json
{
  "short_code": "aB91xYz2",
  "period": {
    "start_date": "2026-10-31",
    "end_date": "2026-11-06"
  },
  "total_clicks": 12500,
  "unique_visitors": null,
  "average_clicks_per_day": 1785.71,
  "last_click_at": "2026-11-06T10:30:00Z"
}
```

`unique_visitors` is null until the platform defines a defensible visitor identity and deduplication policy. Total clicks must not be mislabeled as unique visitors.

## 7.2 Time-series analytics

**Endpoint**

`GET /urls/{short_code}/analytics/timeseries`

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `start_date` | date | Start of requested period |
| `end_date` | date | End of requested period |
| `interval` | string | `hour`, `day`, or `month` |

**Response**

```json
{
  "short_code": "aB91xYz2",
  "interval": "day",
  "data": [
    {
      "date": "2026-11-05",
      "clicks": 1800
    },
    {
      "date": "2026-11-06",
      "clicks": 2100
    }
  ]
}
```

The initial aggregate table supports daily data. Hourly reporting requires an hourly aggregation strategy or a query against raw events. Monthly reporting can be derived from daily aggregates initially.

## 7.3 Geography analytics

**Endpoint**

`GET /urls/{short_code}/analytics/geography`

**Response**

```json
{
  "short_code": "aB91xYz2",
  "countries": [
    {
      "country_code": "IN",
      "clicks": 5000
    },
    {
      "country_code": "US",
      "clicks": 2500
    }
  ]
}
```

Use standardized country codes, such as ISO 3166-1 alpha-2.

Country attribution is approximate and depends on the geolocation source.

## 7.4 Device analytics

**Endpoint**

`GET /urls/{short_code}/analytics/devices`

**Response**

```json
{
  "short_code": "aB91xYz2",
  "devices": [
    {
      "device_type": "mobile",
      "clicks": 7500
    },
    {
      "device_type": "desktop",
      "clicks": 4000
    },
    {
      "device_type": "tablet",
      "clicks": 1000
    },
    {
      "device_type": "unknown",
      "clicks": 0
    }
  ]
}
```

The values are illustrative.

## 7.5 Browser analytics

**Endpoint**

`GET /urls/{short_code}/analytics/browsers`

**Response**

```json
{
  "short_code": "aB91xYz2",
  "browsers": [
    {
      "browser": "Chrome",
      "clicks": 6000
    },
    {
      "browser": "Firefox",
      "clicks": 1500
    },
    {
      "browser": "Safari",
      "clicks": 2000
    },
    {
      "browser": "Other",
      "clicks": 500
    }
  ]
}
```

Browser detection should be normalized by the analytics worker.

Do not create an unbounded number of dimensions from arbitrary user-agent strings.

## 7.6 Referrer analytics

**Endpoint**

`GET /urls/{short_code}/analytics/referrers`

**Response**

```json
{
  "short_code": "aB91xYz2",
  "referrers": [
    {
      "referrer": "google.com",
      "clicks": 3000
    },
    {
      "referrer": "reddit.com",
      "clicks": 1500
    },
    {
      "referrer": "direct",
      "clicks": 4000
    }
  ]
}
```

Normalize referrers into domains or defined source categories.

The `Referer` header may be absent or restricted by browser privacy settings. Missing values should be classified as `direct` or `unknown` according to a documented rule.

---

# 8. Common error response format

All JSON APIs should use a consistent error structure.

```json
{
  "error": {
    "code": "URL_NOT_FOUND",
    "message": "The requested URL was not found.",
    "request_id": "req_abc123",
    "details": null
  }
}
```

Recommended error codes:

| Code | HTTP status | Meaning |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `UNAUTHORIZED` | 401 | Authentication required or invalid |
| `FORBIDDEN` | 403 | Operation not permitted |
| `URL_NOT_FOUND` | 404 | URL does not exist or is inaccessible |
| `ALIAS_ALREADY_EXISTS` | 409 | Requested alias is unavailable |
| `IDEMPOTENCY_CONFLICT` | 409 | Key reused with different request |
| `URL_EXPIRED` | 410 | URL has expired |
| `URL_INACTIVE` | 410 | URL was deactivated |
| `RATE_LIMITED` | 429 | Request limit exceeded |
| `INTERNAL_ERROR` | 500 | Unexpected application error |
| `DEPENDENCY_UNAVAILABLE` | 503 | Required dependency unavailable |

Do not expose stack traces, database exceptions, internal hostnames, or credentials in client-facing error messages.

---

# 9. Rate limiting

Rate limits should be applied at multiple levels.

| API | Rate-limit dimension |
|---|---|
| URL creation | Authenticated user |
| URL updates | Authenticated user |
| URL listing | Authenticated user |
| Analytics queries | Authenticated user |
| Redirect resolution | Source/IP-derived policy, with abuse controls |

The exact limits should be determined through product requirements and load testing.

Do not use one global rate limit for every endpoint. Creating URLs, querying analytics, and following redirects have different resource costs.

Use WAF and/or application-level rate limiting where appropriate.

For authenticated APIs, user-level limits can be enforced using the validated Cognito identity.

For public redirects, IP-based controls must account for NAT, mobile carrier networks, and legitimate traffic bursts.

---

# 10. Internal analytics event contract

The redirect service publishes a message to SQS.

This is not a public HTTP API. It is an internal event contract.

## 10.1 Event name

`url.click.v1`

## 10.2 Example event

```json
{
  "event_id": "evt_01JXYZ123",
  "event_type": "url.click.v1",
  "short_code": "aB91xYz2",
  "occurred_at": "2026-11-06T10:30:00Z",
  "country_code": "IN",
  "device_type": "mobile",
  "browser": "Chrome",
  "referrer_domain": "google.com"
}
```

## 10.3 Event contract rules

- `event_id` must be unique.
- `event_type` includes a version.
- `occurred_at` represents event time, not worker processing time.
- Unknown or unavailable dimensions use a defined fallback such as `unknown`.
- Events should be validated before aggregation.
- Consumers must tolerate duplicate delivery.
- Schema changes require compatibility planning.

## 10.4 Event versioning

Do not silently change the meaning of an existing event field.

For incompatible changes, introduce a new event version, such as `url.click.v2`.

Workers should support a deliberate migration period when multiple versions are in circulation.

---

# 11. Observability and request tracing

Every API request should have a request ID.

The request ID should be:

- Generated or validated at the edge.
- Propagated through service logs.
- Included in error responses.
- Used to correlate application and infrastructure telemetry.

For analytics events, use `event_id` as the correlation identifier.

Measure:

### URL Management API

- Request rate.
- Error rate.
- p50, p95, and p99 latency.
- URL creation failures.
- Conditional-write collisions.
- Rate-limit rejections.

### Redirect Service

- Redirect requests per second.
- Successful redirects.
- 404 and 410 counts.
- Redis hit ratio.
- DynamoDB fallback rate.
- Redirect latency.
- SQS enqueue failures.

### Analytics

- SQS queue depth.
- Oldest message age.
- Worker throughput.
- Failed messages.
- DLQ depth.
- Event-to-dashboard processing delay.
- Aggregate query latency.
- Athena query cost and scan volume.

Never log access tokens or unnecessary personal information.

---

# 12. API security requirements

1. Validate JWT signatures and claims.
2. Derive user identity from authenticated claims.
3. Enforce ownership checks on every user-specific operation.
4. Accept only valid HTTP and HTTPS destination URLs.
5. Reject malformed URLs and unsupported schemes.
6. Restrict alias length and allowed characters.
7. Rate-limit URL creation and public redirects.
8. Avoid leaking whether another user owns a URL.
9. Validate pagination cursors.
10. Limit analytics date ranges and response sizes.
11. Protect API documentation and administrative routes appropriately.
12. Avoid storing raw IP addresses unless a justified, documented requirement exists.

If future functionality fetches or previews destination URLs server-side, it must include SSRF protections. The current redirect service should not fetch the destination URL itself; it should return the destination in the `Location` header.

---

# 13. API testing strategy

## Functional tests

- Create a generated short URL.
- Create a custom alias.
- Reject a duplicate alias.
- Retrieve URL details.
- List URLs with pagination.
- Update destination.
- Deactivate URL.
- Reject expired URLs.
- Redirect valid URLs.
- Return correct errors for invalid codes.

## Authorization tests

- User A cannot retrieve User B's URL.
- User A cannot update User B's URL.
- User A cannot delete User B's URL.
- User A cannot access User B's analytics.
- Missing or invalid JWTs are rejected.
- Expired JWTs are rejected.

## Reliability tests

- Redis unavailable.
- DynamoDB unavailable.
- SQS unavailable.
- Duplicate analytics event.
- Worker crash during processing.
- Analytics worker backlog.
- Invalid event schema.
- Athena unavailable.

## Performance tests

- Redirect requests with warm Redis cache.
- Redirect requests with cold Redis cache.
- Highly popular short code.
- Random short-code distribution.
- Large user URL listing.
- Analytics queries over different date ranges.
- Concurrent URL creation.
- Sudden traffic spikes.

---

# 14. Final endpoint inventory

| Method | Endpoint | Service | Authentication |
|---|---|---|---|
| POST | `/api/v1/urls` | URL Management | Required |
| GET | `/api/v1/urls` | URL Management | Required |
| GET | `/api/v1/urls/{short_code}` | URL Management | Required |
| PATCH | `/api/v1/urls/{short_code}` | URL Management | Required |
| DELETE | `/api/v1/urls/{short_code}` | URL Management | Required |
| GET | `/{short_code}` | Redirect | Public |
| GET | `/health` | Service health | Internal/controlled |
| GET | `/ready` | Service readiness | Internal/controlled |
| GET | `/api/v1/urls/{short_code}/analytics/overview` | Analytics | Required |
| GET | `/api/v1/urls/{short_code}/analytics/timeseries` | Analytics | Required |
| GET | `/api/v1/urls/{short_code}/analytics/geography` | Analytics | Required |
| GET | `/api/v1/urls/{short_code}/analytics/devices` | Analytics | Required |
| GET | `/api/v1/urls/{short_code}/analytics/browsers` | Analytics | Required |
| GET | `/api/v1/urls/{short_code}/analytics/referrers` | Analytics | Required |

---

# 15. Definition of API readiness

The API specification is ready for implementation when:

- All public endpoints have defined methods and paths.
- Request and response schemas are defined.
- Authentication and authorization rules are explicit.
- Error responses are consistent.
- Pagination is specified.
- Redirect status behavior is specified.
- Analytics event schema is versioned.
- Rate-limiting requirements are defined.
- API tests cover normal, failure, and authorization cases.

**Status:** API contract drafted. Exact rate limits, token configuration, date-range limits, and event-delivery guarantees must be finalized during implementation and testing.