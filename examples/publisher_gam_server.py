#!/usr/bin/env python3
# Author: Green Mountain Systems AI Inc.
# Donated to IAB Tech Lab

"""Publisher Seller Agent with GAM Integration - MCP Server

This represents a publisher's sell-side platform that:
1. Exposes CTV inventory via MCP
2. Books Programmatic Guaranteed (PG) lines directly in Google Ad Manager
3. Creates Private Marketplace (PMP) deals and returns Deal IDs to buyers

The buyer agent can:
- Discover CTV inventory
- Book PG deals (fixed price, guaranteed delivery) → directly in GAM
- Create PMP deals (floor price, private auction) → returns Deal ID for DSP

Usage:
    cd ad_seller_system/examples
    python publisher_gam_server.py

Runs on port 8001

LIVE GAM INTEGRATION: This server connects to real Google Ad Manager!
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Add parent directory to path for ad_seller imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env from project root (so script works from any directory)
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Rich console for beautiful output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# FastAPI for HTTP server
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("Error: Please install FastAPI: pip install fastapi uvicorn")
    sys.exit(1)

# Import real GAM clients
try:
    from ad_seller.clients import GAMSoapClient, GAMRestClient
    from ad_seller.models.gam import (
        GAMLineItemType,
        GAMGoal,
        GAMGoalType,
        GAMUnitType,
        GAMMoney,
        GAMCostType,
        GAMTargeting,
        GAMInventoryTargeting,
        GAMAdUnitTargeting,
    )
    from ad_seller.config import get_settings
    GAM_AVAILABLE = True
except ImportError as e:
    GAM_AVAILABLE = False
    print(f"Warning: GAM integration not available: {e}")
    print("Running in simulation mode.")

console = Console() if RICH_AVAILABLE else None

# =============================================================================
# Publisher Inventory (CTV focused)
# =============================================================================

class PublisherInventory:
    """Publisher's CTV inventory available for programmatic buying."""

    def __init__(self):
        self.publisher_name = "Premium Streaming Network"

        # Get real GAM network code from settings
        if GAM_AVAILABLE:
            settings = get_settings()
            self.gam_network_code = settings.gam_network_code or "3790"
        else:
            self.gam_network_code = "3790"

        # Products reference real GAM ad unit IDs (created during startup)
        self.products = [
            {
                "id": "ctv-hbo-max-001",
                "name": "HBO Max - Premium Streaming",
                "channel": "ctv",
                "publisher": "HBO Max",
                "inventory_type": "streaming_vod",
                "base_cpm": 32.00,
                "floor_cpm": 26.00,
                "available_impressions": 25_000_000,
                "targeting_options": ["household", "demographic", "behavioral", "contextual"],
                "ad_formats": ["15s", "30s", "60s"],
                "supported_deal_types": ["programmatic_guaranteed", "private_marketplace"],
                "gam_ad_unit_id": None,  # Set during GAM initialization
                "gam_ad_unit_name": "HBO Max CTV",
            },
            {
                "id": "ctv-peacock-001",
                "name": "Peacock - Premium Streaming",
                "channel": "ctv",
                "publisher": "Peacock",
                "inventory_type": "streaming_vod",
                "base_cpm": 28.00,
                "floor_cpm": 22.00,
                "available_impressions": 35_000_000,
                "targeting_options": ["household", "demographic", "behavioral"],
                "ad_formats": ["15s", "30s"],
                "supported_deal_types": ["programmatic_guaranteed", "private_marketplace"],
                "gam_ad_unit_id": None,
                "gam_ad_unit_name": "Peacock CTV",
            },
            {
                "id": "ctv-paramount-001",
                "name": "Paramount+ - Premium Streaming",
                "channel": "ctv",
                "publisher": "Paramount+",
                "inventory_type": "streaming_vod",
                "base_cpm": 26.00,
                "floor_cpm": 20.00,
                "available_impressions": 40_000_000,
                "targeting_options": ["household", "demographic"],
                "ad_formats": ["15s", "30s"],
                "supported_deal_types": ["programmatic_guaranteed", "private_marketplace"],
                "gam_ad_unit_id": None,
                "gam_ad_unit_name": "Paramount Plus CTV",
            },
            {
                "id": "ctv-hulu-001",
                "name": "Hulu - Premium Streaming",
                "channel": "ctv",
                "publisher": "Hulu",
                "inventory_type": "streaming_vod",
                "base_cpm": 24.00,
                "floor_cpm": 18.00,
                "available_impressions": 50_000_000,
                "targeting_options": ["household", "demographic", "behavioral"],
                "ad_formats": ["15s", "30s", "60s"],
                "supported_deal_types": ["programmatic_guaranteed", "private_marketplace"],
                "gam_ad_unit_id": None,
                "gam_ad_unit_name": "Hulu CTV",
            },
        ]

        # Track booked orders and deals
        self.gam_orders = {}  # PG bookings in GAM
        self.pmp_deals = {}   # PMP deals with Deal IDs
        self.request_log = []

        # GAM integration state
        self.gam_connected = False
        self.gam_soap_client = None
        self.gam_rest_client = None
        self.default_trafficker_id = None
        self.private_auction_id = None  # For PMP deals


