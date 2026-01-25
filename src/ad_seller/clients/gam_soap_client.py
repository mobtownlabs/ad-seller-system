"""Google Ad Manager SOAP API client.

Provides methods for writing to GAM using the SOAP API.
Used for creating orders, line items, and managing audience segments.
"""

from datetime import datetime
from typing import Any, Optional

from ..config import get_settings
from ..models.gam import (
    GAMAudienceSegment,
    GAMAudienceSegmentStatus,
    GAMAudienceSegmentType,
    GAMCompany,
    GAMDateTime,
    GAMGoal,
    GAMGoalType,
    GAMLineItem,
    GAMLineItemStatus,
    GAMLineItemType,
    GAMMoney,
    GAMOrder,
    GAMOrderStatus,
    GAMTargeting,
    GAMUnitType,
    GAMCostType,
)


class GAMSoapClient:
    """SOAP API client for writing to Google Ad Manager.

    Uses the GAM SOAP API (via googleads library) for write operations
    like creating orders, line items, and audience segments.

    Usage:
        client = GAMSoapClient()
        client.connect()
        order = client.create_order(name="My Order", advertiser_id="123", ...)
    """

    def __init__(
        self,
        network_code: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """Initialize the GAM SOAP client.

        Args:
            network_code: GAM network code (defaults to settings)
            credentials_path: Path to service account JSON key (defaults to settings)
        """
        settings = get_settings()
        self.network_code = network_code or settings.gam_network_code
        self.credentials_path = credentials_path or settings.gam_json_key_path
        self.application_name = settings.gam_application_name
        self.api_version = settings.gam_api_version
        self.default_trafficker_id = settings.gam_default_trafficker_id

        self._client: Optional[Any] = None

    def connect(self) -> None:
        """Connect to GAM SOAP API."""
        if not self.network_code or not self.credentials_path:
            raise ValueError(
                "GAM network_code and credentials_path are required. "
                "Set GAM_NETWORK_CODE and GAM_JSON_KEY_PATH environment variables."
            )

        try:
            from googleads import ad_manager
            from googleads import oauth2

            # Load credentials
            oauth2_client = oauth2.GoogleServiceAccountClient(
                self.credentials_path,
                oauth2.GetAPIScope("ad_manager"),
            )

            # Create Ad Manager client
            self._client = ad_manager.AdManagerClient(
                oauth2_client,
                self.application_name,
                network_code=self.network_code,
            )
        except ImportError:
            raise ImportError(
                "GAM SOAP client requires googleads. "
                "Install with: pip install 'ad_seller_system[gam]'"
            )

    def disconnect(self) -> None:
        """Disconnect from GAM SOAP API."""
        self._client = None

    def _ensure_connected(self) -> None:
        """Ensure the client is connected."""
        if not self._client:
            raise RuntimeError("GAM SOAP client not connected. Call connect() first.")

    def _get_service(self, service_name: str) -> Any:
        """Get a GAM service by name."""
        self._ensure_connected()
        return self._client.GetService(service_name, version=self.api_version)

    # =========================================================================
    # Company Operations
    # =========================================================================

    def get_advertiser_by_name(self, name: str) -> Optional[GAMCompany]:
        """Look up an advertiser company by name.

        Args:
            name: Company name to search for

        Returns:
            The company if found, None otherwise
        """
        company_service = self._get_service("CompanyService")

        # Build filter statement
        statement = (
            f"WHERE type = 'ADVERTISER' AND name = '{name}' LIMIT 1"
        )

        response = company_service.getCompaniesByStatement({"query": statement})

        # SOAP returns ZEEP objects - use getattr
        results = getattr(response, "results", None) or []
        if results:
            company_data = results[0]
            return GAMCompany(
                id=str(getattr(company_data, "id", 0)),
                name=getattr(company_data, "name", ""),
                type=getattr(company_data, "type", "ADVERTISER"),
                external_id=getattr(company_data, "externalId", None),
            )
        return None

    def get_or_create_advertiser(self, name: str, external_id: Optional[str] = None) -> str:
        """Get an existing advertiser or create a new one.

        Args:
            name: Advertiser company name
            external_id: Optional external ID for the company

        Returns:
            The company ID
        """
        # Try to find existing
        existing = self.get_advertiser_by_name(name)
        if existing:
            return existing.id

        # Create new advertiser
        company_service = self._get_service("CompanyService")

        company = {
            "name": name,
            "type": "ADVERTISER",
        }
        if external_id:
            company["externalId"] = external_id

        result = company_service.createCompanies([company])
        # SOAP returns ZEEP objects
        return str(getattr(result[0], "id", 0))

    # =========================================================================
    # Order Operations
    # =========================================================================

    def create_order(
        self,
        name: str,
        advertiser_id: str,
        trafficker_id: Optional[str] = None,
        agency_id: Optional[str] = None,
        notes: Optional[str] = None,
        external_order_id: Optional[str] = None,
        is_programmatic: bool = True,
    ) -> GAMOrder:
        """Create a new order in GAM.

        Args:
            name: Order name
            advertiser_id: Advertiser company ID
            trafficker_id: Trafficker user ID (defaults to settings)
            agency_id: Optional agency company ID
            notes: Optional order notes
            external_order_id: Optional external reference ID
            is_programmatic: Whether this is a programmatic order

        Returns:
            The created order
        """
        order_service = self._get_service("OrderService")

        # Use default trafficker if not specified
        trafficker = trafficker_id or self.default_trafficker_id
        if not trafficker:
            raise ValueError(
                "trafficker_id is required. Set GAM_DEFAULT_TRAFFICKER_ID or pass trafficker_id."
            )

        order = {
            "name": name,
            "advertiserId": int(advertiser_id),
            "traffickerId": int(trafficker),
            "isProgrammatic": is_programmatic,
        }

        if agency_id:
            order["agencyId"] = int(agency_id)
        if notes:
            order["notes"] = notes
        if external_order_id:
            order["externalOrderId"] = external_order_id

        result = order_service.createOrders([order])
        order_data = result[0]

        return GAMOrder(
            id=str(order_data["id"]),
            name=order_data["name"],
            advertiser_id=str(order_data["advertiserId"]),
            trafficker_id=str(order_data["traffickerId"]),
            agency_id=str(order_data["agencyId"]) if order_data.get("agencyId") else None,
            status=GAMOrderStatus(order_data.get("status", "DRAFT")),
            external_order_id=order_data.get("externalOrderId"),
            notes=order_data.get("notes"),
            is_programmatic=order_data.get("isProgrammatic", False),
        )

    def approve_order(self, order_id: str) -> GAMOrder:
        """Approve an order (submit for delivery).

        Args:
            order_id: The order ID

        Returns:
            The updated order
        """
        order_service = self._get_service("OrderService")

        # Perform approve action
        action = {"xsi_type": "ApproveOrders"}
        statement = f"WHERE id = {order_id}"

        result = order_service.performOrderAction(
            action, {"query": statement}
        )

        # Fetch updated order
        response = order_service.getOrdersByStatement({"query": statement})
        order_data = response["results"][0]

        return self._parse_order(order_data)

    def _parse_order(self, data: dict[str, Any]) -> GAMOrder:
        """Parse SOAP response into GAMOrder model."""
        return GAMOrder(
            id=str(data["id"]),
            name=data["name"],
            advertiser_id=str(data["advertiserId"]),
            trafficker_id=str(data["traffickerId"]),
            agency_id=str(data["agencyId"]) if data.get("agencyId") else None,
            status=GAMOrderStatus(data.get("status", "DRAFT")),
            external_order_id=data.get("externalOrderId"),
            notes=data.get("notes"),
            is_programmatic=data.get("isProgrammatic", False),
        )

    # =========================================================================
    # Line Item Operations
    # =========================================================================

    def create_line_item(
        self,
        order_id: str,
        name: str,
        line_item_type: GAMLineItemType,
        targeting: GAMTargeting,
        cost_per_unit: GAMMoney,
        goal: GAMGoal,
        start_time: datetime,
        end_time: datetime,
        cost_type: GAMCostType = GAMCostType.CPM,
        creative_sizes: Optional[list[tuple[int, int]]] = None,
        external_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> GAMLineItem:
        """Create a line item within an order.

        Args:
            order_id: The parent order ID
            name: Line item name
            line_item_type: Type of line item
            targeting: Targeting configuration
            cost_per_unit: Cost per unit (CPM, CPC, etc.)
            goal: Delivery goal
            start_time: Start datetime
            end_time: End datetime
            cost_type: Cost type (CPM, CPC, CPD, CPCV)
            creative_sizes: List of (width, height) tuples for creative placeholders.
                           Defaults to common display sizes if not provided.
            external_id: Optional external reference ID
            notes: Optional notes

        Returns:
            The created line item
        """
        line_item_service = self._get_service("LineItemService")

        # Build targeting
        targeting_dict: dict[str, Any] = {}

        if targeting.inventory_targeting:
            targeted_units = []
            for unit in targeting.inventory_targeting.targeted_ad_units:
                targeted_units.append({
                    "adUnitId": int(unit.ad_unit_id),
                    "includeDescendants": unit.include_descendants,
                })
            targeting_dict["inventoryTargeting"] = {
                "targetedAdUnits": targeted_units,
            }

        if targeting.custom_targeting:
            targeting_dict["customTargeting"] = targeting.custom_targeting.model_dump(
                by_alias=True
            )

        # Default creative sizes if not provided
        if creative_sizes is None:
            creative_sizes = [(300, 250), (728, 90)]  # Common display sizes

        # Build creative placeholders
        creative_placeholders = [
            {"size": {"width": w, "height": h, "isAspectRatio": False}}
            for w, h in creative_sizes
        ]

        # Build line item
        line_item = {
            "orderId": int(order_id),
            "name": name,
            "lineItemType": line_item_type.value,
            "targeting": targeting_dict,
            "costType": cost_type.value,
            "costPerUnit": {
                "currencyCode": cost_per_unit.currency_code,
                "microAmount": cost_per_unit.micro_amount,
            },
            "primaryGoal": {
                "goalType": goal.goal_type.value,
                "unitType": goal.unit_type.value,
                "units": goal.units,
            },
            "startDateTime": self._to_soap_datetime(start_time),
            "endDateTime": self._to_soap_datetime(end_time),
            "creativePlaceholders": creative_placeholders,
        }

        if external_id:
            line_item["externalId"] = external_id
        if notes:
            line_item["notes"] = notes

        result = line_item_service.createLineItems([line_item])
        line_item_data = result[0]

        return self._parse_line_item(line_item_data)

    def update_line_item(
        self,
        line_item_id: str,
        updates: dict[str, Any],
    ) -> GAMLineItem:
        """Update an existing line item.

        Args:
            line_item_id: The line item ID
            updates: Dictionary of fields to update

        Returns:
            The updated line item
        """
        line_item_service = self._get_service("LineItemService")

        # Fetch current line item
        statement = f"WHERE id = {line_item_id}"
        response = line_item_service.getLineItemsByStatement({"query": statement})
        line_item = response["results"][0]

        # Apply updates
        for key, value in updates.items():
            line_item[key] = value

        result = line_item_service.updateLineItems([line_item])
        return self._parse_line_item(result[0])

    def _parse_line_item(self, data: dict[str, Any]) -> GAMLineItem:
        """Parse SOAP response into GAMLineItem model."""
        cost_data = data.get("costPerUnit", {})

        return GAMLineItem(
            id=str(data["id"]),
            order_id=str(data["orderId"]),
            name=data["name"],
            line_item_type=GAMLineItemType(data.get("lineItemType", "STANDARD")),
            status=GAMLineItemStatus(data.get("status", "DRAFT")),
            cost_type=GAMCostType(data.get("costType", "CPM")),
            cost_per_unit=GAMMoney(
                currency_code=cost_data.get("currencyCode", "USD"),
                micro_amount=cost_data.get("microAmount", 0),
            ),
            primary_goal=GAMGoal(
                goal_type=GAMGoalType(data["primaryGoal"].get("goalType", "LIFETIME")),
                unit_type=GAMUnitType(data["primaryGoal"].get("unitType", "IMPRESSIONS")),
                units=data["primaryGoal"].get("units", -1),
            ),
            external_id=data.get("externalId"),
            notes=data.get("notes"),
        )

    def _to_soap_datetime(self, dt: datetime) -> dict[str, Any]:
        """Convert Python datetime to SOAP datetime format."""
        return {
            "date": {
                "year": dt.year,
                "month": dt.month,
                "day": dt.day,
            },
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second,
            "timeZoneId": "America/New_York",
        }

    # =========================================================================
    # Audience Segment Operations
    # =========================================================================

    def list_audience_segments(
        self,
        filter_statement: Optional[str] = None,
        limit: int = 500,
    ) -> list[GAMAudienceSegment]:
        """List audience segments.

        Args:
            filter_statement: Optional PQL filter
            limit: Maximum results to return

        Returns:
            List of audience segments
        """
        segment_service = self._get_service("AudienceSegmentService")

        statement = filter_statement or ""
        if statement and not statement.upper().startswith("WHERE"):
            statement = f"WHERE {statement}"
        statement += f" LIMIT {limit}"

        response = segment_service.getAudienceSegmentsByStatement({"query": statement})

        segments = []
        # SOAP returns ZEEP objects, use attribute access not .get()
        results = getattr(response, "results", None) or []
        for data in results:
            segment = self._parse_audience_segment(data)
            segments.append(segment)

        return segments

    def get_audience_segment(self, segment_id: int) -> GAMAudienceSegment:
        """Get a specific audience segment by ID.

        Args:
            segment_id: The segment ID

        Returns:
            The audience segment
        """
        segment_service = self._get_service("AudienceSegmentService")

        statement = f"WHERE id = {segment_id}"
        response = segment_service.getAudienceSegmentsByStatement({"query": statement})

        results = getattr(response, "results", None) or []
        if not results:
            raise ValueError(f"Audience segment {segment_id} not found")

        return self._parse_audience_segment(results[0])

    def create_audience_segment(
        self,
        name: str,
        description: Optional[str] = None,
        membership_expiration_days: int = 30,
    ) -> GAMAudienceSegment:
        """Create a first-party audience segment.

        Args:
            name: Segment name
            description: Optional description
            membership_expiration_days: Days until membership expires

        Returns:
            The created segment
        """
        segment_service = self._get_service("AudienceSegmentService")

        segment = {
            "xsi_type": "RuleBasedFirstPartyAudienceSegment",
            "name": name,
            "membershipExpirationDays": membership_expiration_days,
            "status": "INACTIVE",  # Created as inactive, needs activation
        }

        if description:
            segment["description"] = description

        result = segment_service.createAudienceSegments([segment])
        return self._parse_audience_segment(result[0])

    def activate_audience_segment(self, segment_id: int) -> bool:
        """Activate an audience segment for targeting.

        Args:
            segment_id: The segment ID

        Returns:
            True if successful
        """
        segment_service = self._get_service("AudienceSegmentService")

        action = {"xsi_type": "ActivateAudienceSegments"}
        statement = f"WHERE id = {segment_id}"

        result = segment_service.performAudienceSegmentAction(
            action, {"query": statement}
        )

        return getattr(result, "numChanges", 0) > 0

    def _parse_audience_segment(self, data: Any) -> GAMAudienceSegment:
        """Parse SOAP response (ZEEP object) into GAMAudienceSegment model."""
        # SOAP returns ZEEP objects - use getattr for attribute access
        # Determine segment type from the object type name
        type_name = type(data).__name__
        if "RuleBased" in type_name:
            segment_type = GAMAudienceSegmentType.RULE_BASED
        elif "NonRuleBased" in type_name:
            segment_type = GAMAudienceSegmentType.NON_RULE_BASED
        elif "ThirdParty" in type_name:
            segment_type = GAMAudienceSegmentType.THIRD_PARTY
        else:
            segment_type = GAMAudienceSegmentType.THIRD_PARTY

        return GAMAudienceSegment(
            id=getattr(data, "id", 0),
            name=getattr(data, "name", ""),
            type=segment_type,
            status=GAMAudienceSegmentStatus(getattr(data, "status", "INACTIVE")),
            description=getattr(data, "description", None),
            size=getattr(data, "size", None),
            membership_expiration_days=getattr(data, "membershipExpirationDays", 30),
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user info.

        Returns:
            User information dictionary
        """
        user_service = self._get_service("UserService")
        return user_service.getCurrentUser()
