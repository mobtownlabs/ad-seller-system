#!/usr/bin/env python3
"""Rivian R2 Campaign Demo - Seller Agent Side

This demo runs alongside the buyer agent demos to show the seller perspective.
It displays incoming requests from buyer agents, pricing calculations,
deal approvals, and OpenDirect bookings in real-time.

Run this in a separate terminal window while running the buyer demo
to see the full agent-to-agent interaction.

Usage:
    cd ad_seller_system/examples
    python rivian_seller_demo.py

The demo will:
1. Show the seller agent receiving buyer discovery requests
2. Display tiered pricing calculations based on buyer identity
3. Show Deal ID generation and approval
4. Display OpenDirect line bookings
5. Show the final execution status

Note: For the webinar, run this in one terminal and the buyer demo
in another to show the bidirectional communication.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
import hashlib
import random

# Rich console for beautiful output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Note: Install 'rich' for enhanced output: pip install rich")

# Import seller system components (graceful fallback)
try:
    from ad_seller.models.buyer_identity import BuyerContext, BuyerIdentity
    from ad_seller.engines.pricing_rules_engine import PricingRulesEngine
    from ad_seller.models.pricing_tiers import TieredPricingConfig, PricingTier
    SELLER_AVAILABLE = True
except ImportError:
    SELLER_AVAILABLE = False
    print("Note: ad_seller package not installed, using mock data")


console = Console() if RICH_AVAILABLE else None


def print_header(text: str, style: str = "bold green"):
    """Print a styled header."""
    if RICH_AVAILABLE:
        console.print(Panel(text, style=style))
    else:
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60)


def print_event(event_type: str, message: str):
    """Print an event with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if RICH_AVAILABLE:
        styles = {
            "INCOMING": "bold yellow",
            "PRICING": "bold cyan",
            "DEAL": "bold green",
            "BOOKING": "bold magenta",
            "APPROVED": "bold green",
            "INFO": "dim",
        }
        style = styles.get(event_type, "white")
        console.print(f"[dim]{timestamp}[/dim] [{style}][{event_type}][/{style}] {message}")
    else:
        print(f"[{timestamp}] [{event_type}] {message}")


def print_json(data: dict, title: str = ""):
    """Print formatted JSON."""
    if RICH_AVAILABLE:
        if title:
            console.print(f"[dim]{title}[/dim]")
        console.print_json(json.dumps(data, indent=2, default=str))
    else:
        if title:
            print(title)
        print(json.dumps(data, indent=2, default=str))


@dataclass
class SellerInventory:
    """Publisher inventory catalog."""
    publisher_id: str = "demo-publisher"
    publisher_name: str = "Premium Streaming Network"

    products: list = field(default_factory=list)

    def __post_init__(self):
        if not self.products:
            self.products = [
                {
                    "id": "ctv-hbomax-001",
                    "name": "HBO Max Premium CTV",
                    "channel": "ctv",
                    "base_price": 22.00,
                    "available_impressions": 50_000_000,
                    "targeting": ["household", "geo", "daypart"],
                },
                {
                    "id": "ctv-peacock-001",
                    "name": "Peacock Streaming CTV",
                    "channel": "ctv",
                    "base_price": 18.00,
                    "available_impressions": 75_000_000,
                    "targeting": ["household", "geo", "content"],
                },
                {
                    "id": "ctv-paramount-001",
                    "name": "Paramount+ Premium",
                    "channel": "ctv",
                    "base_price": 20.00,
                    "available_impressions": 40_000_000,
                    "targeting": ["household", "geo", "sports"],
                },
                {
                    "id": "ctv-hulu-001",
                    "name": "Hulu Streaming Network",
                    "channel": "ctv",
                    "base_price": 19.00,
                    "available_impressions": 60_000_000,
                    "targeting": ["household", "geo", "demo"],
                },
                {
                    "id": "video-premium-001",
                    "name": "Premium Video Network",
                    "channel": "video",
                    "base_price": 12.00,
                    "available_impressions": 100_000_000,
                    "targeting": ["demo", "interest", "retargeting"],
                },
                {
                    "id": "display-premium-001",
                    "name": "Premium Display Network",
                    "channel": "display",
                    "base_price": 5.00,
                    "available_impressions": 200_000_000,
                    "targeting": ["demo", "interest", "context"],
                },
                {
                    "id": "mobile-app-001",
                    "name": "Mobile App Network",
                    "channel": "mobile",
                    "base_price": 8.00,
                    "available_impressions": 150_000_000,
                    "targeting": ["device", "app", "interest"],
                },
            ]


@dataclass
class SellerState:
    """Current state of seller agent."""
    active_deals: list = field(default_factory=list)
    pending_requests: list = field(default_factory=list)
    booked_lines: list = field(default_factory=list)
    total_revenue: float = 0.0