class TieredPricingEngine:
    """Calculate tiered pricing based on buyer identity and deal type."""

    TIER_DISCOUNTS = {
        "public": 0,
        "seat": 5,
        "agency": 10,
        "advertiser": 15,
    }

    VOLUME_DISCOUNTS = [
        (50_000_000, 8),
        (25_000_000, 5),
        (10_000_000, 3),
        (5_000_000, 2),
    ]

    @classmethod
    def calculate_price(
        cls,
        base_price: float,
        floor_price: float,
        buyer_tier: str,
        volume: int,
        deal_type: str
    ) -> dict:
        """Calculate final price with all discounts."""
        tier_discount = cls.TIER_DISCOUNTS.get(buyer_tier.lower(), 0)

        volume_discount = 0
        for threshold, discount in cls.VOLUME_DISCOUNTS:
            if volume >= threshold:
                volume_discount = discount
                break

        # Deal type pricing
        if deal_type == "programmatic_guaranteed":
            # PG has slight premium for guaranteed delivery
            deal_premium = 5
            total_discount = tier_discount + volume_discount - deal_premium
        else:  # private_marketplace
            # PMP uses floor price as minimum
            total_discount = tier_discount + volume_discount

        final_price = base_price * (1 - total_discount / 100)

        # Ensure we don't go below floor
        final_price = max(final_price, floor_price)

        return {
            "base_price": base_price,
            "floor_price": floor_price,
            "tier": buyer_tier,
            "tier_discount": tier_discount,
            "volume_discount": volume_discount,
            "deal_type": deal_type,
            "total_discount": max(0, total_discount),
            "final_price": round(final_price, 2),
        }


# Global state
inventory = PublisherInventory()
pricing_engine = TieredPricingEngine()

# =============================================================================
# GAM Integration (REAL - Live GAM Connection)
# =============================================================================

