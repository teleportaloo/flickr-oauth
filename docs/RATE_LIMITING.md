# Rate Limiting in Flickr API Wrapper

## Overview

The Flickr API wrapper now includes automatic rate limiting to ensure you don't exceed Flickr's API limits. The rate limiter uses a **token bucket algorithm** that is thread-safe and configurable.

## Flickr API Limits

According to Flickr's official documentation:
- **3600 requests per hour** per API key (API calls)
- This averages to **1 request per second**
- Bursts are generally tolerated but shouldn't be relied upon

### API Calls vs Image Downloads

It's important to distinguish between two types of requests:

1. **API Calls** (to `api.flickr.com`)
   - Limited to 3600/hour
   - Examples: `getSizes()`, `getInfo()`, `search()`
   - **Always rate limited** by the wrapper

2. **Image Downloads** (from `live.staticflickr.com` or CDN)
   - Separate infrastructure (CDN)
   - Different (likely higher) limits
   - **Also rate limited** by default for good citizenship
   - Can be disabled if needed

The FlickrFrame wrapper rate limits **both** types by default to be respectful of Flickr's infrastructure.

## Usage

### Basic Usage (Default Settings)

The wrapper automatically applies rate limiting with sensible defaults:

```python
from flickr_oauth import FlickrAPI

# Default: 1 call/second, burst size of 2
flickr = FlickrAPI(API_KEY, API_SECRET)

# All API calls are automatically rate limited
for photo in flickr.walk(user_id='me', per_page=100):
    # This will automatically pace requests at 1/second
    info = flickr.photos.getInfo(photo_id=photo.attrib['id'])
```

### Custom Rate Limits

You can customize the rate limiting behavior:

```python
# More conservative: 0.5 calls/second (1800 per hour)
flickr = FlickrAPI(
    API_KEY, 
    API_SECRET,
    rate_limit=0.5,
    burst_size=1
)

# More aggressive: 2 calls/second (use with caution!)
flickr = FlickrAPI(
    API_KEY, 
    API_SECRET,
    rate_limit=2.0,
    burst_size=5
)
```

### Parameters

- **`rate_limit`**: Maximum API calls per second (float)
  - Default: `1.0` (3600 requests/hour)
  - Recommended range: `0.5` to `1.0` for safety
  - Maximum safe: `1.0` (don't exceed Flickr's limits)

- **`burst_size`**: Maximum number of calls that can be made in quick succession (int)
  - Default: `2 × rate_limit`
  - Allows initial burst before throttling kicks in
  - Useful for scripts that need quick startup

## How It Works

### Token Bucket Algorithm

The rate limiter uses a token bucket algorithm:

1. **Tokens**: You start with a bucket of tokens (size = `burst_size`)
2. **Refilling**: Tokens refill at a constant rate (`rate_limit` per second)
3. **Consuming**: Each API call consumes one token
4. **Waiting**: If no tokens available, the call waits until one is available

### Example Timeline

With `rate_limit=1.0` and `burst_size=2`:

```
Time    Tokens  Action
----    ------  ------
0.0s    2.0     Initial state
0.0s    1.0     Call 1 (instant - uses burst)
0.0s    0.0     Call 2 (instant - uses burst)
0.0s    0.0     Call 3 (waits...)
1.0s    1.0     Token refilled
1.0s    0.0     Call 3 proceeds
2.0s    1.0     Token refilled
2.0s    0.0     Call 4 proceeds
```

## Rate Limiter Class

You can also use the `RateLimiter` class independently:

```python
from flickr_oauth import RateLimiter

# Create a rate limiter
limiter = RateLimiter(calls_per_second=1.0, burst_size=2)

# Use it manually
limiter.acquire()  # Blocks until a token is available
make_api_call()

# Non-blocking mode
if limiter.acquire(blocking=False):
    make_api_call()
else:
    print("Rate limit reached, skipping call")

# With timeout
if limiter.acquire(blocking=True, timeout=5.0):
    make_api_call()
else:
    print("Timed out waiting for rate limit")
```

### As a Decorator

```python
from flickr_oauth import RateLimiter

limiter = RateLimiter(calls_per_second=1.0)

@limiter
def my_api_call():
    # This function is automatically rate limited
    return flickr.photos.getInfo(photo_id='12345')

# Multiple calls will be automatically paced
for i in range(10):
    result = my_api_call()
```

## Thread Safety

The rate limiter is **thread-safe** and can be used with multiple threads:

```python
import threading

flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=1.0)

def worker(photo_ids):
    for photo_id in photo_ids:
        # Automatically rate limited across all threads
        info = flickr.photos.getInfo(photo_id=photo_id)

# Multiple threads share the same rate limiter
threads = [
    threading.Thread(target=worker, args=(photos1,)),
    threading.Thread(target=worker, args=(photos2,)),
]

for t in threads:
    t.start()
```

