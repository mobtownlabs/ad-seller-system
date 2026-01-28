#!/usr/bin/env python3
# Author: Green Mountain Systems AI Inc.
# Donated to IAB Tech Lab

"""DSP Seller Agent - MCP Server

This represents a demand-side platform that:
1. Receives Deal IDs from buyers (PMP deals from publishers)
2. Activates deals on campaigns
3. Books Performance and Mobile App campaigns directly

The buyer agent can:
- Attach publisher Deal IDs to campaigns
- Book Performance display campaigns
- Book Mobile App install campaigns

Usage:
    cd ad_seller_system/examples
    python dsp_server.py

Runs on port 8002
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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

console = Console() if RICH_AVAILABLE else None

# =============================================================================
# DSP Inventory (Performance & Mobile focused)
# =============================================================================

class DSPInventory:
    """DSP inventory and campaign management."""

    def __init__(self):
        self.dsp_name = "DSP"
        self.dsp_id = "generic-dsp"

        # Performance Display Products
        self.products = [
            {
                "id": "perf-display-001",
                "name": "Performance Display - ComScore Top 200",
                "channel": "display",
                "type": "performance",
                "base_cpm": 8.00,
                "floor_cpm": 4.00,
                "available_impressions": 500_000_000,
                "targeting_options": ["behavioral", "contextual", "retargeting", "lookalike"],
                "ad_formats": ["300x250", "728x90", "160x600", "320x50"],
                "optimization_goals": ["conversions", "clicks", "viewability"],
            },
            {
                "id": "perf-display-002",
                "name": "Performance Display - Premium Properties",
                "channel": "display",
                "type": "performance",
                "base_cpm": 12.00,
                "floor_cpm": 8.00,
                "available_impressions": 200_000_000,
                "targeting_options": ["purchase_intent", "in_market", "retargeting"],
                "ad_formats": ["300x250", "728x90", "970x250"],
                "optimization_goals": ["conversions", "roas", "sales"],
            },
            {
                "id": "mobile-app-001",
                "name": "Mobile App Install - Premium Network",
                "channel": "mobile",
                "type": "app_install",
                "base_cpi": 3.50,  # Cost per install
                "floor_cpi": 2.00,
                "available_installs": 5_000_000,
                "targeting_options": ["device", "behavioral", "lookalike", "geo"],
                "ad_formats": ["interstitial", "rewarded", "native", "banner"],
                "optimization_goals": ["installs", "post_install_events", "retention"],
            },
            {
                "id": "mobile-app-002",
                "name": "Mobile App Engagement - Deep Link",
                "channel": "mobile",
                "type": "app_engagement",
                "base_cpm": 6.00,
                "floor_cpm": 3.00,
                "available_impressions": 100_000_000,
                "targeting_options": ["app_users", "lapsed_users", "high_value"],
                "ad_formats": ["native", "interstitial"],
                "optimization_goals": ["app_opens", "in_app_events", "purchases"],
            },
        ]

        # Track campaigns and attached deals
        self.campaigns = {}
        self.attached_deals = {}  # Deal IDs from publishers
        self.request_log = []


class DSPPricingEngine:
    """Calculate DSP campaign pricing."""

    TIER_DISCOUNTS = {
        "public": 0,
        "seat": 3,
        "agency": 7,
        "advertiser": 12,
    }

    @classmethod
    def calculate_price(cls, base_price: float, buyer_tier: str, volume: int) -> dict:
        tier_discount = cls.TIER_DISCOUNTS.get(buyer_tier.lower(), 0)

        # Volume discounts for DSP
        volume_discount = 0
        if volume >= 100_000_000:
            volume_discount = 10
        elif volume >= 50_000_000:
            volume_discount = 7
        elif volume >= 10_000_000:
            volume_discount = 4

        total_discount = tier_discount + volume_discount
        final_price = base_price * (1 - total_discount / 100)

        return {
            "base_price": base_price,
            "tier_discount": tier_discount,
            "volume_discount": volume_discount,
            "total_discount": total_discount,
            "final_price": round(final_price, 2),
        }


# Global state
inventory = DSPInventory()
pricing_engine = DSPPricingEngine()

# =============================================================================
# MCP Tool Definitions
# =============================================================================

MCP_TOOLS = [
    {
        "name": "list_products",
        "description": "List available DSP products (Performance Display, Mobile App)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["display", "mobile"]
                }
            }
        }
    },
    {
        "name": "get_pricing",
        "description": "Get pricing for a DSP product",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "buyer_tier": {"type": "string"},
                "volume": {"type": "integer"}
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "attach_deal",
        "description": "Attach a publisher Deal ID (from PMP) to a DSP campaign",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "Deal ID from publisher"},
                "campaign_id": {"type": "string", "description": "DSP campaign to attach to (optional, creates new if not provided)"},
                "campaign_name": {"type": "string"},
                "advertiser_name": {"type": "string"},
                "budget": {"type": "number"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"}
            },
            "required": ["deal_id", "advertiser_name"]
        }
    },
    {
        "name": "create_performance_campaign",
        "description": "Create a Performance Display campaign in DSP",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "campaign_name": {"type": "string"},
                "advertiser_name": {"type": "string"},
                "budget": {"type": "number"},
                "impressions": {"type": "integer"},
                "optimization_goal": {
                    "type": "string",
                    "enum": ["conversions", "clicks", "viewability", "roas"]
                },
                "targeting": {"type": "object"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"}
            },
            "required": ["product_id", "campaign_name", "advertiser_name", "budget"]
        }
    },
    {
        "name": "create_mobile_campaign",
        "description": "Create a Mobile App Install or Engagement campaign",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "campaign_name": {"type": "string"},
                "advertiser_name": {"type": "string"},
                "app_id": {"type": "string", "description": "App Store or Play Store ID"},
                "budget": {"type": "number"},
                "target_installs": {"type": "integer"},
                "optimization_goal": {
                    "type": "string",
                    "enum": ["installs", "post_install_events", "retention"]
                },
                "deep_link_url": {"type": "string"},
                "targeting": {"type": "object"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"}
            },
            "required": ["product_id", "campaign_name", "advertiser_name", "budget"]
        }
    },
    {
        "name": "get_campaign_status",
        "description": "Get status of a DSP campaign",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"}
            },
            "required": ["campaign_id"]
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
        color = "cyan" if source == "MCP" else "yellow" if source == "DSP" else "green"
        console.print(f"[dim]{timestamp}[/dim] [{color}]{source}[/{color}] → {message}")
    else:
        print(f"{timestamp} [{source}] {message}")


# =============================================================================
# MCP Tool Handlers
# =============================================================================

def handle_list_products(args: dict) -> dict:
    """Handle list_products tool call."""
    channel = args.get("channel")

    products = inventory.products
    if channel:
        products = [p for p in products if p["channel"] == channel]

    log_event("MCP", f"list_products → {len(products)} products")

    return {
        "dsp": inventory.dsp_name,
        "products": products,
        "total": len(products),
    }


def handle_get_pricing(args: dict) -> dict:
    """Handle get_pricing tool call."""
    product_id = args.get("product_id")
    buyer_tier = args.get("buyer_tier", "public")
    volume = args.get("volume", 0)

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    # Get base price (CPM or CPI depending on product)
    base_price = product.get("base_cpm", product.get("base_cpi", 0))

    pricing = pricing_engine.calculate_price(base_price, buyer_tier, volume)

    log_event("MCP", f"get_pricing → {product_id}: ${pricing['final_price']}")

    return {
        "product_id": product_id,
        "product_name": product["name"],
        "pricing_model": "CPI" if "cpi" in str(product.keys()) else "CPM",
        "pricing": pricing,
    }


def handle_attach_deal(args: dict) -> dict:
    """Attach a publisher Deal ID to a DSP campaign."""
    deal_id = args.get("deal_id")
    campaign_id = args.get("campaign_id")
    campaign_name = args.get("campaign_name", f"PMP Campaign - {deal_id}")
    advertiser_name = args.get("advertiser_name")
    budget = args.get("budget", 0)
    start_date = args.get("start_date", "2026-03-01")
    end_date = args.get("end_date", "2026-06-30")

    # Create campaign if not provided
    if not campaign_id:
        campaign_id = f"DSP-CAMP-{uuid.uuid4().hex[:8].upper()}"

        campaign = {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "advertiser_name": advertiser_name,
            "campaign_type": "pmp_deal",
            "budget": budget,
            "start_date": start_date,
            "end_date": end_date,
            "status": "ACTIVE",
            "attached_deals": [deal_id],
            "created_at": datetime.now().isoformat(),
        }
        inventory.campaigns[campaign_id] = campaign
        log_event("DSP", f"Created Campaign: {campaign_id}")

    # Attach deal
    inventory.attached_deals[deal_id] = {
        "deal_id": deal_id,
        "campaign_id": campaign_id,
        "status": "ACTIVE",
        "attached_at": datetime.now().isoformat(),
    }

    log_event("DSP", f"Attached Deal: {deal_id} → Campaign {campaign_id}")

    return {
        "status": "deal_attached",
        "deal_id": deal_id,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "message": f"Deal {deal_id} is now active on campaign {campaign_id}. Bidding will begin at campaign start date.",
    }


def handle_create_performance_campaign(args: dict) -> dict:
    """Create a Performance Display campaign."""
    product_id = args.get("product_id")
    campaign_name = args.get("campaign_name")
    advertiser_name = args.get("advertiser_name")
    budget = args.get("budget")
    impressions = args.get("impressions", 0)
    optimization_goal = args.get("optimization_goal", "conversions")
    targeting = args.get("targeting", {})
    start_date = args.get("start_date", "2026-03-01")
    end_date = args.get("end_date", "2026-06-30")

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    campaign_id = f"DSP-PERF-{uuid.uuid4().hex[:8].upper()}"
    line_id = f"DSP-LINE-{uuid.uuid4().hex[:8].upper()}"

    campaign = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "advertiser_name": advertiser_name,
        "campaign_type": "performance_display",
        "product_id": product_id,
        "product_name": product["name"],
        "budget": budget,
        "impressions_target": impressions,
        "optimization_goal": optimization_goal,
        "targeting": targeting,
        "start_date": start_date,
        "end_date": end_date,
        "status": "ACTIVE",
        "line_items": [
            {
                "line_id": line_id,
                "line_name": f"{product['name']} - Line 1",
                "budget": budget,
                "status": "ACTIVE",
            }
        ],
        "created_at": datetime.now().isoformat(),
    }

    inventory.campaigns[campaign_id] = campaign
    log_event("DSP", f"Created Performance Campaign: {campaign_id} (${budget:,.2f} budget)")

    return {
        "status": "campaign_created",
        "campaign": campaign,
        "message": f"Performance campaign created and active. Optimization goal: {optimization_goal}",
    }


def handle_create_mobile_campaign(args: dict) -> dict:
    """Create a Mobile App campaign."""
    product_id = args.get("product_id")
    campaign_name = args.get("campaign_name")
    advertiser_name = args.get("advertiser_name")
    app_id = args.get("app_id", "com.rivian.app")
    budget = args.get("budget")
    target_installs = args.get("target_installs", 0)
    optimization_goal = args.get("optimization_goal", "installs")
    deep_link_url = args.get("deep_link_url", "")
    targeting = args.get("targeting", {})
    start_date = args.get("start_date", "2026-03-01")
    end_date = args.get("end_date", "2026-06-30")

    product = next((p for p in inventory.products if p["id"] == product_id), None)
    if not product:
        return {"error": f"Product {product_id} not found"}

    campaign_id = f"DSP-MOBILE-{uuid.uuid4().hex[:8].upper()}"

    campaign = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "advertiser_name": advertiser_name,
        "campaign_type": "mobile_app",
        "product_id": product_id,
        "product_name": product["name"],
        "app_id": app_id,
        "budget": budget,
        "target_installs": target_installs,
        "estimated_cpi": round(budget / max(target_installs, 1), 2) if target_installs else None,
        "optimization_goal": optimization_goal,
        "deep_link_url": deep_link_url,
        "targeting": targeting,
        "start_date": start_date,
        "end_date": end_date,
        "status": "ACTIVE",
        "created_at": datetime.now().isoformat(),
    }

    inventory.campaigns[campaign_id] = campaign
    log_event("DSP", f"Created Mobile Campaign: {campaign_id} ({target_installs:,} target installs)")

    return {
        "status": "campaign_created",
        "campaign": campaign,
        "message": f"Mobile app campaign created. Target: {target_installs:,} installs at ~${campaign.get('estimated_cpi', 'N/A')} CPI",
    }


def handle_get_campaign_status(args: dict) -> dict:
    """Get campaign status."""
    campaign_id = args.get("campaign_id")

    campaign = inventory.campaigns.get(campaign_id)
    if not campaign:
        return {"error": f"Campaign {campaign_id} not found"}

    return {
        "campaign": campaign,
        "attached_deals": [
            d for d in inventory.attached_deals.values()
            if d.get("campaign_id") == campaign_id
        ]
    }


TOOL_HANDLERS = {
    "list_products": handle_list_products,
    "get_pricing": handle_get_pricing,
    "attach_deal": handle_attach_deal,
    "create_performance_campaign": handle_create_performance_campaign,
    "create_mobile_campaign": handle_create_mobile_campaign,
    "get_campaign_status": handle_get_campaign_status,
}

# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="DSP Seller Agent",
    description="DSP for Performance and Mobile campaigns",
    version="1.0.0"
)


@app.get("/")
async def root():
    return {
        "name": "DSP Seller Agent",
        "dsp": inventory.dsp_name,
        "port": 8002,
        "capabilities": ["deal_attachment", "performance_display", "mobile_app"]
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
║              DSP SELLER AGENT                         ║
╠══════════════════════════════════════════════════════════════╣
║  Platform: Demand-Side Platform                       ║
║  Port: 8002                                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Capabilities:                                               ║
║    • Attach publisher Deal IDs (PMP)                         ║
║    • Performance Display campaigns                           ║
║    • Mobile App Install/Engagement campaigns                 ║
╠══════════════════════════════════════════════════════════════╣
║  MCP Tools:                                                  ║
║    • list_products                                           ║
║    • get_pricing                                             ║
║    • attach_deal           → Attach PMP Deal ID              ║
║    • create_performance_campaign                             ║
║    • create_mobile_campaign                                  ║
║    • get_campaign_status                                     ║
╠══════════════════════════════════════════════════════════════╣
║  Waiting for buyer agent connections...                      ║
╚══════════════════════════════════════════════════════════════╝
"""
        console.print(Panel(banner.strip(), style="bold yellow"))
    else:
        print("\n" + "=" * 60)
        print("DSP SELLER AGENT")
        print("=" * 60)
        print("Port: 8002")
        print("=" * 60 + "\n")


def main():
    """Run the DSP MCP server."""
    print_banner()

    if RICH_AVAILABLE:
        console.print("\n[bold green]Starting server...[/bold green]\n")
        console.print("[dim]Activity log:[/dim]\n")

    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="warning")


if __name__ == "__main__":
    main()
