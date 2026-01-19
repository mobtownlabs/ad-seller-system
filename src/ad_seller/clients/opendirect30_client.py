"""OpenDirect 3.0 client for opendirect3-mcp server.

Connects to the OpenDirect 3.0 MCP server which implements the full
OpenDirect 3.0 specification including proposal revisions, taxonomies,
and ad server integration.
"""

from typing import Any, Optional

from ..config import get_settings


class OpenDirect30Client:
    """Client for OpenDirect 3.0 via opendirect3-mcp server.

    This client connects to the opendirect3-mcp server using the MCP
    protocol over streamable HTTP.

    Key 3.0 features:
    - Proposal revisions with RFC 6902 JSON Patch
    - IAB Taxonomy targeting (Audience, Content, Ad Product)
    - Inventory segments backing products
    - Ad server synchronization (GAM, FreeWheel)

    Usage:
        async with OpenDirect30Client() as client:
            products = await client.list_products()
            # Accept a proposal
            await client.update_proposal(
                proposal_id="...",
                status="accepted",
                revision_type="SELLER_COUNTER"
            )
    """

    def __init__(self, base_url: Optional[str] = None):
        """Initialize the OpenDirect 3.0 client.

        Args:
            base_url: Base URL for the opendirect3-mcp server
        """
        settings = get_settings()
        self.base_url = base_url or settings.opendirect_base_url
        self.mcp_url = f"{self.base_url}/mcp"

        self._session: Optional[Any] = None
        self._tools: dict[str, Any] = {}

    async def __aenter__(self) -> "OpenDirect30Client":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to the MCP server and cache available tools."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            transport = await streamablehttp_client(self.mcp_url).__aenter__()
            read_stream, write_stream, _ = transport
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            # Cache available tools
            tools_result = await self._session.list_tools()
            self._tools = {tool.name: tool for tool in tools_result.tools}
        except Exception as e:
            raise RuntimeError(f"Failed to connect to OpenDirect 3.0 MCP server: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool."""
        if not self._session:
            raise RuntimeError("Client not connected")

        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")

        result = await self._session.call_tool(name, arguments)
        if result.content:
            import json

            try:
                return json.loads(result.content[0].text)
            except (json.JSONDecodeError, AttributeError):
                return result.content[0].text
        return None

    # =========================================================================
    # Organization Operations
    # =========================================================================

    async def list_organizations(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List organizations."""
        args = {}
        if role:
            args["role"] = role
        if status:
            args["status"] = status
        return await self._call_tool("list_organizations", args)

    async def get_organization(self, organization_id: str) -> dict[str, Any]:
        """Get an organization by ID."""
        return await self._call_tool(
            "get_organization", {"organizationid": organization_id}
        )

    async def create_organization(
        self,
        name: str,
        role: str,
        organization_id: Optional[str] = None,
        status: str = "active",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create an organization."""
        args = {"name": name, "role": role, "status": status}
        if organization_id:
            args["organizationid"] = organization_id
        if metadata:
            args["metadata"] = metadata
        return await self._call_tool("create_organization", args)

    async def update_organization(
        self,
        organization_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update an organization."""
        args = {"organizationid": organization_id}
        if name:
            args["name"] = name
        if status:
            args["status"] = status
        if metadata:
            args["metadata"] = metadata
        return await self._call_tool("update_organization", args)

    # =========================================================================
    # Account Operations
    # =========================================================================

    async def list_accounts(
        self,
        buyer_organization_id: Optional[str] = None,
        seller_organization_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List accounts."""
        args = {}
        if buyer_organization_id:
            args["buyerorganizationid"] = buyer_organization_id
        if seller_organization_id:
            args["sellerorganizationid"] = seller_organization_id
        if status:
            args["status"] = status
        return await self._call_tool("list_accounts", args)

    async def create_account(
        self,
        buyer_organization_id: str,
        seller_organization_id: str,
        account_id: Optional[str] = None,
        status: str = "active",
    ) -> dict[str, Any]:
        """Create an account."""
        args = {
            "buyerorganizationid": buyer_organization_id,
            "sellerorganizationid": seller_organization_id,
            "status": status,
        }
        if account_id:
            args["accountid"] = account_id
        return await self._call_tool("create_account", args)

    # =========================================================================
    # Inventory Segment Operations
    # =========================================================================

    async def list_inventory_segments(self) -> list[dict[str, Any]]:
        """List inventory segments."""
        return await self._call_tool("list_inventory_segments", {})

    async def get_inventory_segment(self, inventory_segment_id: str) -> dict[str, Any]:
        """Get an inventory segment by ID."""
        return await self._call_tool(
            "get_inventory_segment", {"inventorysegmentid": inventory_segment_id}
        )

    async def create_inventory_segment(
        self,
        inventory_references: dict[str, Any],
        inventory_segment_id: Optional[str] = None,
        segment_targeting: Optional[dict[str, Any]] = None,
        segment_content: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create an inventory segment."""
        args = {"inventoryreferences": inventory_references}
        if inventory_segment_id:
            args["inventorysegmentid"] = inventory_segment_id
        if segment_targeting:
            args["segmenttargeting"] = segment_targeting
        if segment_content:
            args["segmentcontent"] = segment_content
        return await self._call_tool("create_inventory_segment", args)

    # =========================================================================
    # Product Operations
    # =========================================================================

    async def list_products(
        self,
        seller_organization_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List products."""
        args = {}
        if seller_organization_id:
            args["sellerorganizationid"] = seller_organization_id
        return await self._call_tool("list_products", args)

    async def get_product(self, product_id: str) -> dict[str, Any]:
        """Get a product by ID."""
        return await self._call_tool("get_product", {"productid": product_id})

    async def create_product(
        self,
        name: str,
        seller_organization_id: str,
        inventory_segments: list[str],
        product_id: Optional[str] = None,
        description: Optional[str] = None,
        audience_targeting: Optional[dict[str, Any]] = None,
        ad_product_targeting: Optional[dict[str, Any]] = None,
        content_targeting: Optional[dict[str, Any]] = None,
        commercial_terms: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a product with taxonomy targeting."""
        args = {
            "name": name,
            "sellerorganizationid": seller_organization_id,
            "inventorysegments": inventory_segments,
        }
        if product_id:
            args["productid"] = product_id
        if description:
            args["description"] = description
        if audience_targeting:
            args["audiencetargeting"] = audience_targeting
        if ad_product_targeting:
            args["adproducttargeting"] = ad_product_targeting
        if content_targeting:
            args["contenttargeting"] = content_targeting
        if commercial_terms:
            args["commercialterms"] = commercial_terms
        return await self._call_tool("create_product", args)

    async def update_product(
        self,
        product_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        audience_targeting: Optional[dict[str, Any]] = None,
        ad_product_targeting: Optional[dict[str, Any]] = None,
        content_targeting: Optional[dict[str, Any]] = None,
        commercial_terms: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update a product."""
        args = {"productid": product_id}
        if name:
            args["name"] = name
        if description:
            args["description"] = description
        if audience_targeting:
            args["audiencetargeting"] = audience_targeting
        if ad_product_targeting:
            args["adproducttargeting"] = ad_product_targeting
        if content_targeting:
            args["contenttargeting"] = content_targeting
        if commercial_terms:
            args["commercialterms"] = commercial_terms
        return await self._call_tool("update_product", args)

    # =========================================================================
    # Proposal Operations
    # =========================================================================

    async def list_proposals(
        self,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List proposals."""
        args = {}
        if account_id:
            args["accountid"] = account_id
        if status:
            args["status"] = status
        return await self._call_tool("list_proposals", args)

    async def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Get a proposal by ID."""
        return await self._call_tool("get_proposal", {"proposalid": proposal_id})

    async def create_proposal(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        proposal_id: Optional[str] = None,
        status: str = "draft",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a proposal."""
        args = {
            "accountid": account_id,
            "startdate": start_date,
            "enddate": end_date,
            "status": status,
        }
        if proposal_id:
            args["proposalid"] = proposal_id
        if metadata:
            args["metadata"] = metadata
        return await self._call_tool("create_proposal", args)

    async def update_proposal(
        self,
        proposal_id: str,
        status: Optional[str] = None,
        revision_type: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a proposal (accept, reject, counter).

        For seller counters, only pricing, delivery goals, and narrow
        targeting (exclusions) can be modified.
        """
        args = {"proposalid": proposal_id}
        if status:
            args["status"] = status
        if revision_type:
            args["revisionType"] = revision_type
        if reason:
            args["reason"] = reason
        args.update(kwargs)
        return await self._call_tool("update_proposal", args)

    async def list_proposal_revisions(
        self,
        proposal_thread_id: str,
    ) -> list[dict[str, Any]]:
        """List all revisions for a proposal thread."""
        return await self._call_tool(
            "list_proposal_revisions", {"proposalthreadid": proposal_thread_id}
        )

    # =========================================================================
    # Proposal Line Operations
    # =========================================================================

    async def list_proposal_lines(
        self,
        proposal_id: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List proposal lines."""
        args = {}
        if proposal_id:
            args["proposalid"] = proposal_id
        if product_id:
            args["productid"] = product_id
        return await self._call_tool("list_proposal_lines", args)

    async def get_proposal_line(self, proposal_line_id: str) -> dict[str, Any]:
        """Get a proposal line by ID."""
        return await self._call_tool(
            "get_proposal_line", {"proposallineid": proposal_line_id}
        )

    async def create_proposal_line(
        self,
        proposal_id: str,
        product_id: str,
        deal_type: str,
        delivery_goal: dict[str, Any],
        pricing: dict[str, Any],
        proposal_line_id: Optional[str] = None,
        audience_targeting: Optional[dict[str, Any]] = None,
        ad_product_targeting: Optional[dict[str, Any]] = None,
        content_targeting: Optional[dict[str, Any]] = None,
        external_ids: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a proposal line."""
        args = {
            "proposalid": proposal_id,
            "productid": product_id,
            "dealtype": deal_type,
            "deliverygoal": delivery_goal,
            "pricing": pricing,
        }
        if proposal_line_id:
            args["proposallineid"] = proposal_line_id
        if audience_targeting:
            args["audiencetargeting"] = audience_targeting
        if ad_product_targeting:
            args["adproducttargeting"] = ad_product_targeting
        if content_targeting:
            args["contenttargeting"] = content_targeting
        if external_ids:
            args["externalids"] = external_ids
        return await self._call_tool("create_proposal_line", args)

    async def update_proposal_line(
        self,
        proposal_line_id: str,
        delivery_goal: Optional[dict[str, Any]] = None,
        pricing: Optional[dict[str, Any]] = None,
        audience_targeting: Optional[dict[str, Any]] = None,
        content_targeting: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update a proposal line (seller can only modify certain fields)."""
        args = {"proposallineid": proposal_line_id}
        if delivery_goal:
            args["deliverygoal"] = delivery_goal
        if pricing:
            args["pricing"] = pricing
        if audience_targeting:
            args["audiencetargeting"] = audience_targeting
        if content_targeting:
            args["contenttargeting"] = content_targeting
        return await self._call_tool("update_proposal_line", args)

    # =========================================================================
    # Execution Order Operations
    # =========================================================================

    async def list_execution_orders(
        self,
        proposal_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List execution orders."""
        args = {}
        if proposal_id:
            args["proposalid"] = proposal_id
        if status:
            args["status"] = status
        return await self._call_tool("list_execution_orders", args)

    async def get_execution_order(self, execution_order_id: str) -> dict[str, Any]:
        """Get an execution order by ID."""
        return await self._call_tool(
            "get_execution_order", {"executionorderid": execution_order_id}
        )

    async def create_execution_order(
        self,
        proposal_id: str,
        execution_order_id: Optional[str] = None,
        status: str = "draft",
        external_ids: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create an execution order from an accepted proposal."""
        args = {
            "proposalid": proposal_id,
            "status": status,
            "externalids": external_ids or {},
        }
        if execution_order_id:
            args["executionorderid"] = execution_order_id
        if metadata:
            args["metadata"] = metadata
        return await self._call_tool("create_execution_order", args)

    async def update_execution_order(
        self,
        execution_order_id: str,
        status: Optional[str] = None,
        external_ids: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update an execution order."""
        args = {"executionorderid": execution_order_id}
        if status:
            args["status"] = status
        if external_ids:
            args["externalids"] = external_ids
        return await self._call_tool("update_execution_order", args)

    # =========================================================================
    # Placement Operations
    # =========================================================================

    async def list_placements(
        self,
        execution_order_id: Optional[str] = None,
        inventory_segment_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List placements."""
        args = {}
        if execution_order_id:
            args["executionorderid"] = execution_order_id
        if inventory_segment_id:
            args["inventorysegmentid"] = inventory_segment_id
        if status:
            args["status"] = status
        return await self._call_tool("list_placements", args)

    async def create_placement(
        self,
        execution_order_id: str,
        inventory_segment_id: str,
        placement_id: Optional[str] = None,
        status: str = "created",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a placement."""
        args = {
            "executionorderid": execution_order_id,
            "inventorysegmentid": inventory_segment_id,
            "status": status,
        }
        if placement_id:
            args["placementid"] = placement_id
        if metadata:
            args["metadata"] = metadata
        return await self._call_tool("create_placement", args)

    # =========================================================================
    # Creative Operations
    # =========================================================================

    async def list_creatives(
        self,
        review_status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List creatives."""
        args = {}
        if review_status:
            args["reviewstatus"] = review_status
        return await self._call_tool("list_creatives", args)

    async def create_creative(
        self,
        ad_profile: str,
        creative_manifest: dict[str, Any],
        creative_id: Optional[str] = None,
        review_status: str = "pending",
        is_placeholder: bool = False,
        ad_product_taxonomy: Optional[dict[str, Any]] = None,
        audience_taxonomy: Optional[dict[str, Any]] = None,
        content_policy: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a creative (metadata only)."""
        args = {
            "adprofile": ad_profile,
            "creativemanifest": creative_manifest,
            "reviewstatus": review_status,
            "isplaceholder": is_placeholder,
        }
        if creative_id:
            args["creativeid"] = creative_id
        if ad_product_taxonomy:
            args["adproducttaxonomy"] = ad_product_taxonomy
        if audience_taxonomy:
            args["audiencetaxonomy"] = audience_taxonomy
        if content_policy:
            args["contentpolicy"] = content_policy
        return await self._call_tool("create_creative", args)

    async def update_creative(
        self,
        creative_id: str,
        review_status: Optional[str] = None,
        content_policy: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update a creative (e.g., approve/reject)."""
        args = {"creativeid": creative_id}
        if review_status:
            args["reviewstatus"] = review_status
        if content_policy:
            args["contentpolicy"] = content_policy
        return await self._call_tool("update_creative", args)

    # =========================================================================
    # Assignment Operations
    # =========================================================================

    async def list_assignments(
        self,
        placement_id: Optional[str] = None,
        creative_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List assignments."""
        args = {}
        if placement_id:
            args["placementid"] = placement_id
        if creative_id:
            args["creativeid"] = creative_id
        return await self._call_tool("list_assignments", args)

    async def create_assignment(
        self,
        placement_id: str,
        creative_id: str,
        rotation_mode: str,
        effective_start_date: str,
        effective_end_date: str,
        assignment_id: Optional[str] = None,
        sov: Optional[float] = None,
    ) -> dict[str, Any]:
        """Create an assignment linking creative to placement."""
        args = {
            "placementid": placement_id,
            "creativeid": creative_id,
            "rotationmode": rotation_mode,
            "effectivestartdate": effective_start_date,
            "effectiveenddate": effective_end_date,
        }
        if assignment_id:
            args["assignmentid"] = assignment_id
        if sov is not None:
            args["sov"] = sov
        return await self._call_tool("create_assignment", args)

    # =========================================================================
    # Ad Server Integration Operations
    # =========================================================================

    async def create_ad_server_config(
        self,
        name: str,
        server_type: str,
        organization_id: str,
        network_code: Optional[str] = None,
        json_key_file_path: Optional[str] = None,
        status: str = "active",
    ) -> dict[str, Any]:
        """Create an ad server configuration."""
        args = {
            "name": name,
            "type": server_type,
            "organization_id": organization_id,
            "status": status,
        }
        if network_code:
            args["network_code"] = network_code
        if json_key_file_path:
            args["json_key_file_path"] = json_key_file_path
        return await self._call_tool("create_ad_server_config", args)

    async def test_ad_server_connection(self, config_id: str) -> dict[str, Any]:
        """Test connection to ad server."""
        return await self._call_tool(
            "test_ad_server_connection", {"config_id": config_id}
        )

    async def sync_inventory_from_ad_server(
        self,
        config_id: str,
        organization_id: str,
        update_existing: bool = True,
    ) -> dict[str, Any]:
        """Sync inventory from ad server to create inventory segments."""
        return await self._call_tool(
            "sync_inventory_from_ad_server",
            {
                "config_id": config_id,
                "organization_id": organization_id,
                "update_existing": update_existing,
            },
        )

    async def sync_proposal_to_ad_server(
        self,
        config_id: str,
        proposal_id: str,
    ) -> dict[str, Any]:
        """Sync accepted proposal to ad server (creates Order/Deal)."""
        return await self._call_tool(
            "sync_proposal_to_ad_server",
            {
                "config_id": config_id,
                "proposalid": proposal_id,
            },
        )

    async def list_entity_mappings(
        self,
        config_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        sync_status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List entity mappings between OpenDirect and ad server."""
        args = {}
        if config_id:
            args["config_id"] = config_id
        if entity_type:
            args["entity_type"] = entity_type
        if entity_id:
            args["entity_id"] = entity_id
        if sync_status:
            args["sync_status"] = sync_status
        return await self._call_tool("list_entity_mappings", args)
