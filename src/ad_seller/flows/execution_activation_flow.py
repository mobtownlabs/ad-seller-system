# Author: AgentRange Inc.
# Donated to IAB Tech Lab

"""Execution Activation Flow - Sync deals to ad servers.

This flow handles:
- Creating execution orders from accepted proposals
- Syncing to ad server (GAM/FreeWheel)
- Two paths: IO/Order (budget committed) or Deal ID (access + pricing only)
- Managing creative assignments
- Tracking entity mappings
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from crewai.flow.flow import Flow, start, listen

from ..models.flow_state import (
    ExecutionStatus,
    SellerFlowState,
)
from ..models.core import DealType, ExecutionOrderStatus
from ..clients import UnifiedClient, Protocol
from ..config import get_settings


class ExecutionState(SellerFlowState):
    """State for execution activation flow."""

    # Input
    proposal_id: str = ""
    deal_id: str = ""
    execution_type: str = "deal_id"  # deal_id or io_order

    # Ad server config
    ad_server_config_id: Optional[str] = None

    # Execution tracking
    execution_order_id: str = ""
    ad_server_entity_id: str = ""
    sync_status: str = "pending"


class ExecutionActivationFlow(Flow[ExecutionState]):
    """Flow for activating deals in ad servers.

    Two Output Types:

    1. IO / Booked Order (Budget Committed)
       - GAM: Order + Line Items with budget, impressions, dates
       - FreeWheel: Insertion Order with committed spend
       - Budget lives in ad server, seller responsible for delivery

    2. Deal ID Only (Access + Pricing)
       - GAM: Programmatic Deal with price floor or fixed price
       - FreeWheel: Deal ID for programmatic activation
       - NO budget in deal - just "access pass" + pricing
       - Budget lives in DSP, buyer controls spend
    """

    def __init__(self) -> None:
        """Initialize the execution activation flow."""
        super().__init__()
        self._settings = get_settings()

    @start()
    async def initialize_execution(self) -> None:
        """Initialize the execution flow."""
        self.state.flow_id = str(uuid.uuid4())
        self.state.flow_type = "execution_activation"
        self.state.started_at = datetime.utcnow()
        self.state.status = ExecutionStatus.SYNCING_TO_AD_SERVER

        # Validate we have something to execute
        if not self.state.proposal_id and not self.state.deal_id:
            self.state.errors.append("Either proposal_id or deal_id required")
            self.state.status = ExecutionStatus.FAILED

    @listen(initialize_execution)
    async def create_execution_order(self) -> None:
        """Create execution order in OpenDirect."""
        if self.state.status == ExecutionStatus.FAILED:
            return

        # Generate execution order ID
        self.state.execution_order_id = f"exec-{uuid.uuid4().hex[:8]}"

        try:
            async with UnifiedClient() as client:
                result = await client.create_execution_order(
                    proposal_id=self.state.proposal_id or self.state.deal_id,
                    execution_order_id=self.state.execution_order_id,
                    status="draft",
                    external_ids={
                        "execution_type": self.state.execution_type,
                        "deal_id": self.state.deal_id,
                    },
                )

                if not result.success:
                    self.state.warnings.append(
                        f"Could not create execution order: {result.error}"
                    )
        except Exception as e:
            self.state.warnings.append(f"Execution order creation failed: {e}")

    @listen(create_execution_order)
    async def determine_sync_path(self) -> None:
        """Determine which sync path to use based on deal type."""
        if self.state.status == ExecutionStatus.FAILED:
            return

        # Get deal info
        deal = self.state.deals.get(self.state.deal_id)

        if deal:
            # Deal ID path for PG/PD/PA
            if deal.deal_type in [
                DealType.PROGRAMMATIC_GUARANTEED,
                DealType.PREFERRED_DEAL,
                DealType.PRIVATE_AUCTION,
            ]:
                self.state.execution_type = "deal_id"
            else:
                self.state.execution_type = "io_order"
        else:
            # Default to deal_id path
            self.state.execution_type = "deal_id"

    @listen(determine_sync_path)
    async def sync_deal_id_to_ad_server(self) -> None:
        """Sync Deal ID to ad server (GAM/FreeWheel).

        Creates a programmatic deal with price floor or fixed price.
        NO budget commitment - just access + pricing terms.
        """
        if self.state.status == ExecutionStatus.FAILED:
            return

        if self.state.execution_type != "deal_id":
            return

        deal = self.state.deals.get(self.state.deal_id)
        if not deal:
            self.state.warnings.append("No deal found for sync")
            return

        # Determine ad server type
        ad_server_type = self._settings.ad_server_type

        if ad_server_type == "google_ad_manager":
            await self._sync_to_gam_deal(deal)
        elif ad_server_type == "freewheel":
            await self._sync_to_freewheel_deal(deal)
        else:
            self.state.warnings.append(f"Unknown ad server type: {ad_server_type}")

    async def _sync_to_gam_deal(self, deal: Any) -> None:
        """Sync deal to Google Ad Manager as Programmatic Deal."""
        # In production, this would use GAM API
        # For now, simulate the sync
        self.state.ad_server_entity_id = f"gam-deal-{deal.deal_id}"
        self.state.sync_status = "synced"

        # Store entity mapping
        self.state.execution_orders[deal.deal_id] = {
            "execution_order_id": self.state.execution_order_id,
            "ad_server_type": "google_ad_manager",
            "ad_server_entity_id": self.state.ad_server_entity_id,
            "entity_type": "programmatic_deal",
            "price": deal.price,
            "pricing_type": "fixed" if deal.deal_type == DealType.PROGRAMMATIC_GUARANTEED else "floor",
        }

    async def _sync_to_freewheel_deal(self, deal: Any) -> None:
        """Sync deal to FreeWheel as Deal ID."""
        # In production, this would use FreeWheel API
        self.state.ad_server_entity_id = f"fw-deal-{deal.deal_id}"
        self.state.sync_status = "synced"

        self.state.execution_orders[deal.deal_id] = {
            "execution_order_id": self.state.execution_order_id,
            "ad_server_type": "freewheel",
            "ad_server_entity_id": self.state.ad_server_entity_id,
            "entity_type": "deal",
            "price": deal.price,
        }

    @listen(determine_sync_path)
    async def sync_io_order_to_ad_server(self) -> None:
        """Sync IO/Order to ad server (GAM/FreeWheel).

        Creates Order + Line Items with budget commitment.
        Budget lives in ad server, seller responsible for delivery.
        """
        if self.state.status == ExecutionStatus.FAILED:
            return

        if self.state.execution_type != "io_order":
            return

        # Get proposal data for IO creation
        proposal_data = self.state.counter_proposals.get(self.state.proposal_id, {})

        ad_server_type = self._settings.ad_server_type

        if ad_server_type == "google_ad_manager":
            await self._sync_to_gam_order(proposal_data)
        elif ad_server_type == "freewheel":
            await self._sync_to_freewheel_io(proposal_data)
        else:
            self.state.warnings.append(f"Unknown ad server type: {ad_server_type}")

    async def _sync_to_gam_order(self, proposal_data: dict) -> None:
        """Sync to Google Ad Manager as Order + Line Items."""
        # In production, this would use GAM API
        order_id = f"gam-order-{self.state.execution_order_id}"
        line_id = f"gam-line-{uuid.uuid4().hex[:8]}"

        self.state.ad_server_entity_id = order_id
        self.state.sync_status = "synced"

        self.state.execution_orders[self.state.proposal_id] = {
            "execution_order_id": self.state.execution_order_id,
            "ad_server_type": "google_ad_manager",
            "ad_server_order_id": order_id,
            "ad_server_line_ids": [line_id],
            "entity_type": "order",
            "budget_committed": True,
        }

    async def _sync_to_freewheel_io(self, proposal_data: dict) -> None:
        """Sync to FreeWheel as Insertion Order."""
        io_id = f"fw-io-{self.state.execution_order_id}"

        self.state.ad_server_entity_id = io_id
        self.state.sync_status = "synced"

        self.state.execution_orders[self.state.proposal_id] = {
            "execution_order_id": self.state.execution_order_id,
            "ad_server_type": "freewheel",
            "ad_server_io_id": io_id,
            "entity_type": "insertion_order",
            "budget_committed": True,
        }

    @listen(sync_deal_id_to_ad_server, sync_io_order_to_ad_server)
    async def update_execution_status(self) -> None:
        """Update execution order status after sync."""
        if self.state.status == ExecutionStatus.FAILED:
            return

        try:
            async with UnifiedClient() as client:
                # Update execution order status to booked
                await client.update_proposal(
                    proposal_id=self.state.execution_order_id,
                    status=ExecutionOrderStatus.BOOKED.value,
                )
        except Exception as e:
            self.state.warnings.append(f"Status update failed: {e}")

    @listen(update_execution_status)
    async def finalize(self) -> None:
        """Finalize the execution flow."""
        self.state.status = ExecutionStatus.COMPLETED
        self.state.completed_at = datetime.utcnow()

    def activate(
        self,
        deal_id: Optional[str] = None,
        proposal_id: Optional[str] = None,
        execution_type: str = "deal_id",
        deals: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Activate a deal or proposal in the ad server.

        Args:
            deal_id: Deal ID to activate
            proposal_id: Proposal ID to activate
            execution_type: Type of execution (deal_id or io_order)
            deals: Deal dictionary

        Returns:
            Activation result with ad server entity IDs
        """
        self.state.deal_id = deal_id or ""
        self.state.proposal_id = proposal_id or deal_id or ""
        self.state.execution_type = execution_type
        if deals:
            self.state.deals = deals

        # Run the flow
        self.kickoff()

        return {
            "execution_order_id": self.state.execution_order_id,
            "ad_server_entity_id": self.state.ad_server_entity_id,
            "execution_type": self.state.execution_type,
            "sync_status": self.state.sync_status,
            "execution_orders": self.state.execution_orders,
            "status": self.state.status.value,
            "errors": self.state.errors,
            "warnings": self.state.warnings,
        }
