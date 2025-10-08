# Simkl API Integration

This directory contains improvements to the Simkl API integration module (`simkl_api.py`).

## Overview

The Simkl API module has been enhanced with robust error handling, retry logic, and type annotations to improve reliability and maintainability.

## Key Improvements

### 1. Enhanced Error Handling

All API functions now use a centralized `_make_api_request()` helper that provides:

- **Automatic Retry Logic**: Up to 3 retries with exponential backoff
- **Rate Limiting Support**: Handles HTTP 429 responses with proper `Retry-After` header parsing
- **Transient Error Recovery**: Automatically retries on timeouts, connection errors, and 5xx server errors
- **Smart Error Handling**: Client errors (4xx) return immediately without retry, except for rate limiting (429)

### 2. Type Annotations

All functions have comprehensive type hints for better IDE support and type safety:

```python
def search_movie(
    title: str,
    client_id: str,
    access_token: str,
    file_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    ...
```

### 3. Consistent API

All API functions follow a consistent pattern:
- Return `Optional[Dict[str, Any]]` - `None` on error, dict on success
- Automatically handle authentication headers
- Log all requests and errors for debugging
- Use the retry helper for all network requests

## API Functions

### Search Functions

#### `search_movie(title, client_id, access_token, file_path=None)`
Searches for a movie across multiple Simkl endpoints.

**Returns**: Movie data wrapped in `{'movie': {...}}` structure, or `None`

```python
from simkl_mps.simkl_api import search_movie

result = search_movie("Inception", client_id, access_token)
if result:
    movie = result['movie']
    print(f"Found: {movie['title']} ({movie.get('year', 'N/A')})")
```

#### `search_file(file_path, client_id, part=None)`
Searches for media by file path using Simkl's file recognition API.

**Returns**: Media data with type info, or `None`

```python
result = search_file("/path/to/movie.mkv", client_id)
if result and result.get('type') == 'movie':
    print(f"Identified: {result['movie']['title']}")
```

### Detail Functions

#### `get_movie_details(simkl_id, client_id, access_token)`
Retrieves comprehensive movie information including runtime, poster, IMDb ID, etc.

```python
details = get_movie_details(12345, client_id, access_token)
if details:
    print(f"Runtime: {details.get('runtime', 'N/A')} minutes")
```

#### `get_show_details(simkl_id, client_id, access_token)`
Retrieves TV show or anime details.

```python
show = get_show_details(67890, client_id, access_token)
if show:
    print(f"Show: {show['title']} - Type: {show.get('type', 'show')}")
```

### History Functions

#### `add_to_history(payload, client_id, access_token)`
Adds movies/shows/episodes to user's watch history.

**Payload Structure**:
```python
payload = {
    'movies': [{
        'ids': {'simkl': 12345},
        'watched_at': '2025-01-01T12:00:00Z'
    }]
}
result = add_to_history(payload, client_id, access_token)
```

### User Functions

#### `get_user_settings(client_id, access_token)`
Retrieves user settings and user ID.

```python
settings = get_user_settings(client_id, access_token)
if settings:
    user_id = settings.get('user_id')
    print(f"User ID: {user_id}")
```

### Authentication Functions

#### `pin_auth_flow(client_id, redirect_uri="urn:ietf:wg:oauth:2.0:oob")`
Implements OAuth PIN authentication flow.

**Returns**: Access token on success, `None` on failure

```python
access_token = pin_auth_flow(client_id)
if access_token:
    print("Authentication successful!")
```

## Error Handling

The API module handles errors gracefully:

### Automatic Retries

Transient errors are retried automatically:
- Connection timeouts
- Connection errors  
- Server errors (500-599)
- Rate limiting (429)

### No Retries

Client errors return immediately:
- Bad request (400)
- Unauthorized (401)
- Not found (404)
- Other 4xx errors

### Usage

```python
# No need for manual error handling - it's automatic!
result = search_movie("Movie Title", client_id, access_token)

if result is None:
    # Error occurred and retries exhausted
    print("Failed to search movie")
else:
    # Success!
    movie = result['movie']
    print(f"Found: {movie['title']}")
```

## Rate Limiting

The module automatically handles Simkl's rate limiting:

1. When HTTP 429 is received, checks `Retry-After` header
2. Waits the specified time (or uses exponential backoff)
3. Retries the request up to max retries
4. Logs all rate limit events

**No action required** - rate limiting is handled transparently.

## Logging

All API calls are logged for debugging:

```python
import logging
logging.basicConfig(level=logging.INFO)

# Now all API calls will log their activities
result = search_movie("Test", client_id, access_token)
# Logs: "Simkl API: Searching for movie by title: 'Test'..."
# Logs: "Simkl API: Found 5 movie results for 'Test'."
```

## Helper Functions

### `_make_api_request(method, url, headers, params, json, max_retries, initial_timeout)`
Internal helper that implements retry logic. Used by all API functions.

### `_normalize_simkl_ids(item_dict, item_type, title)`
Ensures Simkl IDs are in consistent format across different API responses.

### `_add_user_agent(headers)`
Adds user agent string to requests for API identification.

### `_validate_access_token(client_id, access_token)`
Quickly validates if an access token is valid by making a test API call.

## Best Practices

1. **Always check for None**: API functions return `None` on error
2. **Use the credentials module**: Get client_id and access_token from `simkl_mps.credentials`
3. **Enable logging**: Set log level to INFO or DEBUG for troubleshooting
4. **Let errors fail**: Don't wrap API calls in try/except - the module handles errors internally

## Example: Complete Flow

```python
from simkl_mps.credentials import get_credentials
from simkl_mps.simkl_api import search_movie, add_to_history
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)

# Get credentials
creds = get_credentials()

# Search for a movie
result = search_movie("The Matrix", creds['client_id'], creds['access_token'])

if result:
    movie = result['movie']
    simkl_id = movie['ids']['simkl']
    
    # Add to history
    payload = {
        'movies': [{
            'ids': {'simkl': simkl_id}
        }]
    }
    
    if add_to_history(payload, creds['client_id'], creds['access_token']):
        print(f"Added '{movie['title']}' to history!")
    else:
        print("Failed to add to history")
else:
    print("Movie not found or API error occurred")
```

## Migration from Previous Version

No changes needed! The improvements are backward compatible:
- All function signatures remain the same
- Return types unchanged
- Behavior improved but consistent

Existing code will automatically benefit from the new error handling and retry logic.

## Future Enhancements

Planned improvements:
- [ ] Response caching to reduce API calls
- [ ] Batch operation support
- [ ] Comprehensive unit test coverage
- [ ] Performance metrics and monitoring

See `simkl_api_integration.md` for full specification.
