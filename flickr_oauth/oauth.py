"""
Modern Flickr OAuth 1.0a authentication module.
Provides OAuth 1.0a signing, token caching, and API method calls.
Uses only Python standard library — no external dependencies.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
import urllib.request
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Tuple


class FlickrOAuth:
    """
    Handles OAuth 1.0a authentication for Flickr API.
    Caches tokens and provides authentication URLs when needed.
    """

    # Flickr API endpoints
    REQUEST_TOKEN_URL = "https://www.flickr.com/services/oauth/request_token"
    AUTHORIZE_URL = "https://www.flickr.com/services/oauth/authorize"
    ACCESS_TOKEN_URL = "https://www.flickr.com/services/oauth/access_token"
    REST_ENDPOINT = "https://api.flickr.com/services/rest/"

    def __init__(self, api_key: str, api_secret: str, token_cache_path: Optional[str] = None):
        """
        Initialize Flickr OAuth handler.

        Args:
            api_key: Your Flickr API key
            api_secret: Your Flickr API secret
            token_cache_path: Path to cache file. Options:
                - None: Uses ~/.flickr/oauth-tokens.json (or FLICKR_TOKEN_CACHE env var)
                - Absolute path: Uses specified path
                - Relative path: Relative to current working directory

        Note for cron jobs:
            When running as root via cron, it's recommended to specify an
            explicit path like '/etc/flickr/oauth-tokens.json' or use the
            FLICKR_TOKEN_CACHE environment variable for consistency.
        """
        self.api_key = api_key
        self.api_secret = api_secret

        # Set up cache path
        if token_cache_path is None:
            # Check for environment variable first (useful for cron)
            env_cache_path = os.environ.get('FLICKR_TOKEN_CACHE')
            if env_cache_path:
                self.token_cache_path = Path(env_cache_path)
            else:
                # Default to user's home directory
                cache_dir = Path.home() / ".flickr"
                cache_dir.mkdir(exist_ok=True, mode=0o700)
                self.token_cache_path = cache_dir / "oauth-tokens.json"
        else:
            self.token_cache_path = Path(token_cache_path)

        # Ensure parent directory exists
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # OAuth tokens
        self.oauth_token: Optional[str] = None
        self.oauth_token_secret: Optional[str] = None
        self.request_token: Optional[str] = None
        self.request_token_secret: Optional[str] = None

        # Try to load cached tokens
        self._load_cached_tokens()

    def _load_cached_tokens(self) -> bool:
        """Load OAuth tokens from cache file."""
        if not self.token_cache_path.exists():
            return False

        try:
            with open(self.token_cache_path, 'r') as f:
                data = json.load(f)

            # Check if we have tokens for this API key
            key_hash = hashlib.md5(self.api_key.encode()).hexdigest()
            if key_hash in data:
                token_data = data[key_hash]
                self.oauth_token = token_data.get('oauth_token')
                self.oauth_token_secret = token_data.get('oauth_token_secret')
                return True
        except (json.JSONDecodeError, IOError):
            pass

        return False

    def _save_tokens(self):
        """Save OAuth tokens to cache file with secure permissions."""
        # Load existing cache
        if self.token_cache_path.exists():
            try:
                with open(self.token_cache_path, 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                data = {}
        else:
            data = {}

        # Save tokens for this API key
        key_hash = hashlib.md5(self.api_key.encode()).hexdigest()
        data[key_hash] = {
            'oauth_token': self.oauth_token,
            'oauth_token_secret': self.oauth_token_secret
        }

        # Write to file with secure permissions (0600 - owner read/write only)
        with open(self.token_cache_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Set file permissions to 0600 (owner read/write only)
        os.chmod(self.token_cache_path, 0o600)

    def _generate_signature(self, method: str, url: str, params: Dict[str, str],
                           token_secret: str = "") -> str:
        """
        Generate OAuth signature for a request.

        Args:
            method: HTTP method (GET or POST)
            url: Base URL
            params: Request parameters
            token_secret: OAuth token secret (if available)

        Returns:
            OAuth signature string (base64 encoded)
        """
        # Sort parameters
        sorted_params = sorted(params.items())
        param_string = urllib.parse.urlencode(sorted_params)

        # Create signature base string
        base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"

        # Create signing key
        signing_key = f"{urllib.parse.quote(self.api_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"

        # Generate signature (HMAC-SHA1, base64 encoded)
        signature = hmac.new(
            signing_key.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha1
        ).digest()

        # Return base64 encoded signature
        return base64.b64encode(signature).decode('utf-8')

    def _make_oauth_params(self, extra_params: Optional[Dict[str, str]] = None,
                          include_token: bool = False) -> Dict[str, str]:
        """Create base OAuth parameters."""
        params = {
            'oauth_nonce': hashlib.md5(str(time.time()).encode()).hexdigest(),
            'oauth_timestamp': str(int(time.time())),
            'oauth_consumer_key': self.api_key,
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_version': '1.0',
        }

        if include_token and self.oauth_token:
            params['oauth_token'] = self.oauth_token

        if extra_params:
            params.update(extra_params)

        return params

    def _request(self, url: str, params: Dict[str, str],
                token_secret: str = "") -> str:
        """Make an OAuth signed request."""
        # Add signature
        params['oauth_signature'] = self._generate_signature('GET', url, params, token_secret)

        # Build full URL
        full_url = f"{url}?{urllib.parse.urlencode(params)}"

        # Make request
        with urllib.request.urlopen(full_url) as response:
            return response.read().decode('utf-8')

    def get_request_token(self, oauth_callback: str = 'oob') -> Tuple[str, str]:
        """
        Get a request token from Flickr.

        Args:
            oauth_callback: OAuth callback (use 'oob' for out-of-band)

        Returns:
            Tuple of (request_token, request_token_secret)
        """
        params = self._make_oauth_params({'oauth_callback': oauth_callback})
        response = self._request(self.REQUEST_TOKEN_URL, params)

        # Parse response
        parsed = dict(urllib.parse.parse_qsl(response))
        self.request_token = parsed['oauth_token']
        self.request_token_secret = parsed['oauth_token_secret']

        return self.request_token, self.request_token_secret

    def get_authorize_url(self, perms: str = 'read') -> str:
        """
        Get the authorization URL for the user to visit.

        Args:
            perms: Permission level ('read', 'write', or 'delete')

        Returns:
            Authorization URL
        """
        if not self.request_token:
            raise ValueError("Must call get_request_token() first")

        params = {
            'oauth_token': self.request_token,
            'perms': perms
        }

        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, verifier: str):
        """
        Exchange request token for access token.

        Args:
            verifier: OAuth verifier code from user
        """
        if not self.request_token or not self.request_token_secret:
            raise ValueError("Must call get_request_token() first")

        params = self._make_oauth_params({
            'oauth_token': self.request_token,
            'oauth_verifier': verifier
        })

        response = self._request(
            self.ACCESS_TOKEN_URL,
            params,
            self.request_token_secret
        )

        # Parse response
        parsed = dict(urllib.parse.parse_qsl(response))
        self.oauth_token = parsed['oauth_token']
        self.oauth_token_secret = parsed['oauth_token_secret']

        # Save tokens
        self._save_tokens()

    def token_valid(self, perms: str = 'read') -> bool:
        """
        Check if we have valid cached tokens.

        Args:
            perms: Required permission level

        Returns:
            True if tokens exist and are valid
        """
        if not self.oauth_token or not self.oauth_token_secret:
            return False

        # Try to make a test API call
        try:
            self.call_method('flickr.test.login')
            return True
        except:
            return False

    # Flickr error codes that indicate a transient service issue worth retrying
    _TRANSIENT_ERROR_CODES = {'201', '500', '502', '503', '504'}

    def call_method(self, method: str, **kwargs) -> ET.Element:
        """
        Call a Flickr API method (GET), retrying on transient service errors.

        Args:
            method: Flickr API method name (e.g., 'flickr.photos.getInfo')
            **kwargs: Additional parameters for the API call

        Returns:
            XML ElementTree root element with response
        """
        if not self.oauth_token or not self.oauth_token_secret:
            raise ValueError("Not authenticated. Call authenticate() first.")

        for attempt in range(10):
            # Build parameters (must be rebuilt each attempt - oauth_timestamp changes)
            params = self._make_oauth_params(include_token=True)
            params['method'] = method
            params['api_key'] = self.api_key

            for key, value in kwargs.items():
                if value is not None:
                    params[key] = str(value)

            params['oauth_signature'] = self._generate_signature(
                'GET',
                self.REST_ENDPOINT,
                params,
                self.oauth_token_secret
            )

            full_url = f"{self.REST_ENDPOINT}?{urllib.parse.urlencode(params)}"

            with urllib.request.urlopen(full_url) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)

            if root.attrib.get('stat') == 'fail':
                err = root.find('err')
                error_msg = err.attrib.get('msg', 'Unknown error')
                error_code = err.attrib.get('code', 'unknown')
                if error_code in self._TRANSIENT_ERROR_CODES and attempt < 9:
                    delay = min(5 * (2 ** attempt), 60)
                    print(f"      Flickr API error {error_code} on {method}: {error_msg}, retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                raise Exception(f"Flickr API error {error_code}: {error_msg}")

            if attempt > 0:
                print(f"      Flickr API call succeeded after {attempt + 1} attempts.")
            return root

    def call_method_post(self, method: str, **kwargs) -> ET.Element:
        """
        Call a Flickr API method using POST (required for write methods).

        Uses RFC 3986 percent-encoding throughout to ensure the OAuth
        signature matches the POST body exactly.

        Args:
            method: Flickr API method name (e.g., 'flickr.photos.addTags')
            **kwargs: Additional parameters for the API call

        Returns:
            XML ElementTree root element with response
        """
        if not self.oauth_token or not self.oauth_token_secret:
            raise ValueError("Not authenticated. Call authenticate() first.")

        params = self._make_oauth_params(include_token=True)
        params['method'] = method
        params['api_key'] = self.api_key

        for key, value in kwargs.items():
            if value is not None:
                params[key] = str(value)

        # Build signature using RFC 3986 percent-encoding (not urlencode's +)
        sorted_params = sorted(params.items())
        param_string = '&'.join(
            f'{urllib.parse.quote(k, safe="")}'
            f'={urllib.parse.quote(str(v), safe="")}'
            for k, v in sorted_params
        )
        base_string = (
            f'POST'
            f'&{urllib.parse.quote(self.REST_ENDPOINT, safe="")}'
            f'&{urllib.parse.quote(param_string, safe="")}'
        )
        signing_key = (
            f'{urllib.parse.quote(self.api_secret, safe="")}'
            f'&{urllib.parse.quote(self.oauth_token_secret, safe="")}'
        )
        sig = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(),
                     hashlib.sha1).digest()
        ).decode()
        params['oauth_signature'] = sig

        # POST body must use the same encoding as the signature
        post_data = '&'.join(
            f'{urllib.parse.quote(k, safe="")}'
            f'={urllib.parse.quote(str(v), safe="")}'
            for k, v in params.items()
        ).encode('utf-8')
        req = urllib.request.Request(
            self.REST_ENDPOINT, data=post_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        if root.attrib.get('stat') == 'fail':
            err = root.find('err')
            error_msg = err.attrib.get('msg', 'Unknown error')
            error_code = err.attrib.get('code', 'unknown')
            raise Exception(f"Flickr API error {error_code}: {error_msg}")

        return root

    def authenticate(self, perms: str = 'read'):
        """
        Full authentication flow. Will prompt user if tokens not cached.

        Args:
            perms: Permission level ('read', 'write', or 'delete')
        """
        if self.token_valid(perms):
            print("Using cached authentication")
            return

        # Need to authenticate
        print("=" * 70)
        print("FLICKR AUTHENTICATION REQUIRED")
        print("=" * 70)

        # Get request token
        self.get_request_token()

        # Get authorization URL
        auth_url = self.get_authorize_url(perms)

        print("\nPlease visit this URL to authorize the application:")
        print(f"\n{auth_url}\n")
        print("After authorizing, you'll receive a verification code.")

        # Get verifier from user
        verifier = input("Enter verification code: ").strip()

        # Exchange for access token
        self.get_access_token(verifier)

        print("Authentication successful! Tokens cached for future use.")