def initialize_gam_connection():
    """Initialize connection to Google Ad Manager and set up demo inventory."""
    global inventory

    if not GAM_AVAILABLE:
        log_event("GAM", "GAM integration not available - running in simulation mode")
        return False

    settings = get_settings()

    if not settings.gam_enabled:
        log_event("GAM", "GAM integration disabled in settings")
        return False

    if not settings.gam_network_code or not settings.gam_json_key_path:
        log_event("GAM", "GAM credentials not configured")
        return False

    try:
        # Initialize SOAP client for creating orders/line items
        log_event("GAM", "Connecting to Google Ad Manager SOAP API...")
        soap_client = GAMSoapClient(
            network_code=settings.gam_network_code,
            credentials_path=settings.gam_json_key_path,
        )
        soap_client.connect()
        inventory.gam_soap_client = soap_client
        log_event("GAM", f"✓ Connected to GAM network {settings.gam_network_code}")

        # Get current user as default trafficker
        try:
            current_user = soap_client.get_current_user()
            # ZEEP returns objects, use getattr
            inventory.default_trafficker_id = str(getattr(current_user, "id", 0))
            user_name = getattr(current_user, "name", "Unknown")
            log_event("GAM", f"✓ Default trafficker: {user_name} (ID: {inventory.default_trafficker_id})")
        except Exception as e:
            log_event("GAM", f"Warning: Could not get current user: {e}")
            inventory.default_trafficker_id = "0"

        # List existing ad units and map to products
        log_event("GAM", "Fetching existing ad units...")
        ad_units = soap_client.list_ad_units(limit=100)
        ad_unit_map = {au.name.lower(): au for au in ad_units}
        log_event("GAM", f"✓ Found {len(ad_units)} ad units in GAM")

        # Map products to existing ad units or use first available
        for product in inventory.products:
            product_name_key = product["gam_ad_unit_name"].lower()

            # Try to find matching ad unit
            matched = False
            for au_name, au in ad_unit_map.items():
                if product_name_key in au_name or au_name in product_name_key:
                    product["gam_ad_unit_id"] = au.id
                    log_event("GAM", f"  Mapped {product['id']} → Ad Unit {au.id} ({au.name})")
                    matched = True
                    break

            if not matched and ad_units:
                # Use first available ad unit for demo
                product["gam_ad_unit_id"] = ad_units[0].id
                log_event("GAM", f"  Mapped {product['id']} → Ad Unit {ad_units[0].id} (default)")

        inventory.gam_connected = True
        log_event("GAM", "✓ GAM integration ready!")
        return True

    except Exception as e:
        log_event("GAM", f"✗ Failed to connect to GAM: {e}")
        return False


def get_or_create_advertiser(advertiser_name: str) -> str:
    """Get or create an advertiser in GAM."""
    if not inventory.gam_connected or not inventory.gam_soap_client:
        return f"SIM-ADV-{uuid.uuid4().hex[:8].upper()}"

    try:
        advertiser_id = inventory.gam_soap_client.get_or_create_advertiser(advertiser_name)
        return advertiser_id
    except Exception as e:
        log_event("GAM", f"Warning: Could not get/create advertiser: {e}")
        return f"SIM-ADV-{uuid.uuid4().hex[:8].upper()}"


def create_gam_order(
    order_name: str,
    advertiser_name: str,
    agency_name: str = None,
) -> dict:
    """Create an order in GAM."""
    if not inventory.gam_connected or not inventory.gam_soap_client:
        # Simulation fallback
        order_id = f"SIM-ORD-{uuid.uuid4().hex[:8].upper()}"
        return {
            "order_id": order_id,
            "order_name": order_name,
            "status": "DRAFT",
            "simulated": True,
        }

    try:
        # Get or create advertiser
        advertiser_id = get_or_create_advertiser(advertiser_name)

        # Create order
        order = inventory.gam_soap_client.create_order(
            name=order_name,
            advertiser_id=advertiser_id,
            trafficker_id=inventory.default_trafficker_id,
            notes=f"Created via OpenDirect - Advertiser: {advertiser_name}, Agency: {agency_name or 'Direct'}",
        )

        log_event("GAM", f"✓ Created Order: {order.id} - {order.name}")

        return {
            "order_id": order.id,
            "order_name": order.name,
            "advertiser_id": order.advertiser_id,
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "simulated": False,
        }

    except Exception as e:
        log_event("GAM", f"✗ Error creating order: {e}")
        order_id = f"ERR-ORD-{uuid.uuid4().hex[:8].upper()}"
        return {
            "order_id": order_id,
            "order_name": order_name,
            "status": "ERROR",
            "error": str(e),
            "simulated": True,
        }


