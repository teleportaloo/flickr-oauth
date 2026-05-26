# flickr-oauth

Modern Flickr OAuth 1.0a authentication and API wrapper for Python. Uses only the Python standard library — no external dependencies.

## Installation

```bash
pip install git+https://github.com/teleportaloo/flickr-oauth.git
```

## Quick start

```python
from flickr_oauth import FlickrAPI

flickr = FlickrAPI("your_api_key", "your_api_secret")
flickr.authenticate(perms='read')

# Dot-notation for any Flickr API method
info = flickr.photos.getInfo(photo_id='12345678')

# Walk through all photos in an album
for photo in flickr.walk_set(photoset_id='72157xyz'):
    print(photo.attrib['title'])
```

## Getting API keys

1. Go to https://www.flickr.com/services/apps/create/apply/
2. Apply for a non-commercial or commercial key
3. Note your API Key and Secret

## Authentication

On first run, the library will prompt you to visit a Flickr URL and enter a verification code. After that, tokens are cached in `~/.flickr/oauth-tokens.json` and reused automatically.

For write operations (adding tags, comments, notes), authenticate with:

```python
flickr.authenticate(perms='write')
```

### Token cache location

By default tokens are stored in `~/.flickr/oauth-tokens.json`. Override with:

- **Constructor argument**: `FlickrAPI(key, secret, token_cache_path='/path/to/tokens.json')`
- **Environment variable**: `FLICKR_TOKEN_CACHE=/path/to/tokens.json`

## API methods

### Explicit methods

```python
flickr.photos.getInfo(photo_id='12345')
flickr.photos.getSizes(photo_id='12345')
flickr.photos.search(user_id='me', tags='astronomy')
flickr.photosets.getPhotos(photoset_id='72157xyz')
flickr.favorites.getList(user_id='me')
flickr.galleries.getPhotos(gallery_id='xyz')
```

### Dynamic method access

Any Flickr API method works via dot-notation:

```python
flickr.photos.comments.getList(photo_id='12345')
flickr.groups.pools.getPhotos(group_id='xyz')
```

### Write operations (POST)

For methods that modify data, use the OAuth object directly:

```python
flickr.oauth.call_method_post('flickr.photos.addTags',
                               photo_id='12345',
                               tags='astronomy')
```

### Walkers (pagination)

```python
# Walk all photos for a user
for photo in flickr.walk(user_id='me'):
    print(photo.attrib['title'])

# Walk a photoset/album
for photo in flickr.walk_set(photoset_id='72157xyz'):
    print(photo.attrib['title'])
```

## Rate limiting

The API wrapper includes a token-bucket rate limiter (default: 1 request/second with burst of 2). Flickr allows 3600 requests/hour.

```python
# Adjust rate limit
flickr = FlickrAPI(key, secret, rate_limit=2.0, burst_size=5)
```

## Features

- OAuth 1.0a with HMAC-SHA1 signing
- RFC 3986 percent-encoding for POST requests
- Automatic token caching with secure file permissions
- Retry on transient Flickr API errors (500, 502, 503, 504)
- Thread-safe rate limiting
- Zero external dependencies — pure Python standard library
- Compatible with Python 3.8+

## License

MIT
