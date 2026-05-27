# Rate Limiter Quick Start Guide

## Summary

Your Flickr API wrapper now includes **automatic rate limiting** to prevent exceeding Flickr's API limits (3600 requests/hour).

## Quick Start

### Default Usage (Recommended)

No changes needed! Rate limiting is automatic with safe defaults:

```python
from flickr_oauth import FlickrAPI

# Automatically rate limited at 1 call/second
flickr = FlickrAPI(API_KEY, API_SECRET)

# All your existing code works the same
for photo in flickr.walk(user_id='me'):
    info = flickr.photos.getInfo(photo_id=photo.attrib['id'])
```

### Custom Rate Limits

If you need to adjust the rate:

```python
# More conservative (0.5 calls/second = 1800/hour)
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=0.5)

# Default (1 call/second = 3600/hour) - matches Flickr's limit
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=1.0)

# Aggressive (not recommended without testing)
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=2.0, burst_size=5)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rate_limit` | `1.0` | Max API calls per second |
| `burst_size` | `2 × rate_limit` | Max burst calls before throttling |

## What Changed?

### Constructor

**Before:**
```python
flickr = FlickrAPI(api_key, api_secret, cache=True)
```

**After (still works!):**
```python
flickr = FlickrAPI(api_key, api_secret, cache=True)
# Now includes rate limiting automatically
```

**After (with custom rate):**
```python
flickr = FlickrAPI(api_key, api_secret, cache=True, 
                  rate_limit=1.0, burst_size=2)
```

### Behavior

- **All API calls** automatically respect rate limits
- **Thread-safe** for multi-threaded applications
- **Transparent** - no code changes required
- **Configurable** - adjust limits as needed

## Examples

### Example 1: Basic Script (No Changes Needed)

```python
# Your existing code works exactly the same
flickr = FlickrAPI(API_KEY, API_SECRET)

if not flickr.token_valid():
    flickr.authenticate()

# Rate limiting is automatic
for photo in flickr.walk(user_id='me', per_page=500):
    sizes = flickr.photos.getSizes(photo_id=photo.attrib['id'])
    print(f"Processing {photo.attrib.get('title')}")
```

### Example 2: Conservative Rate Limit

```python
# For safer operation, use a lower rate
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=0.8, burst_size=1)

# Same code, but throttled more conservatively
for photo in flickr.walk(user_id='me'):
    info = flickr.photos.getInfo(photo_id=photo.attrib['id'])
```

### Example 3: Disable Rate Limiting (Not Recommended)

```python
# Set very high limits to effectively disable
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=1000.0, burst_size=10000)

# ⚠️ Warning: You may hit Flickr's limits and get errors!
```

## Testing

Test the rate limiter:

```bash
python3 test_rate_limiter.py
```

## Need Help?

See [RATE_LIMITING.md](RATE_LIMITING.md) for complete documentation including:
- How the token bucket algorithm works
- Thread safety details
- Best practices
- Troubleshooting
- Advanced usage

## Key Points

✅ **No code changes required** - defaults are sensible and safe  
✅ **Thread-safe** - works with multi-threaded applications  
✅ **Automatic** - rate limiting is applied to all API calls  
✅ **Configurable** - adjust limits if needed  
✅ **Transparent** - your code continues to work as before  

⚠️ **Don't exceed 1.0 calls/second** without good reason - Flickr limits to 3600/hour  
⚠️ **Monitor your usage** - especially with long-running scripts  
