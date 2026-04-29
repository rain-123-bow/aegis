"""Aegis Router package."""

from .core import Router
from .mailbucket import cleanup_expired_mailbucket_messages, create_mailbucket_message
from .models import AgentRecord, DomainRecord, MessageRecord
from .path_resolution import (
    make_dev_protected_path_token,
    make_rsa_oaep_sha256_path_token,
    resolve_route_envelope_path,
)

__all__ = [
    "Router",
    "AgentRecord",
    "DomainRecord",
    "MessageRecord",
    "cleanup_expired_mailbucket_messages",
    "create_mailbucket_message",
    "make_dev_protected_path_token",
    "make_rsa_oaep_sha256_path_token",
    "resolve_route_envelope_path",
]