## Best Practices

### 1. Use Conservative Limits

Start with conservative limits to avoid hitting Flickr's restrictions:

```python
# Safe default - well under Flickr's limit
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=0.9, burst_size=2)
```

### 2. Monitor Your Usage

Keep track of how many requests your scripts make:

```python
call_count = 0

for photo in flickr.walk(user_id='me'):
    info = flickr.photos.getInfo(photo_id=photo.attrib['id'])
    call_count += 1
    
    if call_count % 100 == 0:
        print(f"Made {call_count} API calls")
```

### 3. Handle Large Operations Carefully

For operations that make many API calls, consider:

- Running during off-peak hours
- Breaking into smaller batches
- Using larger `per_page` values to reduce calls

```python
# Better: One call gets 500 photos
for photo in flickr.walk(user_id='me', per_page=500):
    process(photo)

# Worse: Multiple calls to get same photos
for photo in flickr.walk(user_id='me', per_page=10):
    process(photo)
```

### 4. Cache Results

Combine rate limiting with caching to minimize API calls:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_photo_info(photo_id):
    return flickr.photos.getInfo(photo_id=photo_id)

# Subsequent calls with same ID use cache
info1 = get_photo_info('12345')  # API call
info2 = get_photo_info('12345')  # From cache
```

## Testing

Run the test script to see the rate limiter in action:

```bash
python3 test_rate_limiter.py
```

This will demonstrate:
- Basic rate limiting behavior
- Different rate configurations
- Non-blocking mode
- Timeout mode
- Decorator usage

## Troubleshooting

### "Too Many Requests" Errors

If you still get rate limit errors from Flickr:

1. Reduce your `rate_limit` value:
   ```python
   flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=0.5)
   ```

2. Reduce `burst_size` to prevent initial bursts:
   ```python
   flickr = FlickrAPI(API_KEY, API_SECRET, burst_size=1)
   ```

3. Check if you're running multiple scripts with the same API key

### Slow Performance

If requests seem too slow:

1. Check your `rate_limit` setting (don't exceed 1.0)
2. Increase `burst_size` for faster startup
3. Optimize your code to make fewer API calls
4. Use `per_page` parameter effectively

### Rate Limiter Not Working

If rate limiting doesn't seem to apply:

1. Make sure you're creating the API instance correctly
2. Check that you're not directly calling `oauth.call_method()`
3. Verify you're using methods that go through the wrapper

## API Coverage

Rate limiting is automatically applied to:

### API Calls (Always Rate Limited)
- ✅ `flickr.photos.getInfo()`
- ✅ `flickr.photos.getSizes()`
- ✅ `flickr.photos.search()`
- ✅ `flickr.photosets.getPhotos()`
- ✅ `flickr.galleries.getPhotos()`
- ✅ `flickr.favorites.getList()`
- ✅ `flickr.walk()` (iterator)
- ✅ `flickr.walk_set()` (iterator)
- ✅ `flickr.data_walker()` (iterator)
- ✅ Dynamic method calls (e.g., `flickr.people.getInfo()`)
- ✅ All other API methods accessed through the wrapper

### Image Downloads (Rate Limited by Default)
- ✅ Image downloads via `PhotoDownloader` class
- ✅ Downloads from Flickr's CDN (live.staticflickr.com)
- ⚙️ Can be disabled if needed (see below)

### Controlling Image Download Rate Limiting

Image downloads are rate limited by default, but you can control this:

```python
from photo_downloader import PhotoDownloader

# Default: Image downloads ARE rate limited
downloader = PhotoDownloader(flickr, environment)

# Disable rate limiting for image downloads (faster, but less polite)
downloader = PhotoDownloader(flickr, environment, rate_limit_downloads=False)
```

**When to disable image download rate limiting:**
- You need maximum download speed
- You're downloading a small number of images
- You have permission/special arrangement with Flickr

**When to keep it enabled (recommended):**
- Bulk downloads (hundreds/thousands of images)
- Automated/scheduled syncs
- Being a good citizen on Flickr's network
- Avoiding potential temporary bans

## Migration Notes

If you're updating from an older version without rate limiting:

**No code changes required!** Rate limiting is automatically applied with sensible defaults.

If you want to keep the old behavior (no rate limiting):

```python
# Set a very high rate limit (not recommended)
flickr = FlickrAPI(API_KEY, API_SECRET, rate_limit=100.0, burst_size=1000)
```

## Additional Resources

- [Flickr API Documentation](https://www.flickr.com/services/api/)
- [Flickr API Terms of Service](https://www.flickr.com/services/api/tos/)
- [Token Bucket Algorithm](https://en.wikipedia.org/wiki/Token_bucket)