def create_gam_line_item(
    order_id: str,
    line_name: str,
    ad_unit_id: str,
    impressions: int,
    cpm_price: float,
    start_date: str,
    end_date: str,
    targeting: dict = None,
) -> dict:
    """Create a line item in GAM."""
    if not inventory.gam_connected or not inventory.gam_soap_client:
        # Simulation fallback
        line_id = f"SIM-LINE-{uuid.uuid4().hex[:8].upper()}"
        return {
            "line_id": line_id,
            "order_id": order_id,
            "line_name": line_name,
            "impressions": impressions,
            "cpm_price": cpm_price,
            "total_budget": round(cpm_price * impressions / 1000, 2),
            "status": "READY",
            "simulated": True,
        }

    try:
        # Parse dates
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Build targeting
        gam_targeting = GAMTargeting(
            inventory_targeting=GAMInventoryTargeting(
                targeted_ad_units=[
                    GAMAdUnitTargeting(ad_unit_id=ad_unit_id, include_descendants=True)
                ]
            )
        )

        # Build goal
        goal = GAMGoal(
            goal_type=GAMGoalType.LIFETIME,
            unit_type=GAMUnitType.IMPRESSIONS,
            units=impressions,
        )

        # Build cost
        cost_per_unit = GAMMoney.from_dollars(cpm_price)

        # Create line item (STANDARD for PG with fixed impressions)
        line_item = inventory.gam_soap_client.create_line_item(
            order_id=order_id,
            name=line_name,
            line_item_type=GAMLineItemType.STANDARD,
            targeting=gam_targeting,
            cost_per_unit=cost_per_unit,
            goal=goal,
            start_time=start_dt,
            end_time=end_dt,
            cost_type=GAMCostType.CPM,
            creative_sizes=[(300, 250), (728, 90), (1920, 1080)],  # Include CTV size
            external_id=f"OD-{uuid.uuid4().hex[:8].upper()}",
            notes=f"OpenDirect PG Line - {impressions:,} impressions @ ${cpm_price} CPM",
        )

        log_event("GAM", f"✓ Created Line Item: {line_item.id} - {line_item.name}")

        return {
            "line_id": line_item.id,
            "order_id": order_id,
            "line_name": line_item.name,
            "impressions": impressions,
            "cpm_price": cpm_price,
            "total_budget": round(cpm_price * impressions / 1000, 2),
            "status": line_item.status.value if hasattr(line_item.status, 'value') else str(line_item.status),
            "simulated": False,
        }

    except Exception as e:
        log_event("GAM", f"✗ Error creating line item: {e}")
        line_id = f"ERR-LINE-{uuid.uuid4().hex[:8].upper()}"
        return {
            "line_id": line_id,
            "order_id": order_id,
            "line_name": line_name,
            "impressions": impressions,
            "cpm_price": cpm_price,
            "total_budget": round(cpm_price * impressions / 1000, 2),
            "status": "ERROR",
            "error": str(e),
            "simulated": True,
        }


def approve_gam_order(order_id: str) -> dict:
    """Approve an order in GAM."""
    if not inventory.gam_connected or not inventory.gam_soap_client:
        return {"order_id": order_id, "status": "APPROVED", "simulated": True}

    try:
        order = inventory.gam_soap_client.approve_order(order_id)
        log_event("GAM", f"✓ Approved Order: {order.id}")
        return {
            "order_id": order.id,
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "simulated": False,
        }
    except Exception as e:
        log_event("GAM", f"Warning: Could not approve order: {e}")
        return {"order_id": order_id, "status": "APPROVAL_PENDING", "error": str(e)}

# =============================================================================
# MCP Tool Definitions
# =============================================================================

