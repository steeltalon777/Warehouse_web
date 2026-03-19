"""
Deprecated legacy HTTP client for SyncServer API.

Active Django runtime integrations should use apps.sync_client.client.SyncServerClient.
This module remains only for legacy auth/session-oriented flows that still depend on
user-token based request handling.

This module provides a basic HTTP client for communicating with SyncServer.
It handles authentication headers, error handling, and JSON parsing.

Usage:
    from apps.sync_client.simple_client import SyncClient
    
    client = SyncClient()
    response = client.get("/some/endpoint")
    
    # With custom headers
    response = client.post("/create", json={"key": "value"})
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class SyncAPIError(Exception):
    """Base exception for SyncServer API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class SyncClient:
    """
    Base HTTP client for SyncServer API communication.
    
    This client provides basic HTTP methods with automatic header injection
    and error handling for SyncServer API calls.
    
    Attributes:
        base_url (str): Base URL for SyncServer API from settings
        timeout (float): Request timeout in seconds (default: 10)
    """
    
    def __init__(self, timeout: Optional[float] = None) -> None:
        """
        Initialize SyncClient.
        
        Args:
            timeout: Request timeout in seconds. Defaults to SYNC_SERVER_TIMEOUT
                    from settings or 10 seconds.
        
        Raises:
            RuntimeError: If SYNC_SERVER_URL is not configured.
        """
        self.base_url = getattr(settings, "SYNC_SERVER_URL", "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("SYNC_SERVER_URL is not configured in settings.")
        
        self.timeout = timeout or float(getattr(settings, "SYNC_SERVER_TIMEOUT", 10))
        
        # Get device token from settings
        self.device_token = getattr(settings, "SYNC_DEVICE_TOKEN", "").strip()
        
        logger.debug(
            "SyncClient initialized",
            extra={"base_url": self.base_url, "timeout": self.timeout}
        )
    
    def _get_headers(self, request) -> dict[str, str]:
        """
        Build headers for SyncServer request.
        
        Args:
            request: Django HttpRequest object or None
            
        Returns:
            dict: Headers for HTTP request
            
        Note:
            X-User-Token is extracted from Django session if request is provided.
            X-Device-Token is taken from settings.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        # Add device token from settings
        if self.device_token:
            headers["X-Device-Token"] = self.device_token
        
        # Try to get user token from session if request is provided
        if request and hasattr(request, 'session'):
            # First try new SyncServer identity structure
            user_token = request.session.get('sync_user_token')

            # Fall back to legacy user_token key
            if not user_token:
                user_token = request.session.get('user_token')

            if user_token:
                headers["X-User-Token"] = str(user_token)
        
        return headers
    
    def _build_url(self, path: str) -> str:
        """
        Build full URL from path.
        
        Args:
            path: API endpoint path (with or without leading slash)
            
        Returns:
            str: Full URL
        """
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"
    
    def _handle_response(self, response: httpx.Response, method: str, path: str) -> Any:
        """
        Handle HTTP response, parse JSON, and raise errors if needed.
        
        Args:
            response: httpx.Response object
            method: HTTP method used
            path: API path requested
            
        Returns:
            Parsed JSON response or None for 204 No Content
            
        Raises:
            SyncAPIError: If response status is >= 400
        """
        if response.status_code >= 400:
            self._log_error(method, path, response.status_code, response.text)
            
            try:
                error_data = response.json()
                error_message = error_data.get("detail", str(error_data))
            except ValueError:
                error_message = response.text or f"HTTP {response.status_code}"
            
            raise SyncAPIError(
                message=error_message,
                status_code=response.status_code,
                response_data=error_data if 'error_data' in locals() else None,
            )
        
        if response.status_code == 204:
            return None
        
        if not response.content:
            return None
        
        try:
            return response.json()
        except ValueError as e:
            logger.warning(
                "Failed to parse JSON response",
                extra={"method": method, "path": path, "status": response.status_code}
            )
            return {"raw_response": response.text}
    
    def _log_error(self, method: str, path: str, status_code: int, response_text: str) -> None:
        """Log failed request details."""
        logger.error(
            "SyncServer request failed",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "response": response_text[:500],  # Limit log size
            }
        )
    
    def _request(
        self,
        method: str,
        path: str,
        request=None,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """
        Make HTTP request to SyncServer.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            path: API endpoint path
            request: Django HttpRequest object (for session access)
            json: JSON data for request body
            params: Query parameters
            
        Returns:
            Parsed response data
            
        Raises:
            SyncAPIError: For API errors
            httpx.RequestError: For network errors
        """
        url = self._build_url(path)
        headers = self._get_headers(request)
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                )
        except httpx.TimeoutException as e:
            logger.error(
                "SyncServer request timeout",
                extra={"method": method, "path": path, "timeout": self.timeout}
            )
            raise SyncAPIError(f"Request timeout after {self.timeout}s") from e
        except httpx.RequestError as e:
            logger.error(
                "SyncServer connection error",
                extra={"method": method, "path": path, "error": str(e)}
            )
            raise SyncAPIError(f"Connection error: {str(e)}") from e
        
        return self._handle_response(response, method, path)
    
    def get(self, path: str, request=None, params: Optional[dict] = None) -> Any:
        """
        Make GET request to SyncServer.
        
        Args:
            path: API endpoint path
            request: Django HttpRequest object (for session access)
            params: Query parameters
            
        Returns:
            Parsed response data
        """
        return self._request("GET", path, request=request, params=params)
    
    def post(self, path: str, request=None, json: Optional[dict] = None, params: Optional[dict] = None) -> Any:
        """
        Make POST request to SyncServer.
        
        Args:
            path: API endpoint path
            request: Django HttpRequest object (for session access)
            json: JSON data for request body
            params: Query parameters
            
        Returns:
            Parsed response data
        """
        return self._request("POST", path, request=request, json=json, params=params)
    
    def patch(self, path: str, request=None, json: Optional[dict] = None) -> Any:
        """
        Make PATCH request to SyncServer.
        
        Args:
            path: API endpoint path
            request: Django HttpRequest object (for session access)
            json: JSON data for request body
            
        Returns:
            Parsed response data
        """
        return self._request("PATCH", path, request=request, json=json)
    
    def delete(self, path: str, request=None) -> Any:
        """
        Make DELETE request to SyncServer.
        
        Args:
            path: API endpoint path
            request: Django HttpRequest object (for session access)
            
        Returns:
            Parsed response data
        """
        return self._request("DELETE", path, request=request)


# Convenience function for quick usage
def get_sync_client(timeout: Optional[float] = None) -> SyncClient:
    """
    Get a SyncClient instance.
    
    Args:
        timeout: Optional timeout override
        
    Returns:
        SyncClient instance
    """
    return SyncClient(timeout=timeout)