def calculate_tiered_price(base_price: float, buyer_tier: str, volume: int = 0) -> dict:
    """Calculate tiered pricing based on buyer identity."""
    tier_discounts = {
        "public": 0.0,
        "seat": 5.0,
        "agency": 10.0,
        "advertiser": 15.0,
    }

    tier_discount = tier_discounts.get(buyer_tier, 0.0)
    tiered_price = base_price * (1 - tier_discount / 100)

    # Volume discount for agency/advertiser
    volume_discount = 0.0
    if buyer_tier in ("agency", "advertiser"):
        if volume >= 20_000_000:
            volume_discount = 15.0
        elif volume >= 10_000_000:
            volume_discount = 10.0
        elif volume >= 5_000_000:
            volume_discount = 5.0

    if volume_discount > 0:
        tiered_price = tiered_price * (1 - volume_discount / 100)

    return {
        "base_price": base_price,
        "tier": buyer_tier,
        "tier_discount": tier_discount,
        "volume_discount": volume_discount,
        "final_price": round(tiered_price, 2),
        "total_discount": round(tier_discount + volume_discount, 1),
    }


def generate_deal_id(product_id: str, buyer_info: str) -> str:
    """Generate a unique Deal ID."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    seed = f"{product_id}-{buyer_info}-{timestamp}"
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:8].upper()
    return f"DEAL-{hash_suffix}"


async def simulate_buyer_discovery_request(
    inventory: SellerInventory,
    state: SellerState
):
    """Simulate receiving a discovery request from buyer agent."""
    print_event("INCOMING", "Discovery request received from buyer agent")

    if RICH_AVAILABLE:
        request_data = {
            "type": "discovery",
            "buyer": {
                "agency": "Horizon Media",
                "advertiser": "Rivian Automotive",
                "tier": "advertiser",
            },
            "requirements": {
                "channel": "ctv",
                "reach_target": 5_000_000,
                "frequency": "3x/week",
                "publishers": ["HBO Max", "Peacock", "Paramount+", "Hulu"],
            },
        }
        console.print(Panel(
            json.dumps(request_data, indent=2),
            title="[bold yellow]Buyer Discovery Request[/bold yellow]",
            style="yellow"
        ))

    await asyncio.sleep(0.5)

    # Display available inventory
    print_event("INFO", "Searching available inventory...")

    if RICH_AVAILABLE:
        table = Table(title="Available CTV Inventory")
        table.add_column("Product ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Avail (M)", style="yellow")
        table.add_column("Base CPM", style="magenta")
        table.add_column("Targeting", style="dim")

        for p in inventory.products:
            if p["channel"] == "ctv":
                table.add_row(
                    p["id"],
                    p["name"],
                    f"{p['available_impressions'] / 1_000_000:.0f}M",
                    f"${p['base_price']:.2f}",
                    ", ".join(p["targeting"])
                )
        console.print(table)


async def simulate_pricing_request(
    inventory: SellerInventory,
    state: SellerState
):
    """Simulate receiving a pricing request with buyer identity."""
    print_event("INCOMING", "Pricing request received with buyer identity")

    buyer_info = {
        "agency_id": "horizon-media-001",
        "agency_name": "Horizon Media",
        "advertiser_id": "rivian-automotive-001",
        "advertiser_name": "Rivian Automotive",
        "tier": "advertiser",
    }

    if RICH_AVAILABLE:
        console.print(Panel(
            json.dumps(buyer_info, indent=2),
            title="[bold cyan]Buyer Identity[/bold cyan]",
            style="cyan"
        ))

    print_event("PRICING", "Calculating tiered pricing...")
    await asyncio.sleep(0.3)

    # Calculate pricing for each CTV product
    if RICH_AVAILABLE:
        table = Table(title="Tiered Pricing Results (Advertiser Tier)")
        table.add_column("Product", style="green")
        table.add_column("Base CPM", style="yellow")
        table.add_column("Tier Disc", style="cyan")
        table.add_column("Volume Disc", style="cyan")
        table.add_column("Final CPM", style="bold green")

        for p in inventory.products:
            if p["channel"] == "ctv":
                pricing = calculate_tiered_price(
                    p["base_price"],
                    "advertiser",
                    volume=15_000_000
                )
                table.add_row(
                    p["name"][:25],
                    f"${pricing['base_price']:.2f}",
                    f"-{pricing['tier_discount']:.0f}%",
                    f"-{pricing['volume_discount']:.0f}%",
                    f"${pricing['final_price']:.2f}"
                )
        console.print(table)

    print_event("INFO", "Tiered pricing applied: 15% advertiser discount + 10% volume discount")


async def simulate_deal_creation(
    inventory: SellerInventory,
    state: SellerState
):
    """Simulate creating Deal IDs for the buyer."""
    print_event("INCOMING", "Deal ID request received")

    deal_request = {
        "deal_type": "PD",
        "products": ["ctv-hbomax-001", "ctv-peacock-001", "ctv-paramount-001"],
        "impressions_each": 5_000_000,
        "flight_start": "2026-03-01",
        "flight_end": "2026-06-30",
    }

    if RICH_AVAILABLE:
        console.print(Panel(
            json.dumps(deal_request, indent=2),
            title="[bold green]Deal Request[/bold green]",
            style="green"
        ))

    await asyncio.sleep(0.5)

    # Create deals for each product
    deals = []
    for product_id in deal_request["products"]:
        product = next((p for p in inventory.products if p["id"] == product_id), None)
        if product:
            deal_id = generate_deal_id(product_id, "rivian")
            pricing = calculate_tiered_price(product["base_price"], "advertiser", 15_000_000)

            deal = {
                "deal_id": deal_id,
                "product_id": product_id,
                "product_name": product["name"],
                "deal_type": "PD",
                "price": pricing["final_price"],
                "impressions": 5_000_000,
                "status": "APPROVED",
            }
            deals.append(deal)
            state.active_deals.append(deal)

            print_event("DEAL", f"Created: {deal_id} for {product['name']}")

    await asyncio.sleep(0.3)

    # Display deal summary
    if RICH_AVAILABLE:
        table = Table(title="Generated Deal IDs")
        table.add_column("Deal ID", style="bold cyan")
        table.add_column("Product", style="green")
        table.add_column("CPM", style="yellow")
        table.add_column("Impressions", style="magenta")
        table.add_column("Status", style="bold green")

        for deal in deals:
            table.add_row(
                deal["deal_id"],
                deal["product_name"][:20],
                f"${deal['price']:.2f}",
                f"{deal['impressions']:,}",
                deal["status"]
            )
        console.print(table)

    # Show DSP activation instructions
    print_event("INFO", "Deal IDs ready for DSP activation")
    if RICH_AVAILABLE:
        for deal in deals[:1]:  # Show for first deal
            console.print("\n[bold]DSP Activation Instructions:[/bold]")
            console.print(f"  [cyan]Amazon DSP:[/cyan] Private Marketplace > Add Deal: {deal['deal_id']}")
            console.print(f"  [cyan]The Trade Desk:[/cyan] Inventory > PMP > Deal ID: {deal['deal_id']}")
            console.print(f"  [cyan]DV360:[/cyan] My Inventory > New > Deal ID: {deal['deal_id']}")

    return deals


async def simulate_opendirect_booking(
    inventory: SellerInventory,
    state: SellerState,
    deals: list
):
    """Simulate OpenDirect order and line item booking."""
    print_event("INCOMING", "OpenDirect booking request received")

    booking_request = {
        "type": "order",
        "account": "Rivian Automotive",
        "order_name": "Rivian R2 CTV Campaign Q1-Q2 2026",
        "budget": 3_500_000,
        "lines": len(deals),
    }

    if RICH_AVAILABLE:
        console.print(Panel(
            json.dumps(booking_request, indent=2),
            title="[bold magenta]OpenDirect Booking Request[/bold magenta]",
            style="magenta"
        ))

    await asyncio.sleep(0.5)

    # Create order
    order_id = f"ORD-RIVIAN-{datetime.now().strftime('%Y%m%d')}"
    print_event("BOOKING", f"Created Order: {order_id}")

    # Create line items
    lines = []
    for i, deal in enumerate(deals):
        line_id = f"LINE-{order_id}-{i+1:03d}"
        line = {
            "line_id": line_id,
            "order_id": order_id,
            "product_id": deal["product_id"],
            "product_name": deal["product_name"],
            "deal_id": deal["deal_id"],
            "impressions": deal["impressions"],
            "cpm": deal["price"],
            "budget": deal["impressions"] * deal["price"] / 1000,
            "status": "BOOKED",
        }
        lines.append(line)
        state.booked_lines.append(line)
        state.total_revenue += line["budget"]

        print_event("BOOKING", f"Line {line_id}: {deal['product_name']} - ${line['budget']:,.2f}")

    await asyncio.sleep(0.3)

    # Display booking summary
    if RICH_AVAILABLE:
        table = Table(title=f"OpenDirect Booking Summary - {order_id}")
        table.add_column("Line ID", style="cyan")
        table.add_column("Product", style="green")
        table.add_column("Deal ID", style="yellow")
        table.add_column("Budget", style="magenta")
        table.add_column("Status", style="bold green")

        for line in lines:
            table.add_row(
                line["line_id"],
                line["product_name"][:20],
                line["deal_id"],
                f"${line['budget']:,.2f}",
                line["status"]
            )
        console.print(table)

    return lines


async def simulate_adserver_sync(lines: list):
    """Simulate syncing to ad server (GAM/FreeWheel)."""
    print_event("INFO", "Syncing to ad server...")

    await asyncio.sleep(0.5)

    if RICH_AVAILABLE:
        console.print("\n[bold]Ad Server Sync Status:[/bold]")
        for line in lines:
            console.print(f"  [green]:white_check_mark:[/green] {line['product_name'][:25]}")
            console.print(f"      [dim]GAM Line Item: gam_{line['line_id']}[/dim]")
            console.print(f"      [dim]Deal ID synced: {line['deal_id']}[/dim]")

    print_event("APPROVED", "All lines synced to ad server - Ready for delivery")


async def run_seller_demo():
    """Run the complete seller agent demo."""
    print_header("SELLER AGENT DEMO - RIVIAN R2 CAMPAIGN", "bold blue")

    if RICH_AVAILABLE:
        console.print("\n[bold]Publisher:[/bold] Premium Streaming Network")
        console.print("[bold]Protocol:[/bold] IAB OpenDirect 2.1 + MCP/A2A")
        console.print("[dim]Waiting for buyer agent requests...[/dim]\n")
    else:
        print("\nPublisher: Premium Streaming Network")
        print("Protocol: IAB OpenDirect 2.1 + MCP/A2A")
        print("Waiting for buyer agent requests...\n")

    # Initialize seller state
    inventory = SellerInventory()
    state = SellerState()

    await asyncio.sleep(1)

    # Step 1: Receive discovery request
    print_header("STEP 1: INVENTORY DISCOVERY", "bold yellow")
    await simulate_buyer_discovery_request(inventory, state)

    await asyncio.sleep(1.5)

    # Step 2: Receive pricing request
    print_header("STEP 2: TIERED PRICING", "bold cyan")
    await simulate_pricing_request(inventory, state)

    await asyncio.sleep(1.5)

    # Step 3: Create Deal IDs
    print_header("STEP 3: DEAL ID GENERATION", "bold green")
    deals = await simulate_deal_creation(inventory, state)

    await asyncio.sleep(1.5)

    # Step 4: Book OpenDirect lines
    print_header("STEP 4: OPENDIRECT BOOKING", "bold magenta")
    lines = await simulate_opendirect_booking(inventory, state, deals)

    await asyncio.sleep(1)

    # Step 5: Sync to ad server
    print_header("STEP 5: AD SERVER SYNC", "bold blue")
    await simulate_adserver_sync(lines)

    await asyncio.sleep(0.5)

    # Final summary
    print_header("SELLER DEMO COMPLETE", "bold green")

    if RICH_AVAILABLE:
        console.print("\n[bold]Session Summary:[/bold]")
        console.print(f"  Deals Created: {len(state.active_deals)}")
        console.print(f"  Lines Booked: {len(state.booked_lines)}")
        console.print(f"  Total Revenue: ${state.total_revenue:,.2f}")
        console.print("\n[bold green]:white_check_mark: Campaign successfully booked![/bold green]")

        # Show JSON output
        console.print("\n[dim]OpenDirect JSON Response:[/dim]")
        output = {
            "order_id": lines[0]["order_id"] if lines else "N/A",
            "status": "BOOKED",
            "deals": [
                {
                    "deal_id": d["deal_id"],
                    "product": d["product_name"],
                    "price": d["price"],
                }
                for d in state.active_deals
            ],
            "lines": [
                {
                    "line_id": l["line_id"],
                    "deal_id": l["deal_id"],
                    "budget": l["budget"],
                    "status": l["status"],
                }
                for l in state.booked_lines
            ],
            "total_budget": state.total_revenue,
        }
        console.print_json(json.dumps(output, indent=2))
    else:
        print(f"\nSession Summary:")
        print(f"  Deals Created: {len(state.active_deals)}")
        print(f"  Lines Booked: {len(state.booked_lines)}")
        print(f"  Total Revenue: ${state.total_revenue:,.2f}")


def main():
    """Main entry point."""
    print("""
Seller Agent Demo - Rivian R2 Campaign
======================================

This demo simulates the seller agent side of the Rivian R2 campaign.
Run this alongside the buyer demo to see the full agent-to-agent interaction.

The demo will show:
  1. Receiving buyer discovery requests
  2. Calculating tiered pricing
  3. Generating Deal IDs
  4. Booking OpenDirect lines
  5. Syncing to ad server

Press Enter to start the demo...
""")
    input()
    asyncio.run(run_seller_demo())


if __name__ == "__main__":
    main()
