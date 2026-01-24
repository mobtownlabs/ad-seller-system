"""Protocol clients for OpenDirect and A2A communication."""

from .unified_client import Protocol, UnifiedClient, UnifiedResult
from .opendirect21_client import OpenDirect21Client
from .opendirect30_client import OpenDirect30Client
from .a2a_client import A2AClient, A2AResponse
from .ucp_client import UCPClient, UCPExchangeResult

__all__ = [
    "Protocol",
    "UnifiedClient",
    "UnifiedResult",
    "OpenDirect21Client",
    "OpenDirect30Client",
    "A2AClient",
    "A2AResponse",
    # UCP client for audience validation
    "UCPClient",
    "UCPExchangeResult",
]
