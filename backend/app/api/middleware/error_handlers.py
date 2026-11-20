import inspect
from functools import wraps
from typing import Any, Callable
from fastapi import HTTPException
from app.ai.errors import AIError


def handle_grounded_errors(func: Callable) -> Callable:
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except AIError as exc:
                headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
                status = 429 if exc.code == "rate_limit" else (401 if exc.code == "auth_error" else 502)
                raise HTTPException(status_code=status, detail=exc.user_message, headers=headers) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except HTTPException:
                raise
            except AIError as exc:
                headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
                status = 429 if exc.code == "rate_limit" else (401 if exc.code == "auth_error" else 502)
                raise HTTPException(status_code=status, detail=exc.user_message, headers=headers) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        return sync_wrapper
