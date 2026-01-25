#!/usr/bin/env python3
"""Seller Agent MCP Server - Interactive Demo

This starts the seller agent as an MCP server that the buyer agent can connect to.
Run this in one terminal, then run the buyer demo in another terminal.

Usage:
    cd ad_seller_system/examples
    python seller_mcp_server.py

The server will listen on http://localhost:8000 and expose MCP tools for:
- list_products: Get available inventory
- get_pricing: Get tiered pricing based on buyer identity
- check_availability: Check inventory availability
- create_deal: Generate Deal IDs for DSP activation
- book_order: Book OpenDirect order lines
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Rich console for beautiful output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Note: Install 'rich' for enhanced output: pip install rich")

# FastAPI for HTTP server
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import StreamingResponse, JSONResponse
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    print("Error: Please install FastAPI: pip install fastapi uvicorn")
    sys.exit(1)

console = Console() if RICH_AVAILABLE else None

# =============================================================================
# Seller Inventory & State
# =============================================================================

class SellerInventory:
    """Seller's available inventory for the demo."""

    def __init__(self):
        self.products = [
            {
                "id": "ctv-premium-001",
                "name": "Premium CTV - HBO Max + Peacock Bundle",
                "channel": "ctv",
                "type": "streaming",
                "base_price": 28.00,
                "floor_price": 22.00,
                "available_impressions": 50_000_000,
                "targeting": ["household", "demographic", "behavioral"],
                "publishers": ["HBO Max", "Peacock"],
                "formats": ["15s", "30s", "60s"],
            },
            {
                "id": "ctv-standard-001",
                "name": "Standard CTV - Paramount+ & Hulu",
                "channel": "ctv",
                "type": "streaming",
                "base_price": 22.00,
                "floor_price": 18.00,
                "available_impressions": 80_000_000,
                "targeting": ["household", "demographic"],
                "publishers": ["Paramount+", "Hulu"],
                "formats": ["15s", "30s"],
            },
            {
                "id": "ctv-sports-001",
                "name": "Live Sports CTV Package",
                "channel": "ctv",
                "type": "live_sports",
                "base_price": 45.00,
                "floor_price": 38.00,
                "available_impressions": 25_000_000,
                "targeting": ["household", "geo", "sports_affinity"],
                "publishers": ["ESPN+", "Fox Sports"],
                "formats": ["15s", "30s"],
            },
            {
                "id": "display-perf-001",
                "name": "Performance Display - ComScore Top 200",
                "channel": "display",
                "type": "performance",
                "base_price": 8.00,
                "floor_price": 5.00,
                "available_impressions": 500_000_000,
                "targeting": ["behavioral", "contextual", "retargeting"],
                "publishers": ["ComScore Top 200"],
                "formats": ["300x250", "728x90", "160x600", "320x50"],
            },
            {
                "id": "mobile-app-001",
                "name": "Mobile App Install Campaign",
                "channel": "mobile",
                "type": "app_install",
                "base_price": 12.00,
                "floor_price": 8.00,
                "available_impressions": 100_000_000,
                "targeting": ["device", "behavioral", "lookalike"],
                "publishers": ["Premium App Network"],
                "formats": ["interstitial", "rewarded", "native"],
            },
        ]

        # Track active deals and orders
        self.deals = {}
        self.orders = {}
        self.request_log = []


class TieredPricingEngine:
    """Calculate tiered pricing based on buyer identity."""

    TIER_DISCOUNTS = {
        "public": 0,
        "seat": 5,
        "agency": 10,
        "advertiser": 15,
    }

    VOLUME_DISCOUNTS = [
        (100_000_000, 8),   # 100M+ impressions
        (50_000_000, 5),    # 50M+ impressions
        (10_000_000, 3),    # 10M+ impressions
        (1_000_000, 1),     # 1M+ impressions
    ]

    @classmethod
    def calculate_price(
        cls,
        base_price: float,
        buyer_tier: str,
        volume: int = 0,
        deal_type: str = "open_auction"
    ) -> dict:
        """Calculate final price with all discounts."""
        tier_discount = cls.TIER_DISCOUNTS.get(buyer_tier.lower(), 0)

        volume_discount = 0
        for threshold, discount in cls.VOLUME_DISCOUNTS:
            if volume >= threshold:
                volume_discount = discount
                break

        # Deal type adjustments
        deal_adjustment = 0
        if deal_type == "preferred_deal":
            deal_adjustment = 2  # Slight premium for guaranteed access
        elif deal_type == "programmatic_guaranteed":
            deal_adjustment = 5  # Premium for guaranteed delivery

        total_discount = tier_discount + volume_discount - deal_adjustment
        final_price = base_price * (1 - total_discount / 100)

        return {
            "base_price": base_price,
            "tier": buyer_tier,
            "tier_discount": tier_discount,
            "volume_discount": volume_discount,
            "deal_adjustment": deal_adjustment,
            "total_discount": total_discount,
            "final_price": round(final_price, 2),
        }


