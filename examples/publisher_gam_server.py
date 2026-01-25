#!/usr/bin/env python3
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
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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

console = Console() if RICH_AVAILABLE else None

# =============================================================================
# Publisher Inventory (CTV focused)
# =============================================================================

class PublisherInventory:
    """Publisher's CTV inventory available for programmatic buying."""

    def __init__(self):
        self.publisher_name = "Premium Streaming Network"
        self.gam_network_code = "12345678"

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
                "gam_ad_unit_id": "/12345678/hbo_max_ctv",
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
                "gam_ad_unit_id": "/12345678/peacock_ctv",
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
                "gam_ad_unit_id": "/12345678/paramount_ctv",
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
                "gam_ad_unit_id": "/12345678/hulu_ctv",
            },
        ]

        # Track booked orders and deals
        self.gam_orders = {}  # PG bookings in GAM
        self.pmp_deals = {}   # PMP deals with Deal IDs
        self.request_log = []


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
# GAM Integration (Simulated)
# =============================================================================

class GAMClient:
    """Simulated Google Ad Manager client for booking PG lines."""

    def __init__(self, network_code: str):
        self.network_code = network_code
        self.orders = {}
        self.line_items = {}

    def create_order(
        self,
        order_name: str,
        advertiser_name: str,
        agency_name: str,
        trafficker_email: str = "trafficker@publisher.com"
    ) -> dict:
        """Create an order in GAM."""
        order_id = f"GAM-ORD-{uuid.uuid4().hex[:8].upper()}"

        order = {
            "order_id": order_id,
            "order_name": order_name,
            "advertiser_name": advertiser_name,
            "agency_name": agency_name,
            "trafficker_email": trafficker_email,
            "status": "DRAFT",
            "created_at": datetime.now().isoformat(),
            "gam_network_code": self.network_code,
        }

        self.orders[order_id] = order
        log_event("GAM", f"Created Order: {order_id}")
        return order

    def create_line_item(
        self,
        order_id: str,
        line_name: str,
        ad_unit_id: str,
        impressions: int,
        cpm_price: float,
        start_date: str,
        end_date: str,
        targeting: dict = None
    ) -> dict:
        """Create a Programmatic Guaranteed line item in GAM."""
        line_id = f"GAM-LINE-{uuid.uuid4().hex[:8].upper()}"

        line_item = {
            "line_id": line_id,
            "order_id": order_id,
            "line_name": line_name,
            "ad_unit_id": ad_unit_id,
            "line_item_type": "PROGRAMMATIC_GUARANTEED",
            "impressions": impressions,
            "cpm_price": cpm_price,
            "total_budget": round(cpm_price * impressions / 1000, 2),
            "start_date": start_date,
            "end_date": end_date,
            "targeting": targeting or {},
            "status": "READY",
            "delivery_status": "NOT_STARTED",
            "created_at": datetime.now().isoformat(),
        }

        self.line_items[line_id] = line_item
        log_event("GAM", f"Created PG Line: {line_id} ({impressions:,} imps @ ${cpm_price} CPM)")
        return line_item

    def approve_order(self, order_id: str) -> dict:
        """Approve an order for delivery."""
        if order_id in self.orders:
            self.orders[order_id]["status"] = "APPROVED"
            log_event("GAM", f"Approved Order: {order_id}")
            return self.orders[order_id]
        return {"error": "Order not found"}


# Global GAM client
gam_client = GAMClient(inventory.gam_network_code)

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
                    "enum": ["amazon_dsp", "the_trade_desk", "dv360", "xandr"]
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
    """Book a PG line directly in GAM."""
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

    # Create GAM order
    order = gam_client.create_order(
        order_name=f"{campaign_name} - OpenDirect",
        advertiser_name=advertiser_name,
        agency_name=agency_name
    )

    # Create line item
    line_item = gam_client.create_line_item(
        order_id=order["order_id"],
        line_name=f"{product['publisher']} - PG Line",
        ad_unit_id=product["gam_ad_unit_id"],
        impressions=impressions,
        cpm_price=cpm_price,
        start_date=start_date,
        end_date=end_date,
        targeting=targeting
    )

    # Approve order
    gam_client.approve_order(order["order_id"])

    # Store in inventory
    inventory.gam_orders[order["order_id"]] = {
        "order": order,
        "line_items": [line_item]
    }

    log_event("GAM", f"PG Booking Complete: {order['order_id']}")

    return {
        "booking_type": "programmatic_guaranteed",
        "status": "booked",
        "gam_order": order,
        "gam_line_item": line_item,
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
        "message": "Line booked directly in Google Ad Manager. No DSP action required."
    }


def handle_create_pmp_deal(args: dict) -> dict:
    """Create a PMP deal and return Deal ID for DSP."""
    product_id = args.get("product_id")
    floor_price = args.get("floor_price")
    impressions = args.get("impressions", 0)
    advertiser_name = args.get("advertiser_name", "Unknown")
    agency_name = args.get("agency_name", "Direct")
    buyer_seat_id = args.get("buyer_seat_id")
    target_dsp = args.get("target_dsp", "amazon_dsp")
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

    # Generate Deal ID
    deal_id = f"PMP-{uuid.uuid4().hex[:8].upper()}"

    # DSP-specific configuration
    dsp_configs = {
        "amazon_dsp": {
            "platform": "Amazon DSP",
            "seat_id_format": "amazon-dsp-*",
            "activation_url": "https://advertising.amazon.com/dsp/deals",
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

    dsp_config = dsp_configs.get(target_dsp, dsp_configs["amazon_dsp"])

    deal = {
        "deal_id": deal_id,
        "deal_type": "private_marketplace",
        "product_id": product_id,
        "product_name": product["name"],
        "publisher": product["publisher"],
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
    log_event("MCP", f"PMP Deal Created: {deal_id} → Send to {dsp_config['platform']}")

    return {
        "booking_type": "private_marketplace",
        "status": "deal_created",
        "deal": deal,
        "next_step": f"Send Deal ID {deal_id} to {dsp_config['platform']} to activate",
        "message": "Deal ID created. Buyer must add this deal to their DSP campaign."
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

def print_banner():
    """Print server banner."""
    if RICH_AVAILABLE:
        banner = """
╔══════════════════════════════════════════════════════════════╗
║       PUBLISHER SELLER AGENT - Google Ad Manager Integration ║
╠══════════════════════════════════════════════════════════════╣
║  Publisher: Premium Streaming Network                        ║
║  Port: 8001                                                  ║
║  Integration: Google Ad Manager                              ║
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
        print("Port: 8001")
        print("=" * 60 + "\n")


def main():
    """Run the publisher MCP server."""
    print_banner()

    if RICH_AVAILABLE:
        console.print("\n[bold green]Starting server...[/bold green]\n")
        console.print("[dim]Activity log:[/dim]\n")

    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