MCP_TOOLS = [
    {
        "name": "list_products",
        "description": "List available CTV inventory from publisher",
        "inputSchema": {
            "type": "object",
            "properties": {
                "publisher": {
                    "type": "string",
                    "description": "Filter by publisher name"
                }
            }
        }
    },
    {
        "name": "get_pricing",
        "description": "Get tiered pricing for a product based on buyer identity and deal type",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "buyer_tier": {
                    "type": "string",
                    "enum": ["public", "seat", "agency", "advertiser"]
                },
                "volume": {"type": "integer"},
                "deal_type": {
                    "type": "string",
                    "enum": ["programmatic_guaranteed", "private_marketplace"]
                }
            },
            "required": ["product_id", "deal_type"]
        }
    },
    {
        "name": "check_availability",
        "description": "Check if requested inventory is available",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "impressions": {"type": "integer"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"}
            },
            "required": ["product_id", "impressions"]
        }
    },
    {
        "name": "book_programmatic_guaranteed",
        "description": "Book a Programmatic Guaranteed line directly in Google Ad Manager. Fixed price, guaranteed delivery.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "impressions": {"type": "integer"},
                "cpm_price": {"type": "number"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "advertiser_name": {"type": "string"},
                "agency_name": {"type": "string"},
                "campaign_name": {"type": "string"},
                "targeting": {"type": "object"}
            },
            "required": ["product_id", "impressions", "cpm_price", "advertiser_name"]
        }
    },
    {
        "name": "create_pmp_deal",
        "description": "Create a Private Marketplace deal. Returns a Deal ID that the buyer sends to their DSP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "floor_price": {"type": "number"},
                "impressions": {"type": "integer"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "advertiser_name": {"type": "string"},
                "agency_name": {"type": "string"},
                "buyer_seat_id": {"type": "string"},
                "target_dsp": {
                    "type": "string",
                    "enum": ["generic_dsp", "the_trade_desk", "dv360", "xandr"]
                }
            },
            "required": ["product_id", "floor_price", "buyer_seat_id"]
        }
    }
]

# =============================================================================
# Logging
# =============================================================================