# Global state
inventory = SellerInventory()
pricing_engine = TieredPricingEngine()

# =============================================================================
# MCP Tool Definitions
# =============================================================================

MCP_TOOLS = [
    {
        "name": "list_products",
        "description": "List all available advertising products/inventory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Filter by channel: ctv, display, mobile",
                    "enum": ["ctv", "display", "mobile"]
                }
            }
        }
    },
    {
        "name": "get_pricing",
        "description": "Get tiered pricing for a product based on buyer identity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
                "buyer_tier": {
                    "type": "string",
                    "description": "Buyer access tier",
                    "enum": ["public", "seat", "agency", "advertiser"]
                },
                "volume": {"type": "integer", "description": "Requested impression volume"},
                "deal_type": {
                    "type": "string",
                    "description": "Type of deal",
                    "enum": ["open_auction", "preferred_deal", "programmatic_guaranteed"]
                }
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "check_availability",
        "description": "Check if requested inventory is available for the specified dates",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
                "impressions": {"type": "integer", "description": "Requested impressions"},
                "start_date": {"type": "string", "description": "Flight start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Flight end date (YYYY-MM-DD)"}
            },
            "required": ["product_id", "impressions", "start_date", "end_date"]
        }
    },
    {
        "name": "create_deal",
        "description": "Create a Deal ID for DSP activation",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
                "deal_type": {
                    "type": "string",
                    "enum": ["preferred_deal", "programmatic_guaranteed"]
                },
                "price": {"type": "number", "description": "Negotiated CPM price"},
                "impressions": {"type": "integer", "description": "Guaranteed impressions"},
                "start_date": {"type": "string", "description": "Flight start date"},
                "end_date": {"type": "string", "description": "Flight end date"},
                "buyer_id": {"type": "string", "description": "Buyer identifier"},
                "advertiser_name": {"type": "string", "description": "Advertiser name"},
                "dsp_platform": {
                    "type": "string",
                    "description": "Target DSP",
                    "enum": ["amazon_dsp", "the_trade_desk", "dv360", "xandr"]
                }
            },
            "required": ["product_id", "deal_type", "price", "impressions"]
        }
    },
    {
        "name": "book_order",
        "description": "Book an OpenDirect order line",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "Deal ID to book"},
                "order_name": {"type": "string", "description": "Order name"},
                "buyer_id": {"type": "string", "description": "Buyer identifier"},
                "billing_contact": {"type": "string", "description": "Billing contact email"}
            },
            "required": ["deal_id", "order_name"]
        }
    }
]

# =============================================================================
# MCP Tool Handlers
# =============================================================================

def handle_list_products(args: dict) -> dict:
    """Handle list_products tool call."""
    channel_filter = args.get("channel")

    products = inventory.products
    if channel_filter:
        products = [p for p in products if p["channel"] == channel_filter]

    log_request("list_products", args, f"Returned {len(products)} products")

    return {
        "products": products,
        "total": len(products),
        "timestamp": datetime.now().isoformat()
    }


def handle_get_pricing(args: dict) -> dict:
    """Handle get_pricing tool call."""
    product_id = args.get("product_id")
    buyer_tier = args.get("buyer_tier", "public")
    volume = args.get("volume", 0)
    deal_type = args.get("deal_type", "open_auction")

    # Find product
    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    # Calculate pricing
    pricing = pricing_engine.calculate_price(
        base_price=product["base_price"],
        buyer_tier=buyer_tier,
        volume=volume,
        deal_type=deal_type
    )

    result = {
        "product_id": product_id,
        "product_name": product["name"],
        "pricing": pricing,
        "floor_price": product["floor_price"],
        "currency": "USD",
        "pricing_model": "CPM",
        "timestamp": datetime.now().isoformat()
    }

    log_request("get_pricing", args, f"Tier: {buyer_tier}, Price: ${pricing['final_price']}")

    return result


