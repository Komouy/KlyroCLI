"""
error_handler.py — Error Classification & Retry Policy

Classifies errors into:
  - PERMANENT: don't retry (401, 403, validation errors)
  - TRANSIENT: retry with backoff (timeout, connection errors)
  - RATE_LIMIT: fallback to next provider (429, quota)
  - AUTHENTICATION: ask user (API key invalid)
"""

from enum import Enum
from typing import Optional, Callable
import time
import re


class ErrorClass(Enum):
    """Error classification for retry/fallback decisions."""
    PERMANENT = "permanent"           # Don't retry
    TRANSIENT = "transient"           # Retry with backoff
    RATE_LIMIT = "rate_limit"         # Backoff + fallback
    AUTHENTICATION = "authentication" # Ask user
    UNKNOWN = "unknown"               # Default


class ErrorClassifier:
    """Classify errors based on type and message."""
    
    # Error patterns
    PERMANENT_PATTERNS = [
        r"401|unauthorized|unauthenticated",
        r"403|forbidden|permission denied",
        r"invalid.*argument|invalid.*parameter",
        r"not found|404|no such",
        r"bad request",
        r"model.*not.*found|model.*not.*exist",
    ]
    
    TRANSIENT_PATTERNS = [
        r"timeout|timed out|deadline exceeded",
        r"connection.*reset|connection.*refused",
        r"connection.*timeout|socket.*timeout",
        r"temporarily unavailable",
        r"service unavailable|503",
        r"bad gateway|502",
        r"gateway timeout|504",
    ]
    
    RATE_LIMIT_PATTERNS = [
        r"429|too many requests",
        r"rate limit|rate_limit",
        r"quota.*exceeded|quota.*exhausted",
        r"daily.*limit|daily_limit",
        r"request.*limit|rpm|tpm",
        r"insufficient quota|insufficient_quota",
        r"payment.*required|402|billing",
    ]
    
    AUTHENTICATION_PATTERNS = [
        r"invalid.*api.*key|invalid api key",
        r"api key.*invalid|api_key_invalid",
        r"api key.*not.*set|api key is required",
        r"authentication.*failed|auth.*failed",
        r"invalid.*token|token.*invalid",
    ]
    
    @classmethod
    def classify(cls, error: Exception) -> ErrorClass:
        """
        Classify an error based on its message and type.
        """
        if error is None:
            return ErrorClass.UNKNOWN
        
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Check authentication first (most specific)
        if any(re.search(p, error_str) for p in cls.AUTHENTICATION_PATTERNS):
            return ErrorClass.AUTHENTICATION
        
        # Check rate limit
        if any(re.search(p, error_str) for p in cls.RATE_LIMIT_PATTERNS):
            return ErrorClass.RATE_LIMIT
        
        # Check transient
        if any(re.search(p, error_str) for p in cls.TRANSIENT_PATTERNS):
            return ErrorClass.TRANSIENT
        
        # Check permanent
        if any(re.search(p, error_str) for p in cls.PERMANENT_PATTERNS):
            return ErrorClass.PERMANENT
        
        # Default: if it looks like a connection/network error, treat as transient
        if any(x in error_type for x in ["connection", "socket", "timeout", "http"]):
            return ErrorClass.TRANSIENT
        
        return ErrorClass.UNKNOWN


class BackoffStrategy:
    """Exponential backoff with jitter and max retries."""
    
    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 32.0,
        multiplier: float = 2.0,
        jitter: bool = True,
        max_retries: int = 5,
    ):
        """
        Args:
            initial_delay: First backoff in seconds
            max_delay: Maximum backoff in seconds
            multiplier: Exponential factor (1s → 2s → 4s → ...)
            jitter: Add randomness to avoid thundering herd
            max_retries: Max number of retry attempts
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.max_retries = max_retries
    
    def get_delay(self, attempt: int) -> float:
        """
        Calculate backoff delay for given attempt number (0-indexed).
        
        Args:
            attempt: Attempt number (0 = first retry)
            
        Returns:
            Delay in seconds before next attempt
        """
        if attempt >= self.max_retries:
            return None  # Stop retrying
        
        # Exponential: 1 → 2 → 4 → 8 → 16 → 32
        delay = self.initial_delay * (self.multiplier ** attempt)
        delay = min(delay, self.max_delay)
        
        # Add jitter: ±10% randomness
        if self.jitter:
            import random
            delay *= (0.9 + random.random() * 0.2)
        
        return delay
    
    def should_retry(self, attempt: int) -> bool:
        """Should we retry for this attempt number?"""
        return attempt < self.max_retries
    
    def wait(self, attempt: int) -> None:
        """Wait for backoff duration, then continue."""
        delay = self.get_delay(attempt)
        if delay:
            time.sleep(delay)


class RetryPolicy:
    """
    Decides retry behavior based on error classification.
    
    Usage:
    
        policy = RetryPolicy()
        error_class = ErrorClassifier.classify(exception)
        
        action = policy.decide(error_class)
        # action = "RETRY", "FALLBACK", "FAIL", or "ASK_USER"
    """
    
    def __init__(self, backoff_strategy: Optional[BackoffStrategy] = None):
        self.backoff = backoff_strategy or BackoffStrategy()
    
    def decide(self, error_class: ErrorClass, attempt: int = 0) -> str:
        """
        Decide what to do based on error class and attempt number.
        
        Returns:
            "RETRY" - retry with backoff
            "FALLBACK" - switch provider and retry
            "FAIL" - give up, return error to user
            "ASK_USER" - ask user for intervention (e.g., API key)
        """
        if error_class == ErrorClass.TRANSIENT:
            if self.backoff.should_retry(attempt):
                return "RETRY"
            else:
                return "FAIL"
        
        elif error_class == ErrorClass.RATE_LIMIT:
            if self.backoff.should_retry(attempt):
                return "FALLBACK"  # Try next provider
            else:
                return "FAIL"
        
        elif error_class == ErrorClass.AUTHENTICATION:
            return "ASK_USER"
        
        elif error_class == ErrorClass.PERMANENT:
            return "FAIL"
        
        else:  # UNKNOWN
            if self.backoff.should_retry(attempt):
                return "RETRY"  # Be optimistic
            else:
                return "FAIL"
    
    def execute_with_backoff(
        self,
        fn: Callable,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
    ):
        """
        Execute a function with automatic retry on transient errors.
        
        Args:
            fn: Function to execute (should raise on error)
            on_retry: Optional callback called on each retry: on_retry(attempt, error)
            
        Returns:
            fn() result
            
        Raises:
            Original exception if max retries exceeded or permanent error
        """
        attempt = 0
        
        while True:
            try:
                return fn()
            except Exception as e:
                error_class = ErrorClassifier.classify(e)
                action = self.decide(error_class, attempt)
                
                if action == "FAIL":
                    raise
                elif action == "ASK_USER":
                    raise  # Let caller handle
                elif action == "RETRY":
                    if on_retry:
                        on_retry(attempt, e)
                    self.backoff.wait(attempt)
                    attempt += 1
                elif action == "FALLBACK":
                    raise  # Let caller handle provider fallback
