"""
flickr-oauth: Modern Flickr OAuth 1.0a authentication and API wrapper.

Provides OAuth 1.0a authentication, token caching, rate limiting,
and a convenient API wrapper for the Flickr REST API.

Usage:
    from flickr_oauth import FlickrAPI

    flickr = FlickrAPI("your_api_key", "your_api_secret")
    flickr.authenticate(perms='read')

    # Use dot-notation for any Flickr API method
    result = flickr.photos.getInfo(photo_id='12345678')

    # Or call methods directly
    result = flickr.oauth.call_method('flickr.photos.getInfo', photo_id='12345678')
"""

from flickr_oauth.oauth import FlickrOAuth
from flickr_oauth.api import FlickrAPI, FlickrAPIWrapper, RateLimiter

__version__ = "1.0.0"
__all__ = ["FlickrOAuth", "FlickrAPI", "FlickrAPIWrapper", "RateLimiter"]