def handle_check_availability(args: dict) -> dict:
    """Handle check_availability tool call."""
    product_id = args.get("product_id")
    impressions = args.get("impressions", 0)
    start_date = args.get("start_date")
    end_date = args.get("end_date")

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    available = product["available_impressions"]
    is_available = impressions <= available

    result = {
        "product_id": product_id,
        "requested_impressions": impressions,
        "available_impressions": available,
        "is_available": is_available,
        "start_date": start_date,
        "end_date": end_date,
        "availability_percentage": min(100, round(available / max(impressions, 1) * 100, 1)),
        "timestamp": datetime.now().isoformat()
    }

    log_request("check_availability", args, f"Available: {is_available}")

    return result


def handle_create_deal(args: dict) -> dict:
    """Handle create_deal tool call."""
    product_id = args.get("product_id")
    deal_type = args.get("deal_type", "preferred_deal")
    price = args.get("price")
    impressions = args.get("impressions")
    start_date = args.get("start_date", "2026-03-01")
    end_date = args.get("end_date", "2026-06-30")
    buyer_id = args.get("buyer_id", "unknown")
    advertiser_name = args.get("advertiser_name", "Unknown Advertiser")
    dsp_platform = args.get("dsp_platform", "amazon_dsp")

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    # Check floor price
    if price < product["floor_price"]:
        return {
            "error": f"Price ${price} below floor ${product['floor_price']}",
            "floor_price": product["floor_price"],
            "suggested_price": product["floor_price"]
        }

    # Generate Deal ID
    deal_id = f"DEAL-{uuid.uuid4().hex[:8].upper()}"

    # DSP-specific activation instructions
    dsp_instructions = {
        "amazon_dsp": {
            "platform": "Amazon DSP",
            "activation_url": "https://advertising.amazon.com/dsp/deals",
            "steps": [
                "1. Navigate to Deals in Amazon DSP",
                "2. Click 'Add Deal'",
                f"3. Enter Deal ID: {deal_id}",
                "4. Select matching advertiser",
                "5. Apply to campaigns"
            ]
        },
        "the_trade_desk": {
            "platform": "The Trade Desk",
            "activation_url": "https://desk.thetradedesk.com",
            "steps": [
                "1. Go to Inventory > Private Contracts",
                f"2. Add new contract with Deal ID: {deal_id}",
                "3. Configure targeting to match deal terms",
                "4. Activate on campaigns"
            ]
        },
        "dv360": {
            "platform": "Display & Video 360",
            "activation_url": "https://displayvideo.google.com",
            "steps": [
                "1. Navigate to Inventory > My Inventory",
                f"2. Add Deal ID: {deal_id}",
                "3. Accept deal terms",
                "4. Apply to insertion orders"
            ]
        },
        "xandr": {
            "platform": "Xandr/Microsoft Invest",
            "activation_url": "https://invest.xandr.com",
            "steps": [
                "1. Go to Inventory > Deals",
                f"2. Enter Deal ID: {deal_id}",
                "3. Review and accept terms",
                "4. Target in line items"
            ]
        }
    }

    deal = {
        "deal_id": deal_id,
        "product_id": product_id,
        "product_name": product["name"],
        "deal_type": deal_type,
        "price": price,
        "pricing_model": "CPM",
        "impressions": impressions,
        "start_date": start_date,
        "end_date": end_date,
        "buyer_id": buyer_id,
        "advertiser_name": advertiser_name,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "openrtb_params": {
            "id": deal_id,
            "bidfloor": price,
            "bidfloorcur": "USD",
            "at": 1 if deal_type == "preferred_deal" else 3,
            "wseat": [buyer_id],
        },
        "activation": dsp_instructions.get(dsp_platform, dsp_instructions["amazon_dsp"])
    }

    inventory.deals[deal_id] = deal

    log_request("create_deal", args, f"Created {deal_id} at ${price} CPM")

    return deal


def handle_book_order(args: dict) -> dict:
    """Handle book_order tool call."""
    deal_id = args.get("deal_id")
    order_name = args.get("order_name", "Untitled Order")
    buyer_id = args.get("buyer_id", "unknown")
    billing_contact = args.get("billing_contact", "billing@example.com")

    # Find the deal
    deal = inventory.deals.get(deal_id)
    if not deal:
        return {"error": f"Deal {deal_id} not found"}

    # Create order
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    line_id = f"LINE-{uuid.uuid4().hex[:8].upper()}"

    order = {
        "order_id": order_id,
        "order_name": order_name,
        "line_id": line_id,
        "deal_id": deal_id,
        "product_id": deal["product_id"],
        "product_name": deal["product_name"],
        "buyer_id": buyer_id,
        "billing_contact": billing_contact,
        "status": "booked",
        "terms": {
            "price": deal["price"],
            "pricing_model": "CPM",
            "impressions": deal["impressions"],
            "start_date": deal["start_date"],
            "end_date": deal["end_date"],
            "total_cost": round(deal["price"] * deal["impressions"] / 1000, 2)
        },
        "created_at": datetime.now().isoformat(),
        "opendirect_version": "2.1",
    }

    inventory.orders[order_id] = order

    log_request("book_order", args, f"Booked {order_id} for {deal_id}")

    return order