def log_event(source: str, message: str):
    """Log an event with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"timestamp": timestamp, "source": source, "message": message}
    inventory.request_log.append(entry)

    if RICH_AVAILABLE:
        color = "cyan" if source == "MCP" else "magenta" if source == "GAM" else "green"
        console.print(f"[dim]{timestamp}[/dim] [{color}]{source}[/{color}] → {message}")
    else:
        print(f"{timestamp} [{source}] {message}")


# =============================================================================
# MCP Tool Handlers
# =============================================================================

def handle_list_products(args: dict) -> dict:
    """Handle list_products tool call."""
    publisher_filter = args.get("publisher")

    products = inventory.products
    if publisher_filter:
        products = [p for p in products if publisher_filter.lower() in p["publisher"].lower()]

    log_event("MCP", f"list_products → {len(products)} products")

    return {
        "publisher": inventory.publisher_name,
        "products": products,
        "total": len(products),
    }


def handle_get_pricing(args: dict) -> dict:
    """Handle get_pricing tool call."""
    product_id = args.get("product_id")
    buyer_tier = args.get("buyer_tier", "public")
    volume = args.get("volume", 0)
    deal_type = args.get("deal_type", "private_marketplace")

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    pricing = pricing_engine.calculate_price(
        base_price=product["base_cpm"],
        floor_price=product["floor_cpm"],
        buyer_tier=buyer_tier,
        volume=volume,
        deal_type=deal_type
    )

    log_event("MCP", f"get_pricing → {product_id}: ${pricing['final_price']} CPM ({deal_type})")

    return {
        "product_id": product_id,
        "product_name": product["name"],
        "publisher": product["publisher"],
        "pricing": pricing,
    }


def handle_check_availability(args: dict) -> dict:
    """Handle check_availability tool call."""
    product_id = args.get("product_id")
    impressions = args.get("impressions", 0)

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    available = product["available_impressions"]
    is_available = impressions <= available

    log_event("MCP", f"check_availability → {product_id}: {'✓' if is_available else '✗'}")

    return {
        "product_id": product_id,
        "requested": impressions,
        "available": available,
        "is_available": is_available,
    }


def handle_book_programmatic_guaranteed(args: dict) -> dict:
    """Book a PG line directly in GAM (REAL GAM Integration)."""
    product_id = args.get("product_id")
    impressions = args.get("impressions")
    cpm_price = args.get("cpm_price")
    advertiser_name = args.get("advertiser_name")
    agency_name = args.get("agency_name", "Direct")
    campaign_name = args.get("campaign_name", f"{advertiser_name} CTV Campaign")
    start_date = args.get("start_date", "2026-03-01")
    end_date = args.get("end_date", "2026-06-30")
    targeting = args.get("targeting", {})

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    if "programmatic_guaranteed" not in product["supported_deal_types"]:
        return {"error": f"Product {product_id} does not support PG deals"}

    # Check floor price
    if cpm_price < product["floor_cpm"]:
        return {
            "error": f"Price ${cpm_price} below floor ${product['floor_cpm']}",
            "floor_price": product["floor_cpm"]
        }

    # Get ad unit ID (either from GAM or simulation)
    ad_unit_id = product.get("gam_ad_unit_id")
    if not ad_unit_id:
        log_event("GAM", f"Warning: No GAM ad unit for {product_id}, using simulation")
        ad_unit_id = "0"  # Will use simulation mode

    log_event("GAM", f"Booking PG: {campaign_name} - {impressions:,} imps @ ${cpm_price} CPM")

    # Add timestamp to make order name unique (GAM requires unique names)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create GAM order (REAL)
    order = create_gam_order(
        order_name=f"{campaign_name} - OpenDirect PG - {timestamp}",
        advertiser_name=advertiser_name,
        agency_name=agency_name
    )

    if order.get("error"):
        return {
            "error": f"Failed to create GAM order: {order.get('error')}",
            "details": order
        }

    # Create line item (REAL)
    line_item = create_gam_line_item(
        order_id=order["order_id"],
        line_name=f"{product['publisher']} - PG Line - {impressions:,} imps",
        ad_unit_id=ad_unit_id,
        impressions=impressions,
        cpm_price=cpm_price,
        start_date=start_date,
        end_date=end_date,
        targeting=targeting
    )

    if line_item.get("error"):
        log_event("GAM", f"Warning: Line item creation had issues: {line_item.get('error')}")

    # Approve order (REAL)
    approval = approve_gam_order(order["order_id"])

    # Store in inventory
    inventory.gam_orders[order["order_id"]] = {
        "order": order,
        "line_items": [line_item],
        "approval": approval
    }

    is_live = not order.get("simulated", True)
    log_event("GAM", f"{'✓ LIVE' if is_live else '⚡ SIMULATED'} PG Booking Complete: Order {order['order_id']}")

    return {
        "booking_type": "programmatic_guaranteed",
        "status": "booked",
        "live_gam": is_live,
        "gam_order": order,
        "gam_line_item": line_item,
        "approval_status": approval,
        "product": {
            "id": product_id,
            "name": product["name"],
            "publisher": product["publisher"]
        },
        "terms": {
            "impressions": impressions,
            "cpm_price": cpm_price,
            "total_budget": line_item["total_budget"],
            "start_date": start_date,
            "end_date": end_date
        },
        "gam_links": {
            "order_url": f"https://admanager.google.com/{inventory.gam_network_code}#delivery/order/order_overview/order_id={order['order_id']}" if is_live else None,
            "line_item_url": f"https://admanager.google.com/{inventory.gam_network_code}#delivery/line_item/detail/line_item_id={line_item['line_id']}" if is_live else None,
        },
        "message": f"Line booked {'LIVE in Google Ad Manager' if is_live else '(simulated)'}. No DSP action required for PG deals."
    }


def handle_create_pmp_deal(args: dict) -> dict:
    """Create a PMP deal and return Deal ID for DSP.

    This creates a deal structure that:
    1. Can be referenced by the DSP for private auction bidding
    2. Is tracked locally for reporting
    3. The Deal ID follows OpenRTB conventions
    """
    product_id = args.get("product_id")
    floor_price = args.get("floor_price")
    impressions = args.get("impressions", 0)
    advertiser_name = args.get("advertiser_name", "Unknown")
    agency_name = args.get("agency_name", "Direct")
    buyer_seat_id = args.get("buyer_seat_id")
    target_dsp = args.get("target_dsp", "generic_dsp")
    start_date = args.get("start_date", "2026-03-01")
    end_date = args.get("end_date", "2026-06-30")

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    if "private_marketplace" not in product["supported_deal_types"]:
        return {"error": f"Product {product_id} does not support PMP deals"}

    # Check floor price
    if floor_price < product["floor_cpm"]:
        return {
            "error": f"Floor ${floor_price} below minimum ${product['floor_cpm']}",
            "minimum_floor": product["floor_cpm"]
        }

    # Generate Deal ID (format: PMP-<network>-<unique>)
    # NOTE: This is a SIMULATED deal ID for demo purposes.
    # Real PMP deals require GAM Programmatic Direct features to be enabled.
    deal_id = f"PMP-{inventory.gam_network_code}-{uuid.uuid4().hex[:8].upper()}"

    log_event("GAM", f"Creating PMP Deal (SIMULATED): {deal_id} - Floor ${floor_price} CPM")

    # DSP-specific configuration
    dsp_configs = {
        "generic_dsp": {
            "platform": "DSP",
            "seat_id_format": "dsp-*",
            "activation_url": "https://dsp.example.com/deals",
        },
        "the_trade_desk": {
            "platform": "The Trade Desk",
            "seat_id_format": "ttd-*",
            "activation_url": "https://desk.thetradedesk.com",
        },
        "dv360": {
            "platform": "Display & Video 360",
            "seat_id_format": "dv360-*",
            "activation_url": "https://displayvideo.google.com",
        },
        "xandr": {
            "platform": "Xandr",
            "seat_id_format": "xandr-*",
            "activation_url": "https://invest.xandr.com",
        }
    }

    dsp_config = dsp_configs.get(target_dsp, dsp_configs["generic_dsp"])

    deal = {
        "deal_id": deal_id,
        "deal_type": "private_marketplace",
        "product_id": product_id,
        "product_name": product["name"],
        "publisher": product["publisher"],
        "gam_ad_unit_id": product.get("gam_ad_unit_id"),
        "floor_price": floor_price,
        "auction_type": "first_price",
        "impressions_estimate": impressions,
        "start_date": start_date,
        "end_date": end_date,
        "advertiser_name": advertiser_name,
        "agency_name": agency_name,
        "buyer_seat_id": buyer_seat_id,
        "target_dsp": target_dsp,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "gam_network_code": inventory.gam_network_code,
        "simulated": True,  # PMP deals are simulated for demo
        "openrtb_params": {
            "id": deal_id,
            "bidfloor": floor_price,
            "bidfloorcur": "USD",
            "at": 1,  # First price auction
            "wseat": [buyer_seat_id],
            "wadomain": [],
        },
        "dsp_activation": {
            "platform": dsp_config["platform"],
            "deal_id": deal_id,
            "activation_url": dsp_config["activation_url"],
            "instructions": [
                f"1. Log into {dsp_config['platform']}",
                "2. Navigate to Deals / Private Inventory",
                f"3. Add new deal with ID: {deal_id}",
                f"4. Set floor price: ${floor_price} CPM",
                "5. Apply to your campaign targeting",
            ]
        }
    }

    inventory.pmp_deals[deal_id] = deal
    log_event("GAM", f"✓ PMP Deal Created (SIMULATED): {deal_id} → {dsp_config['platform']}")

    return {
        "booking_type": "private_marketplace",
        "status": "deal_created",
        "simulated": True,  # PMP deals are simulated - GAM Programmatic Direct not enabled
        "deal": deal,
        "next_step": f"Send Deal ID '{deal_id}' to {dsp_config['platform']} to activate",
        "message": "PMP Deal ID created (SIMULATED for demo). In production, this would be registered in GAM Programmatic Direct.",
        "note": "This Deal ID is for demo purposes. Real PMP deals require GAM Programmatic Direct features."
    }


TOOL_HANDLERS = {
    "list_products": handle_list_products,
    "get_pricing": handle_get_pricing,
    "check_availability": handle_check_availability,
    "book_programmatic_guaranteed": handle_book_programmatic_guaranteed,
    "create_pmp_deal": handle_create_pmp_deal,
}

# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Publisher Seller Agent (GAM)",
    description="CTV Publisher with Google Ad Manager integration",
    version="1.0.0"
)


@app.get("/")
async def root():
    return {
        "name": "Publisher Seller Agent",
        "publisher": inventory.publisher_name,
        "integration": "Google Ad Manager",
        "port": 8001,
        "capabilities": ["programmatic_guaranteed", "private_marketplace"]
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/mcp/tools")
async def list_tools():
    return {"tools": MCP_TOOLS}


@app.post("/mcp/call")
async def call_tool(request: Request):
    try:
        body = await request.json()
        tool_name = body.get("name")
        arguments = body.get("arguments", {})

        if tool_name not in TOOL_HANDLERS:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        handler = TOOL_HANDLERS[tool_name]
        result = handler(arguments)

        return {"success": True, "tool": tool_name, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Main
# =============================================================================

def print_banner(gam_connected: bool = False):
    """Print server banner."""
    gam_status = "🟢 LIVE" if gam_connected else "🟡 SIMULATION"
    gam_network = inventory.gam_network_code if gam_connected else "N/A"

    if RICH_AVAILABLE:
        banner = f"""
