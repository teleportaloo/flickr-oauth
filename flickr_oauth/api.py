"""
Flickr API wrapper providing compatibility with flickrapi-style methods.
Uses FlickrOAuth for authentication, adds rate limiting and walkers.
"""

from flickr_oauth.oauth import FlickrOAuth
from typing import Iterator, Optional
import xml.etree.ElementTree as ET
import time
import threading


class RateLimiter:
    """
    Token bucket rate limiter for API calls.
    Thread-safe implementation that ensures API rate limits are respected.
    """

    def __init__(self, calls_per_second: float = 1.0, burst_size: Optional[int] = None):
        """
        Initialize rate limiter.

        Args:
            calls_per_second: Maximum number of API calls per second (default: 1.0)
            burst_size: Maximum burst size (default: 2x calls_per_second)
        """
        self.calls_per_second = calls_per_second
        self.burst_size = burst_size or int(calls_per_second * 2)

        # Token bucket state
        self.tokens = float(self.burst_size)
        self.last_update = time.time()

        # Thread safety
        self.lock = threading.Lock()

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make an API call.

        Args:
            blocking: If True, wait until a token is available
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            True if permission granted, False if timeout/non-blocking and unavailable
        """
        start_time = time.time()

        while True:
            with self.lock:
                # Refill tokens based on time elapsed
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + elapsed * self.calls_per_second
                )
                self.last_update = now

                # Check if we have a token available
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True

                # Calculate time until next token
                time_to_next_token = (1.0 - self.tokens) / self.calls_per_second

            # Handle non-blocking or timeout
            if not blocking:
                return False

            if timeout is not None:
                if time.time() - start_time >= timeout:
                    return False

            # Sleep until next token (with small buffer)
            sleep_time = min(time_to_next_token, 0.1)
            time.sleep(sleep_time)

    def __call__(self, func):
        """
        Decorator to rate limit a function.

        Usage:
            @rate_limiter
            def api_call():
                ...
        """
        def wrapper(*args, **kwargs):
            self.acquire()
            return func(*args, **kwargs)
        return wrapper


class FlickrAPIWrapper:
    """
    Wrapper providing flickrapi-compatible interface with modern OAuth.

    Supports both explicit method classes (flickr.photos.getInfo) and
    dynamic attribute access for any Flickr API method.
    """

    def __init__(self, api_key: str, api_secret: str, cache: bool = True,
                 token_cache_path: Optional[str] = None,
                 rate_limit: float = 1.0, burst_size: Optional[int] = None):
        """
        Initialize Flickr API wrapper.

        Args:
            api_key: Your Flickr API key
            api_secret: Your Flickr API secret
            cache: Whether to cache tokens (always True for this implementation)
            token_cache_path: Optional path to token cache file
            rate_limit: Maximum API calls per second (default: 1.0)
                       Flickr allows 3600 requests/hour = 1 req/sec average
            burst_size: Maximum burst size for rate limiter (default: 2x rate_limit)
        """
        self.oauth = FlickrOAuth(api_key, api_secret, token_cache_path)
        self._api_cache = None  # Placeholder for response caching
        self.rate_limiter = RateLimiter(calls_per_second=rate_limit, burst_size=burst_size)

    @property
    def cache(self):
        """Compatibility property for cache."""
        return self._api_cache

    @cache.setter
    def cache(self, value):
        """Compatibility setter for cache."""
        self._api_cache = value

    def token_valid(self, perms: str = 'read') -> bool:
        """Check if authentication token is valid."""
        return self.oauth.token_valid(perms)

    def get_request_token(self, oauth_callback: str = 'oob'):
        """Get request token for OAuth flow."""
        return self.oauth.get_request_token(oauth_callback)

    def auth_url(self, perms: str = 'read') -> str:
        """Get authorization URL for user to visit."""
        return self.oauth.get_authorize_url(perms)

    def get_access_token(self, verifier: str):
        """Exchange verifier code for access token."""
        self.oauth.get_access_token(verifier)

    def authenticate(self, perms: str = 'read'):
        """Full authentication flow."""
        self.oauth.authenticate(perms)

    # API method call compatibility
    class _MethodGroup:
        """Helper class to handle method calls like flickr.photos.getInfo()"""
        def __init__(self, api_wrapper, prefix: str = ''):
            self._api = api_wrapper
            self._prefix = prefix

        def __getattr__(self, name: str):
            """Build method path like flickr.photos.getInfo"""
            new_prefix = f"{self._prefix}.{name}" if self._prefix else name

            # Check if this might be a final method or needs more nesting
            if '_' in name or name[0].islower():
                # Likely a method call
                def method_call(**kwargs):
                    method_name = f"flickr.{new_prefix}"
                    self._api.rate_limiter.acquire()
                    return self._api.oauth.call_method(method_name, **kwargs)
                return method_call
            else:
                # Return another group for chaining
                return FlickrAPIWrapper._MethodGroup(self._api, new_prefix)

    def __getattr__(self, name: str):
        """Handle attribute access for API methods."""
        # Prevent interception of internal cached attributes used by properties
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        # Return a method group for building API calls
        return self._MethodGroup(self, name)

    # Walker methods for iterating through paginated results

    def walk(self, user_id: str = 'me', tags: Optional[str] = None,
             per_page: int = 500, media: str = 'photos',
             extras: Optional[str] = None, **kwargs) -> Iterator[ET.Element]:
        """
        Walk through all photos for a user.

        Args:
            user_id: Flickr user ID or 'me'
            tags: Filter by tags
            per_page: Number of results per page
            media: Media type filter
            extras: Extra fields to retrieve
            **kwargs: Additional API parameters

        Yields:
            Photo elements
        """
        page = 1

        while True:
            params = {
                'user_id': user_id,
                'per_page': per_page,
                'page': page,
                'media': media,
                **kwargs
            }

            if tags:
                params['tags'] = tags

            if extras:
                params['extras'] = extras

            self.rate_limiter.acquire()
            response = self.oauth.call_method('flickr.photos.search', **params)
            photos_elem = response.find('photos')

            if photos_elem is None:
                break

            photos = photos_elem.findall('photo')

            if not photos:
                break

            for photo in photos:
                yield photo

            # Check if there are more pages
            total_pages = int(photos_elem.attrib.get('pages', 1))
            if page >= total_pages:
                break

            page += 1

    def walk_set(self, photoset_id: str, per_page: int = 500,
                 media: str = 'photos', extras: Optional[str] = None,
                 **kwargs) -> Iterator[ET.Element]:
        """
        Walk through all photos in a photoset.

        Args:
            photoset_id: Flickr photoset ID
            per_page: Number of results per page
            media: Media type filter
            extras: Extra fields to retrieve
            **kwargs: Additional API parameters

        Yields:
            Photo elements
        """
        page = 1

        while True:
            params = {
                'photoset_id': photoset_id,
                'per_page': per_page,
                'page': page,
                'media': media,
                **kwargs
            }

            if extras:
                params['extras'] = extras

            self.rate_limiter.acquire()
            response = self.oauth.call_method('flickr.photosets.getPhotos', **params)
            photoset_elem = response.find('photoset')

            if photoset_elem is None:
                break

            photos = photoset_elem.findall('photo')

            if not photos:
                break

            for photo in photos:
                yield photo

            # Check if there are more pages
            total_pages = int(photoset_elem.attrib.get('pages', 1))
            if page >= total_pages:
                break

            page += 1

    def data_walker(self, method_func, per_page: int = 500,
                    **kwargs) -> Iterator[ET.Element]:
        """
        Generic data walker for paginated results.

        Args:
            method_func: Method to call (should be a bound method from this API)
            per_page: Number of results per page
            **kwargs: Additional API parameters

        Yields:
            Elements from the response
        """
        page = 1

        # Extract method name from function
        method_name = None
        result_path = None
        item_tag = 'photo'

        # Try to determine the method name from method_func
        if hasattr(method_func, '__self__'):
            method_str = str(method_func)
            func_name = getattr(method_func, '__name__', '')

            if 'galleries' in method_str.lower() or 'galleries' in func_name.lower():
                method_name = 'flickr.galleries.getPhotos'
                result_path = 'photos'
                item_tag = 'photo'
            elif 'favorites' in method_str.lower() or 'favorites' in func_name.lower():
                method_name = 'flickr.favorites.getList'
                result_path = 'photos'
                item_tag = 'photo'
            elif 'photosets' in method_str.lower() or 'photosets' in func_name.lower():
                method_name = 'flickr.photosets.getPhotos'
                result_path = 'photoset'
                item_tag = 'photo'
        elif callable(method_func):
            method_str = str(method_func)
            if 'galleries' in method_str.lower():
                method_name = 'flickr.galleries.getPhotos'
                result_path = 'photos'
            elif 'favorites' in method_str.lower():
                method_name = 'flickr.favorites.getList'
                result_path = 'photos'

        if method_name is None:
            raise ValueError(f"Could not determine API method from method_func: {method_func}")

        while True:
            params = {
                'per_page': per_page,
                'page': page,
                **kwargs
            }

            self.rate_limiter.acquire()
            response = self.oauth.call_method(method_name, **params)
            result_elem = response.find(result_path)

            if result_elem is None:
                break

            items = result_elem.findall(item_tag)

            if not items:
                break

            for item in items:
                yield item

            # Check if there are more pages
            total_pages = int(result_elem.attrib.get('pages', 1))
            if page >= total_pages:
                break

            page += 1

    # Nested classes for explicit API methods

    class Photos:
        """Photos API methods"""
        def __init__(self, oauth: FlickrOAuth, rate_limiter: RateLimiter):
            self._oauth = oauth
            self._rate_limiter = rate_limiter

        def getSizes(self, photo_id: str, secret: Optional[str] = None) -> ET.Element:
            """Get available sizes for a photo."""
            params = {'photo_id': photo_id}
            if secret:
                params['secret'] = secret
            self._rate_limiter.acquire()
            return self._oauth.call_method('flickr.photos.getSizes', **params)

        def getInfo(self, photo_id: str, secret: Optional[str] = None) -> ET.Element:
            """Get info about a photo."""
            params = {'photo_id': photo_id}
            if secret:
                params['secret'] = secret
            self._rate_limiter.acquire()
            return self._oauth.call_method('flickr.photos.getInfo', **params)

        def search(self, user_id: str = 'me', **kwargs) -> ET.Element:
            """Search for photos."""
            params = {'user_id': user_id, **kwargs}
            self._rate_limiter.acquire()
            return self._oauth.call_method('flickr.photos.search', **params)

    class Galleries:
        """Galleries API methods"""
        def __init__(self, oauth: FlickrOAuth, rate_limiter: RateLimiter):
            self._oauth = oauth
            self._rate_limiter = rate_limiter

        def getPhotos(self, gallery_id: str, **kwargs) -> ET.Element:
            """Get photos from a gallery."""
            params = {'gallery_id': gallery_id, **kwargs}
            self._rate_limiter.acquire()
            return self._oauth.call_method('flickr.galleries.getPhotos', **params)

    class Favorites:
        """Favorites API methods"""
        def __init__(self, oauth: FlickrOAuth, rate_limiter: RateLimiter):
            self._oauth = oauth
            self._rate_limiter = rate_limiter

        def getList(self, user_id: str, **kwargs) -> ET.Element:
            """Get a user's favorites."""
            params = {'user_id': user_id, **kwargs}
            self._rate_limiter.acquire()
            return self._oauth.call_method('flickr.favorites.getList', **params)

    class Photosets:
        """Photosets API methods"""
        def __init__(self, oauth: FlickrOAuth, rate_limiter: RateLimiter):
            self._oauth = oauth
            self._rate_limiter = rate_limiter

        def getPhotos(self, photoset_id: str, **kwargs) -> ET.Element:
            """Get photos from a photoset."""
            params = {'photoset_id': photoset_id, **kwargs}
            self._rate_limiter.acquire()
            return self._oauth.call_method('flickr.photosets.getPhotos', **params)

    @property
    def photos(self):
        """Access photos API methods."""
        if not hasattr(self, '_photos'):
            self._photos = self.Photos(self.oauth, self.rate_limiter)
        return self._photos

    @property
    def galleries(self):
        """Access galleries API methods."""
        if not hasattr(self, '_galleries'):
            self._galleries = self.Galleries(self.oauth, self.rate_limiter)
        return self._galleries

    @property
    def favorites(self):
        """Access favorites API methods."""
        if not hasattr(self, '_favorites'):
            self._favorites = self.Favorites(self.oauth, self.rate_limiter)
        return self._favorites

    @property
    def photosets(self):
        """Access photosets API methods."""
        if not hasattr(self, '_photosets'):
            self._photosets = self.Photosets(self.oauth, self.rate_limiter)
        return self._photosets

    # Compatibility methods for old flickrapi underscore style
    def galleries_getPhotos(self, gallery_id: str, **kwargs):
        """Compatibility wrapper for flickr.galleries.getPhotos"""
        return self.galleries.getPhotos(gallery_id, **kwargs)

    def favorites_getList(self, user_id: str = 'me', **kwargs):
        """Compatibility wrapper for flickr.favorites.getList"""
        return self.favorites.getList(user_id, **kwargs)


class FlickrAPI(FlickrAPIWrapper):
    """
    Main API class matching flickrapi.FlickrAPI interface.
    """
    pass