TOOL_HANDLERS = {
    "list_products": handle_list_products,
    "get_pricing": handle_get_pricing,
    "check_availability": handle_check_availability,
    "create_deal": handle_create_deal,
    "book_order": handle_book_order,
}


def log_request(tool: str, args: dict, result_summary: str):
    """Log incoming requests for display."""
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "tool": tool,
        "args": args,
        "result": result_summary
    }
    inventory.request_log.append(entry)

    if RICH_AVAILABLE:
        console.print(f"[dim]{entry['timestamp']}[/dim] [cyan]{tool}[/cyan] → [green]{result_summary}[/green]")
    else:
        print(f"{entry['timestamp']} {tool} → {result_summary}")


# =============================================================================
# FastAPI Application (MCP over HTTP)
# =============================================================================

app = FastAPI(
    title="Seller Agent MCP Server",
    description="MCP server for advertising inventory",
    version="1.0.0"
)


@app.get("/")
async def root():
    """Server info."""
    return {
        "name": "Seller Agent MCP Server",
        "version": "1.0.0",
        "protocol": "MCP over HTTP",
        "endpoints": {
            "mcp": "/mcp",
            "tools": "/mcp/tools",
            "call": "/mcp/call"
        }
    }


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/mcp/tools")
async def list_tools():
    """List available MCP tools."""
    return {"tools": MCP_TOOLS}


@app.post("/mcp/call")
async def call_tool(request: Request):
    """Call an MCP tool."""
    try:
        body = await request.json()
        tool_name = body.get("name")
        arguments = body.get("arguments", {})

        if tool_name not in TOOL_HANDLERS:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

        handler = TOOL_HANDLERS[tool_name]
        result = handler(arguments)

        return {
            "success": True,
            "tool": tool_name,
            "result": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# SSE endpoint for MCP streaming (simplified for demo)
@app.get("/mcp/sse")
async def mcp_sse():
    """MCP SSE endpoint for streaming responses."""
    async def event_stream():
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'server': 'seller-agent'})}\n\n"

        # Keep connection alive
        while True:
            await asyncio.sleep(30)
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )


# =============================================================================
# Main
# =============================================================================

def print_banner():
    """Print server banner."""
    if RICH_AVAILABLE:
        banner = """
╔══════════════════════════════════════════════════════════════╗
║           SELLER AGENT MCP SERVER - IAB Tech Lab Demo        ║
╠══════════════════════════════════════════════════════════════╣
║  Protocol: MCP over HTTP                                     ║
║  Port: 8001                                                  ║
║  Endpoints:                                                  ║
║    • GET  /mcp/tools  - List available tools                 ║
║    • POST /mcp/call   - Call a tool                          ║
╠══════════════════════════════════════════════════════════════╣
║  Available Tools:                                            ║
║    • list_products     - Get inventory catalog               ║
║    • get_pricing       - Get tiered pricing                  ║
║    • check_availability - Check inventory                    ║
║    • create_deal       - Generate Deal IDs                   ║
║    • book_order        - Book OpenDirect orders              ║
╠══════════════════════════════════════════════════════════════╣
║  Waiting for buyer agent connections...                      ║
╚══════════════════════════════════════════════════════════════╝
"""
        console.print(Panel(banner.strip(), style="bold blue"))
    else:
        print("\n" + "=" * 60)
        print("SELLER AGENT MCP SERVER - IAB Tech Lab Demo")
        print("=" * 60)
        print("Port: 8001")
        print("Endpoints: /mcp/tools, /mcp/call")
        print("=" * 60 + "\n")


def main():
    """Run the seller MCP server."""
    print_banner()

    if RICH_AVAILABLE:
        console.print("\n[bold green]Starting server...[/bold green]\n")
        console.print("[dim]Incoming requests will be logged below:[/dim]\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="warning"  # Reduce uvicorn noise
    )


if __name__ == "__main__":
    main()