╔══════════════════════════════════════════════════════════════╗
║       PUBLISHER SELLER AGENT - Google Ad Manager Integration ║
╠══════════════════════════════════════════════════════════════╣
║  Publisher: Premium Streaming Network                        ║
║  Port: 8001                                                  ║
║  GAM Status: {gam_status:<46} ║
║  GAM Network: {gam_network:<45} ║
╠══════════════════════════════════════════════════════════════╣
║  Capabilities:                                               ║
║    • Programmatic Guaranteed (PG) - Book directly in GAM     ║
║    • Private Marketplace (PMP) - Returns Deal ID for DSP     ║
╠══════════════════════════════════════════════════════════════╣
║  MCP Tools:                                                  ║
║    • list_products                                           ║
║    • get_pricing                                             ║
║    • check_availability                                      ║
║    • book_programmatic_guaranteed  → Books in GAM            ║
║    • create_pmp_deal               → Returns Deal ID         ║
╠══════════════════════════════════════════════════════════════╣
║  Waiting for buyer agent connections...                      ║
╚══════════════════════════════════════════════════════════════╝
"""
        console.print(Panel(banner.strip(), style="bold blue"))
    else:
        print("\n" + "=" * 60)
        print("PUBLISHER SELLER AGENT - GAM Integration")
        print("=" * 60)
        print(f"Port: 8001")
        print(f"GAM Status: {gam_status}")
        print(f"GAM Network: {gam_network}")
        print("=" * 60 + "\n")


def main():
    """Run the publisher MCP server."""
    if RICH_AVAILABLE:
        console.print("\n[bold cyan]Initializing Publisher Seller Agent...[/bold cyan]\n")

    # Initialize GAM connection
    gam_connected = initialize_gam_connection()

    # Print banner with GAM status
    print_banner(gam_connected)

    if RICH_AVAILABLE:
        console.print("\n[bold green]Starting server...[/bold green]\n")
        console.print("[dim]Activity log:[/dim]\n")

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
