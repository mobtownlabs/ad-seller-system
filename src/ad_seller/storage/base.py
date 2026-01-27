# Author: AgentRange Inc.
# Donated to IAB Tech Lab

"""Base storage backend interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to storage backend."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to storage backend."""
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with optional TTL (seconds)."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if key existed."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def keys(self, pattern: str = "*") -> list[str]:
        """List keys matching pattern."""
        pass

    # Higher-level operations for common use cases

    async def get_product(self, product_id: str) -> Optional[dict]:
        """Get a product by ID."""
        return await self.get(f"product:{product_id}")

    async def set_product(self, product_id: str, product_data: dict) -> None:
        """Store a product."""
        await self.set(f"product:{product_id}", product_data)

    async def get_proposal(self, proposal_id: str) -> Optional[dict]:
        """Get a proposal by ID."""
        return await self.get(f"proposal:{proposal_id}")

    async def set_proposal(self, proposal_id: str, proposal_data: dict) -> None:
        """Store a proposal."""
        await self.set(f"proposal:{proposal_id}", proposal_data)

    async def get_deal(self, deal_id: str) -> Optional[dict]:
        """Get a deal by ID."""
        return await self.get(f"deal:{deal_id}")

    async def set_deal(self, deal_id: str, deal_data: dict) -> None:
        """Store a deal."""
        await self.set(f"deal:{deal_id}", deal_data)

    async def list_products(self) -> list[dict]:
        """List all products."""
        keys = await self.keys("product:*")
        products = []
        for key in keys:
            product = await self.get(key)
            if product:
                products.append(product)
        return products

    async def list_proposals(self) -> list[dict]:
        """List all proposals."""
        keys = await self.keys("proposal:*")
        proposals = []
        for key in keys:
            proposal = await self.get(key)
            if proposal:
                proposals.append(proposal)
        return proposals

    async def list_deals(self) -> list[dict]:
        """List all deals."""
        keys = await self.keys("deal:*")
        deals = []
        for key in keys:
            deal = await self.get(key)
            if deal:
                deals.append(deal)
        return deals
