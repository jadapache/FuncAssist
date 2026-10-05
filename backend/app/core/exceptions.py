"""
Custom exception hierarchy for QA_MGMT application.

Provides domain-specific exceptions that map to appropriate HTTP status codes
and can be caught by error handling middleware for consistent error responses.
"""

from fastapi import HTTPException
from typing import Any, Optional


class BaseApplicationException(HTTPException):
    """Base exception for all application-specific errors.
    
    Inherits from HTTPException to integrate seamlessly with FastAPI
    error handling middleware.
    """
    
    status_code: int = 500
    detail: str = "Internal server error"
    
    def __init__(
        self,
        detail: Optional[str] = None,
        status_code: Optional[int] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        if detail is not None:
            self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        
        super().__init__(
            status_code=self.status_code,
            detail=self.detail,
            headers=headers,
        )


class FeatureNotFoundError(BaseApplicationException):
    """Raised when a requested feature or resource is not found.
    
    Maps to HTTP 404 Not Found.
    """
    
    status_code = 404
    detail = "Feature or resource not found"
    
    def __init__(
        self,
        resource: str,
        identifier: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"{resource} not found"
        if identifier:
            detail = f"{resource} '{identifier}' not found"
        super().__init__(detail=detail, status_code=404, headers=headers)


class MissingContextError(BaseApplicationException):
    """Raised when required context or configuration is missing.
    
    Maps to HTTP 400 Bad Request.
    """
    
    status_code = 400
    detail = "Missing required context or configuration"
    
    def __init__(
        self,
        context_type: str,
        reason: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"Missing {context_type}"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(detail=detail, status_code=400, headers=headers)


class ValidationError(BaseApplicationException):
    """Raised when input validation fails.
    
    Maps to HTTP 422 Unprocessable Entity.
    """
    
    status_code = 422
    detail = "Validation failed"
    
    def __init__(
        self,
        field: str,
        reason: str,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"Validation failed for '{field}': {reason}"
        super().__init__(detail=detail, status_code=422, headers=headers)


class IntegrationError(BaseApplicationException):
    """Raised when external service integration fails.
    
    Maps to HTTP 502 Bad Gateway.
    """
    
    status_code = 502
    detail = "External service integration failed"
    
    def __init__(
        self,
        service: str,
        reason: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"{service} integration failed"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(detail=detail, status_code=502, headers=headers)


class AIProviderError(BaseApplicationException):
    """Raised when AI provider operations fail.
    
    Maps to HTTP 502 Bad Gateway for external provider issues,
    or 400 Bad Request for configuration issues.
    """
    
    status_code = 502
    detail = "AI provider error"
    
    def __init__(
        self,
        provider: str,
        reason: str,
        is_config_error: bool = False,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"{provider} provider error: {reason}"
        status = 400 if is_config_error else 502
        super().__init__(detail=detail, status_code=status, headers=headers)


class DuplicateResourceError(BaseApplicationException):
    """Raised when attempting to create a duplicate resource.
    
    Maps to HTTP 409 Conflict.
    """
    
    status_code = 409
    detail = "Resource already exists"
    
    def __init__(
        self,
        resource: str,
        identifier: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"{resource} already exists"
        if identifier:
            detail = f"{resource} '{identifier}' already exists"
        super().__init__(detail=detail, status_code=409, headers=headers)


class OperationNotAllowedError(BaseApplicationException):
    """Raised when an operation is not allowed in the current state.
    
    Maps to HTTP 403 Forbidden.
    """
    
    status_code = 403
    detail = "Operation not allowed"
    
    def __init__(
        self,
        operation: str,
        reason: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"Operation '{operation}' not allowed"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(detail=detail, status_code=403, headers=headers)


class StorageError(BaseApplicationException):
    """Raised when storage operations fail.
    
    Maps to HTTP 500 Internal Server Error.
    """
    
    status_code = 500
    detail = "Storage operation failed"
    
    def __init__(
        self,
        operation: str,
        reason: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        detail = f"Storage operation '{operation}' failed"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(detail=detail, status_code=500, headers=headers)
