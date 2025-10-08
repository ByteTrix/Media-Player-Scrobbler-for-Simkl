# Simkl API Integration Specification

## Overview
This document outlines the Simkl API integration improvements for the Media Player Scrobbler for Simkl application.

## Current State
The application currently integrates with the Simkl API through the `simkl_api.py` module, which provides:
- Movie and TV show search functionality
- File-based search
- Watch history tracking
- OAuth authentication flow
- User settings retrieval

## Completed Improvements

### 1. Enhanced Error Handling ✅
- **Implemented**: Added comprehensive retry logic with exponential backoff for transient errors
- **Rate Limiting**: Proper handling of HTTP 429 (Rate Limiting) with respect for `Retry-After` header
- **Improved Messages**: Better error logging for debugging
- **Transient Errors**: Automatic retry for 5xx server errors, timeouts, and connection errors
- **Implementation**: New `_make_api_request()` helper function that all API calls use

### 2. Type Annotations ✅
- **Added**: Comprehensive type hints to all API functions using Python's `typing` module
- **Types Used**: `Dict`, `Optional`, `Any`, `Union` for precise type checking
- **Benefits**: Better IDE support, easier debugging, and clearer API contracts

### 3. Consistent API Usage ✅
- **Standardized**: All API functions now use the `_make_api_request()` helper
- **Functions Updated**:
  - `search_movie()`
  - `search_file()`
  - `add_to_history()`
  - `get_movie_details()`
  - `get_show_details()`
  - `get_user_settings()`
  - `_validate_access_token()`

## Proposed Future Improvements

### 1. API Response Caching
- Implement response caching to reduce API calls
- Cache show/movie details to avoid repeated lookups
- Respect cache TTL and invalidation strategies

### 2. Batch Operations
- Add support for batch operations where Simkl API allows
- Bulk history updates for offline mode

### 3. Comprehensive Testing
- Add unit tests for API functions (framework created, needs fixes)
- Mock API responses for reliable testing
- Add integration tests with actual API (optional)

## Implementation Details

### Retry Logic
The `_make_api_request()` function implements:
- **Max Retries**: Default 3 attempts
- **Exponential Backoff**: Starts at 1 second, doubles each retry
- **Rate Limiting**: Respects `Retry-After` header from HTTP 429 responses
- **Server Errors**: Retries 5xx errors (500-599)
- **Transient Errors**: Retries timeouts and connection errors
- **Client Errors**: Does not retry 4xx errors (except 429)

### Type Annotations
Example function signature:
```python
def search_movie(
    title: str,
    client_id: str,
    access_token: str,
    file_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
```

## Success Criteria
- [x] All API functions have proper error handling with retry logic
- [x] Type annotations pass Python syntax checks
- [x] All public and private API functions have type hints
- [ ] Response caching reduces unnecessary API calls by 50%
- [ ] Full test coverage for API module
- [ ] Documentation with usage examples

## Usage Examples

### Basic Movie Search
```python
from simkl_mps.simkl_api import search_movie
from simkl_mps.credentials import get_credentials

creds = get_credentials()
result = search_movie("Inception", creds['client_id'], creds['access_token'])
if result:
    movie = result.get('movie', {})
    print(f"Found: {movie.get('title')} ({movie.get('year')})")
```

### Error Handling
The API functions automatically handle errors:
- Returns `None` on failure
- Logs errors for debugging
- Retries transient errors automatically
- No need for manual retry logic in calling code

### Rate Limiting
Rate limiting is handled automatically:
```python
# This call will automatically retry with exponential backoff if rate limited
result = search_movie("Movie Title", client_id, access_token)
```

## Migration Guide
No breaking changes - all existing code continues to work. The improvements are internal:
- Existing API function signatures remain the same
- Return types unchanged (still return `None` on error)
- Only internal implementation improved
