# Author: AgentRange Inc.
# Donated to IAB Tech Lab

"""Product Setup Flow - Define and configure sellable inventory products.

This flow handles:
- Syncing inventory from ad server (GAM/FreeWheel)
- Defining products backed by inventory segments
- Attaching IAB taxonomies (Audience, Content, Ad Product)
- Setting commercial terms (deal types, pricing models)
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from crewai.flow.flow import Flow, start, listen

from ..models.flow_state import (
    ExecutionStatus,
    ProductDefinition,
    SellerFlowState,
)
from ..models.core import DealType, PricingModel
from ..clients import UnifiedClient, Protocol
from ..config import get_settings


class ProductSetupState(SellerFlowState):
    """State for product setup flow."""

    # Ad server sync state
    ad_server_config_id: Optional[str] = None
    synced_segments: list[str] = []

    # Product creation state
    products_to_create: list[dict[str, Any]] = []
    created_products: list[str] = []


class ProductSetupFlow(Flow[ProductSetupState]):
    """Flow for setting up products in the seller catalog.

    Steps:
    1. Initialize seller organization
    2. Sync inventory from ad server (optional)
    3. Create inventory segments
    4. Define products with taxonomy targeting
    5. Set commercial terms
    """

    def __init__(self) -> None:
        """Initialize the product setup flow."""
        super().__init__()
        self._settings = get_settings()

    @start()
    async def initialize_setup(self) -> None:
        """Initialize the product setup flow."""
        self.state.flow_id = str(uuid.uuid4())
        self.state.flow_type = "product_setup"
        self.state.started_at = datetime.utcnow()
        self.state.status = ExecutionStatus.PRODUCT_SETUP

        # Set seller identity from settings
        self.state.seller_organization_id = (
            self._settings.seller_organization_id or f"seller-{uuid.uuid4().hex[:8]}"
        )
        self.state.seller_name = self._settings.seller_organization_name

    @listen(initialize_setup)
    async def ensure_seller_organization(self) -> None:
        """Ensure seller organization exists in OpenDirect."""
        async with UnifiedClient(protocol=Protocol.OPENDIRECT_21) as client:
            # Check if organization exists
            result = await client.list_organizations(role="seller")

            if result.success:
                orgs = result.data or []
                existing = next(
                    (o for o in orgs if o.get("organizationid") == self.state.seller_organization_id),
                    None,
                )

                if not existing:
                    # Create seller organization
                    create_result = await client.create_organization(
                        name=self.state.seller_name,
                        role="seller",
                        organization_id=self.state.seller_organization_id,
                    )

                    if not create_result.success:
                        self.state.errors.append(f"Failed to create organization: {create_result.error}")

    @listen(ensure_seller_organization)
    async def sync_from_ad_server(self) -> None:
        """Sync inventory from ad server if configured.

        This step is optional and only runs if ad server is configured.
        """
        # Check if ad server sync is configured
        if not self._settings.gam_network_code and not self._settings.freewheel_api_url:
            self.state.warnings.append("No ad server configured, skipping inventory sync")
            return

        # TODO: Implement GAM inventory sync when GAM client is available
        pass

    @listen(sync_from_ad_server)
    async def create_default_products(self) -> None:
        """Create default products for common inventory types."""
        async with UnifiedClient() as client:
            # Define default products
            default_products = [
                {
                    "name": "Premium Display - Homepage",
                    "description": "High-impact display on homepage",
                    "inventory_type": "display",
                    "base_cpm": 15.0,
                    "floor_cpm": 10.0,
                    "supported_deal_types": [DealType.PROGRAMMATIC_GUARANTEED, DealType.PREFERRED_DEAL],
                    "supported_pricing_models": [PricingModel.CPM],
                },
                {
                    "name": "Standard Display - ROS",
                    "description": "Run of site display inventory",
                    "inventory_type": "display",
                    "base_cpm": 8.0,
                    "floor_cpm": 5.0,
                    "supported_deal_types": [DealType.PREFERRED_DEAL, DealType.PRIVATE_AUCTION],
                    "supported_pricing_models": [PricingModel.CPM],
                },
                {
                    "name": "Pre-Roll Video",
                    "description": "In-stream pre-roll video ads",
                    "inventory_type": "video",
                    "base_cpm": 25.0,
                    "floor_cpm": 18.0,
                    "supported_deal_types": [DealType.PROGRAMMATIC_GUARANTEED, DealType.PREFERRED_DEAL],
                    "supported_pricing_models": [PricingModel.CPM, PricingModel.CPCV],
                },
                {
                    "name": "CTV Premium Streaming",
                    "description": "Connected TV inventory on premium streaming apps",
                    "inventory_type": "ctv",
                    "base_cpm": 35.0,
                    "floor_cpm": 28.0,
                    "supported_deal_types": [DealType.PROGRAMMATIC_GUARANTEED],
                    "supported_pricing_models": [PricingModel.CPM],
                },
                {
                    "name": "Mobile App Rewarded Video",
                    "description": "User-initiated rewarded video in mobile apps",
                    "inventory_type": "mobile_app",
                    "base_cpm": 20.0,
                    "floor_cpm": 15.0,
                    "supported_deal_types": [DealType.PREFERRED_DEAL, DealType.PRIVATE_AUCTION],
                    "supported_pricing_models": [PricingModel.CPM, PricingModel.CPCV],
                },
                {
                    "name": "Native In-Feed",
                    "description": "Native ads in content feeds",
                    "inventory_type": "native",
                    "base_cpm": 12.0,
                    "floor_cpm": 8.0,
                    "supported_deal_types": [DealType.PREFERRED_DEAL],
                    "supported_pricing_models": [PricingModel.CPM, PricingModel.CPC],
                },
            ]

            for product_config in default_products:
                product_def = ProductDefinition(
                    product_id=f"prod-{uuid.uuid4().hex[:8]}",
                    name=product_config["name"],
                    description=product_config.get("description"),
                    inventory_type=product_config["inventory_type"],
                    supported_deal_types=product_config["supported_deal_types"],
                    supported_pricing_models=product_config["supported_pricing_models"],
                    base_cpm=product_config["base_cpm"],
                    floor_cpm=product_config["floor_cpm"],
                )

                self.state.products[product_def.product_id] = product_def
                self.state.created_products.append(product_def.product_id)

    @listen(create_default_products)
    async def finalize_setup(self) -> None:
        """Finalize the product setup flow."""
        self.state.status = ExecutionStatus.COMPLETED
        self.state.completed_at = datetime.utcnow()

    def get_products(self) -> dict[str, ProductDefinition]:
        """Get all configured products."""
        return self.state.products

    def add_product(self, product: ProductDefinition) -> None:
        """Add a product to the catalog."""
        self.state.products[product.product_id] = product
