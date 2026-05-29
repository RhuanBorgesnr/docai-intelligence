"""
Notification channel backends.

Each module exposes a ``deliver(notification) -> tuple[bool, dict]`` function
that performs the actual delivery and returns (success, provider_response).
"""
