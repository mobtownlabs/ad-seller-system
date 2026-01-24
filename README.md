# Ad Seller System

An AI-powered inventory management system for **publishers and SSPs** to automate programmatic direct sales using IAB OpenDirect standards.

## What This Does

The Ad Seller System lets you:

- **Automate deal negotiations** with AI agents that understand your inventory and pricing rules
- **Offer tiered pricing** based on buyer identity (public, agency, advertiser)
- **Generate Deal IDs** compatible with any DSP (The Trade Desk, Amazon, DV360, etc.)
- **Validate audience targeting** using IAB User Context Protocol (UCP) for embedding-based matching
- **Connect to IAB OpenDirect servers** for standardized programmatic direct workflows
- **Expose your inventory** via REST API, CLI, or conversational chat interface

## Who Should Use This

- **Publishers** (news sites, streaming services, apps) who want to automate direct sales
- **SSPs** selling curated inventory packages to agencies
- **Ad ops teams** looking to reduce manual deal setup
- **Anyone** wanting to experiment with agentic advertising workflows

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AD SELLER SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║                 LEVEL 1: ORCHESTRATION (Claude Opus)                  ║  │
│  ║  ┌─────────────────────────────────────────────────────────────────┐  ║  │
│  ║  │                    Inventory Manager                            │  ║  │
│  ║  │   • Yield optimization          • Deal acceptance decisions     │  ║  │
│  ║  │   • Portfolio strategy          • Cross-sell opportunities      │  ║  │
│  ║  └─────────────────────────────────────────────────────────────────┘  ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                    │                                        │
│                                    ▼                                        │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║             LEVEL 2: CHANNEL SPECIALISTS (Claude Sonnet)              ║  │
│  ║  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         ║  │
│  ║  │ Display │ │  Video  │ │   CTV   │ │ Mobile  │ │ Native  │         ║  │
│  ║  │Inventory│ │Inventory│ │Inventory│ │   App   │ │Inventory│         ║  │
│  ║  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘         ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                    │                                        │
│                                    ▼                                        │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║              LEVEL 3: FUNCTIONAL AGENTS (Claude Sonnet)               ║  │
│  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    ║  │
│  ║  │ Pricing  │ │  Avails  │ │ Proposal │ │  Upsell  │ │ Audience │    ║  │
│  ║  │  Agent   │ │  Agent   │ │  Review  │ │  Agent   │ │ Validator│    ║  │
│  ║  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘    ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  TOOLS                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Pricing: PriceCalculator, FloorManager, DiscountEngine                 │ │
│  │ Inventory: AvailsChecker, CapacityForecaster, AllocationManager        │ │
│  │ Deals: ProposalGenerator, CounterOfferBuilder, DealIDGenerator         │ │
│  │ Audience: AudienceValidation, AudienceCapability, CoverageCalculator   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────┤
│  INTERFACES: CLI │ REST API │ Chat                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  STORAGE: SQLite (dev) │ Redis (prod)                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  PROTOCOLS                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │ MCP (33 OpenDirect   │  │ A2A (Natural Language│  │ UCP (Audience    │  │
│  │      Tools)          │  │      Queries)        │  │    Embeddings)   │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│  SERVER: IAB Tech Lab agentic-direct (OpenDirect 2.1)                       │
│  https://agentic-direct-server-hwgrypmndq-uk.a.run.app                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Hierarchy

| Level | Agent | Model | Temperature | Role |
|-------|-------|-------|-------------|------|
| **1** | Inventory Manager | Claude Opus | 0.3 | Strategic orchestration, yield optimization, portfolio management |
| **2** | Display Inventory Specialist | Claude Sonnet | 0.5 | Display ad inventory (IAB units, rich media, viewability) |
| **2** | Video Inventory Specialist | Claude Sonnet | 0.5 | Video inventory (pre-roll, mid-roll, outstream, CPCV) |
| **2** | CTV Inventory Specialist | Claude Sonnet | 0.5 | CTV inventory (streaming, FAST, household targeting) |
| **2** | Mobile App Specialist | Claude Sonnet | 0.5 | Mobile app inventory (rewarded video, interstitials, ATT) |
| **2** | Native Inventory Specialist | Claude Sonnet | 0.5 | Native content (in-feed, widgets, sponsored content) |
| **3** | Pricing Agent | Claude Sonnet | 0.2 | Pricing calculations, floor management, discount application |
| **3** | Availability Agent | Claude Sonnet | 0.2 | Inventory forecasting, capacity planning, delivery confidence |
| **3** | Proposal Review Agent | Claude Sonnet | 0.3 | Proposal evaluation, counter-offer generation, acceptance decisions |
| **3** | Upsell Agent | Claude Sonnet | 0.3 | Cross-sell identification, volume upgrades, alternative recommendations |
| **3** | Audience Validator | Claude Sonnet | 0.2 | UCP-based audience validation, coverage estimation, gap analysis |

---

## UCP: User Context Protocol

The Ad Seller System implements IAB Tech Lab's **User Context Protocol (UCP)** for privacy-preserving audience validation between buyers and sellers.

### What UCP Does

UCP enables real-time audience matching by exchanging embeddings (256-1024 dimension vectors) that encode:

- **Identity Signals** - Hashed user IDs, device graphs
- **Contextual Signals** - Page content, keywords, categories
- **Reinforcement Signals** - Conversion data, feedback loops

### Audience Validator Agent

The **Audience Validator Agent** (Level 3) uses UCP to:

1. **Validate Buyer Requests** - Check if requested audience targeting can be fulfilled
2. **Estimate Coverage** - Calculate what percentage of inventory matches the audience
3. **Identify Gaps** - Find audience capabilities the seller cannot support
4. **Suggest Alternatives** - Recommend similar audiences when exact match unavailable
5. **Compute Similarity** - Use UCP embeddings to score audience alignment

### Audience Tools

| Tool | Purpose |
|------|---------|
| `AudienceValidationTool` | Validate buyer audience requests against product capabilities |
| `AudienceCapabilityTool` | Report available audience capabilities for products |
| `CoverageCalculatorTool` | Calculate coverage percentage for targeting combinations |

### Audience Validation Flow

```
Buyer Proposal → Audience Validator Agent → UCP Validation → Coverage Estimate → Proposal Decision
                        │
                        ├─ Validate against product capabilities
                        ├─ Compute UCP similarity score
                        ├─ Calculate coverage percentage
                        └─ Identify gaps and alternatives
```

### Example: Audience Validation in Proposal Review

```python
from ad_seller.tools.audience import (
    AudienceValidationTool,
    AudienceCapabilityTool,
    CoverageCalculatorTool,
)

# Validate a buyer's audience request
validation_tool = AudienceValidationTool()
result = validation_tool._run(
    buyer_audience={
        "demographics": {"age": "25-54", "income": "high"},
        "interests": ["technology", "business"],
        "behaviors": ["in-market-auto"]
    },
    product_id="ctv-premium"
)

# Result includes:
# - validation_status: "valid" | "partial_match" | "no_match"
# - coverage_percentage: 0-100
# - ucp_similarity_score: 0.0-1.0
# - gaps: ["in-market-auto not available"]
# - alternatives: ["in-market-luxury-goods"]
```

### UCP Technical Details

| Property | Value |
|----------|-------|
| **Content-Type** | `application/vnd.ucp.embedding+json; v=1` |
| **Embedding Dimensions** | 256-1024 |
| **Similarity Metric** | Cosine (default), Dot Product, L2 |
| **Consent Required** | Yes (IAB TCF v2) |

---

## Installation

### Prerequisites

- Python 3.11 or higher
- An [Anthropic API key](https://console.anthropic.com/) for Claude

### Step 1: Clone and Install

```bash
git clone https://github.com/mobtownlabs/ad_seller_system.git
cd ad_seller_system

# Install the package
pip install -e .

# Or with Redis support (for production)
pip install -e ".[redis]"

# Or with dev tools (for testing)
pip install -e ".[dev]"
```

### Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required: Your Anthropic API key
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# Your publisher identity
SELLER_ORGANIZATION_ID=my-publisher
SELLER_ORGANIZATION_NAME=My Publishing Company

# OpenDirect server (default: live IAB Tech Lab server)
OPENDIRECT_BASE_URL=https://agentic-direct-server-hwgrypmndq-uk.a.run.app
DEFAULT_PROTOCOL=opendirect21

# Storage: sqlite (default) or redis
STORAGE_TYPE=sqlite
DATABASE_URL=sqlite:///./ad_seller.db

# For Redis (production deployments)
# STORAGE_TYPE=redis
# REDIS_URL=redis://localhost:6379/0
```

### Step 3: Verify Installation

```bash
# Test the CLI
ad-seller --help

# Test connection to OpenDirect server
ad-seller connect
```

---

## Quick Start Examples

### Example 1: Calculate Tiered Pricing

```python
from ad_seller.models.buyer_identity import BuyerIdentity, BuyerContext
from ad_seller.models.pricing_tiers import TieredPricingConfig
from ad_seller.engines.pricing_rules_engine import PricingRulesEngine

# Setup your pricing config
config = TieredPricingConfig(seller_organization_id="my-publisher")
engine = PricingRulesEngine(config=config)

# Public buyer (unauthenticated) - sees price ranges
public_buyer = BuyerContext(
    identity=BuyerIdentity(),
    is_authenticated=False
)
display = engine.get_price_display(base_price=20.0, buyer_context=public_buyer)
print(display)
# Output: {'type': 'range', 'low': 16.0, 'high': 24.0, 'currency': 'USD', 'display': '$16-$24 CPM'}

# Agency buyer - sees exact price with 10% discount
agency_buyer = BuyerContext(
    identity=BuyerIdentity(agency_id="omnicom-123", agency_name="Omnicom"),
    is_authenticated=True
)
display = engine.get_price_display(base_price=20.0, buyer_context=agency_buyer)
print(display)
# Output: {'type': 'exact', 'price': 18.0, 'currency': 'USD', 'negotiation_enabled': True}

# Advertiser buyer - best price with 15% discount
advertiser_buyer = BuyerContext(
    identity=BuyerIdentity(
        agency_id="omnicom-123",
        agency_name="Omnicom",
        advertiser_id="coca-cola",
        advertiser_name="Coca-Cola"
    ),
    is_authenticated=True
)
result = engine.calculate_price(
    product_id="ctv-premium",
    base_price=20.0,
    buyer_context=advertiser_buyer,
    volume=10_000_000  # 10M impressions
)
print(f"Final price: ${result.final_price} CPM")
print(f"Savings: {(1 - result.final_price/20) * 100:.1f}%")
# Output: Final price: $15.3 CPM
# Output: Savings: 23.5%
```

### Example 2: Connect to OpenDirect Server

```python
import asyncio
from ad_seller.clients import UnifiedClient, Protocol

async def main():
    async with UnifiedClient(
        base_url="https://agentic-direct-server-hwgrypmndq-uk.a.run.app",
        protocol=Protocol.OPENDIRECT_21,
    ) as client:
        # List available products
        result = await client.list_products()
        if result.success:
            for product in result.data[:5]:
                print(f"- {product.get('name')}")

        # Create your seller organization
        result = await client.create_organization(
            name="My Publisher",
            role="seller",
        )
        print(f"Created: {result.data}")

asyncio.run(main())
```

### Example 3: Store and Retrieve Data

```python
import asyncio
from ad_seller.storage import get_storage_backend

async def main():
    # Creates SQLite backend by default (or Redis if configured)
    storage = get_storage_backend()
    await storage.connect()

    # Store a product
    await storage.set_product("ctv-premium", {
        "name": "CTV Premium Package",
        "inventory_type": "ctv",
        "base_cpm": 35.0,
        "floor_cpm": 28.0,
    })

    # Retrieve it
    product = await storage.get_product("ctv-premium")
    print(product)
    # Output: {'name': 'CTV Premium Package', 'inventory_type': 'ctv', 'base_cpm': 35.0, 'floor_cpm': 28.0}

    # List all products
    products = await storage.list_products()
    print(f"Total products: {len(products)}")

    await storage.disconnect()

asyncio.run(main())
```

### Example 4: Validate Audience with UCP

```python
import asyncio
from ad_seller.clients import UCPClient, UCPExchangeResult

async def main():
    client = UCPClient()

    # Validate a buyer's audience request against your capabilities
    result = await client.validate_buyer_audience(
        buyer_embedding={
            "embedding_type": "user_intent",
            "vector": [...],  # 256-1024 dimension vector
            "dimension": 512,
        },
        product_id="ctv-premium"
    )

    print(f"Similarity score: {result.similarity_score}")
    print(f"Recommendation: {result.recommendation}")
    # Output: Similarity score: 0.87
    # Output: Recommendation: accept

asyncio.run(main())
```

---

## Tiered Pricing System

The system supports identity-based pricing tiers:

| Tier | Who | What They See | Discount | Features |
|------|-----|---------------|----------|----------|
| **Public** | Unauthenticated visitors | Price ranges ($18-25 CPM) | 0% | General catalog only |
| **Seat** | Authenticated DSP seat | Fixed prices | 5% | Standard deals |
| **Agency** | Agency with ID | Fixed prices | 10% | Premium inventory, negotiation |
| **Advertiser** | Advertiser with ID | Best prices | 15% | Volume discounts, full negotiation |

### Volume Discounts (for Agency/Advertiser tiers)

| Impressions | Additional Discount |
|-------------|---------------------|
| 5M+ | 5% |
| 10M+ | 10% |
| 20M+ | 15% |
| 50M+ | 20% |

### Example Pricing Calculation

```
Base Price:      $20.00 CPM
Advertiser Tier: -15%  → $17.00
Volume (10M):    -10%  → $15.30
─────────────────────────────────
Final Price:     $15.30 CPM (23.5% total savings)
```

---

## Protocol Options

The system supports multiple protocols for communicating with OpenDirect servers:

| Protocol | Best For | Speed | Flexibility |
|----------|----------|-------|-------------|
| **MCP** | Structured operations (create, update, list) | Fast | Deterministic, 33 tools |
| **A2A** | Natural language queries and discovery | Moderate | Flexible, conversational |
| **UCP** | Audience embedding exchange | Fast | Privacy-preserving matching |

### When to Use Each

- **MCP**: Managing products, processing orders, automated deal workflows
- **A2A**: Responding to buyer queries, recommendations, negotiation conversations
- **UCP**: Audience validation, coverage estimation, capability reporting

---

## Available MCP Tools

The IAB Tech Lab server provides 33 OpenDirect tools that both buyers and sellers use:

| Category | Tools |
|----------|-------|
| **Accounts** | `create_account`, `update_account`, `get_account`, `list_accounts` |
| **Orders** | `create_order`, `update_order`, `get_order`, `list_orders` |
| **Lines** | `create_line`, `update_line`, `get_line`, `list_lines` |
| **Products** | `get_product`, `list_products`, `search_products` |
| **Creatives** | `create_creative`, `update_creative`, `get_creative`, `list_creatives` |
| **Assignments** | `create_assignment`, `delete_assignment`, `get_assignment`, `list_assignments` |
| **Organizations** | `create_organization`, `update_organization`, `get_organization`, `list_organizations` |
| **Change Requests** | `create_changerequest`, `get_changerequest`, `list_changerequests` |
| **Messages** | `create_message`, `get_message`, `list_messages` |

---

## REST API

Start the API server:

```bash
uvicorn ad_seller.interfaces.api.main:app --reload --port 8000
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products` | List all products in catalog |
| `GET` | `/products/{id}` | Get product details |
| `POST` | `/pricing` | Calculate price for a buyer |
| `POST` | `/proposals` | Submit a proposal |
| `POST` | `/deals` | Generate a Deal ID |
| `POST` | `/discovery` | Natural language query |
| `POST` | `/audience/validate` | Validate audience targeting (UCP) |

### Example: Get Pricing via API

```bash
curl -X POST http://localhost:8000/pricing \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "ctv-premium",
    "base_price": 35.0,
    "buyer": {
      "agency_id": "agency-123",
      "advertiser_id": "coca-cola"
    },
    "volume": 5000000
  }'
```

Response:
```json
{
  "product_id": "ctv-premium",
  "base_price": 35.0,
  "final_price": 28.26,
  "tier": "advertiser",
  "tier_discount": 0.15,
  "volume_discount": 0.05,
  "currency": "USD",
  "rationale": "Base price: $35.00 CPM | Advertiser tier: -15% | Volume discount: -5.0% | Final price: $28.26 CPM"
}
```

---

## CLI Commands

```bash
# View help
ad-seller --help

# Initialize and view catalog
ad-seller init
ad-seller catalog

# Get pricing for a product
ad-seller price ctv-premium --tier agency --volume 5000000

# Process a deal request
ad-seller deal "I want 5M CTV impressions for Q1" --agency agency-123

# Start interactive chat with buyers
ad-seller chat

# Test connection to OpenDirect server
ad-seller connect
```

---

## Configuration Reference

All settings can be configured via environment variables or `.env` file:

```bash
# ─────────────────────────────────────────────────────────────────
# REQUIRED
# ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# ─────────────────────────────────────────────────────────────────
# SELLER IDENTITY
# ─────────────────────────────────────────────────────────────────
SELLER_ORGANIZATION_ID=my-publisher
SELLER_ORGANIZATION_NAME=My Publishing Company

# ─────────────────────────────────────────────────────────────────
# OPENDIRECT SERVER
# ─────────────────────────────────────────────────────────────────
# Live IAB Tech Lab server (recommended)
OPENDIRECT_BASE_URL=https://agentic-direct-server-hwgrypmndq-uk.a.run.app
DEFAULT_PROTOCOL=opendirect21

# ─────────────────────────────────────────────────────────────────
# STORAGE (choose one)
# ─────────────────────────────────────────────────────────────────
# SQLite (default, good for development)
STORAGE_TYPE=sqlite
DATABASE_URL=sqlite:///./ad_seller.db

# Redis (recommended for production)
# STORAGE_TYPE=redis
# REDIS_URL=redis://localhost:6379/0

# ─────────────────────────────────────────────────────────────────
# PRICING DEFAULTS
# ─────────────────────────────────────────────────────────────────
DEFAULT_CURRENCY=USD
DEFAULT_PRICE_FLOOR_CPM=5.0
MIN_DEAL_VALUE=1000.0

# ─────────────────────────────────────────────────────────────────
# YIELD OPTIMIZATION
# ─────────────────────────────────────────────────────────────────
YIELD_OPTIMIZATION_ENABLED=true
PROGRAMMATIC_FLOOR_MULTIPLIER=1.2
PREFERRED_DEAL_DISCOUNT_MAX=0.15

# ─────────────────────────────────────────────────────────────────
# UCP (User Context Protocol)
# ─────────────────────────────────────────────────────────────────
UCP_ENABLED=true
UCP_EMBEDDING_DIMENSION=512
UCP_SIMILARITY_THRESHOLD=0.5
UCP_CONSENT_REQUIRED=true

# ─────────────────────────────────────────────────────────────────
# AD SERVER INTEGRATION (optional)
# ─────────────────────────────────────────────────────────────────
# Google Ad Manager
# AD_SERVER_TYPE=google_ad_manager
# GAM_NETWORK_CODE=12345678
# GAM_JSON_KEY_PATH=/path/to/service-account.json

# FreeWheel
# AD_SERVER_TYPE=freewheel
# FREEWHEEL_API_URL=https://api.freewheel.com
# FREEWHEEL_API_KEY=your-key

# ─────────────────────────────────────────────────────────────────
# LLM CONFIGURATION
# ─────────────────────────────────────────────────────────────────
DEFAULT_LLM_MODEL=anthropic/claude-sonnet-4-5-20250929
MANAGER_LLM_MODEL=anthropic/claude-opus-4-20250514
LLM_TEMPERATURE=0.3
```

---

## Project Structure

```
ad_seller_system/
├── examples/              # Runnable example scripts
│   ├── tiered_pricing.py
│   ├── opendirect_connection.py
│   ├── storage_demo.py
│   └── audience_validation.py
├── src/ad_seller/
│   ├── agents/            # CrewAI agents
│   │   ├── level1/        # Inventory Manager
│   │   ├── level2/        # Channel Specialists (Display, Video, CTV, Mobile, Native)
│   │   └── level3/        # Functional Agents (incl. Audience Validator)
│   ├── clients/           # API clients
│   │   ├── unified_client.py     # Unified protocol access
│   │   ├── opendirect21_client.py # OpenDirect 2.1
│   │   ├── opendirect30_client.py # OpenDirect 3.0
│   │   ├── a2a_client.py         # A2A natural language
│   │   └── ucp_client.py         # UCP embedding exchange
│   ├── crews/             # CrewAI crews
│   │   └── inventory_crews.py    # Channel-specific crews
│   ├── engines/           # Business logic engines
│   │   └── pricing_rules_engine.py
│   ├── flows/             # Workflow orchestration
│   │   └── proposal_handling_flow.py # Proposal evaluation (with audience validation)
│   ├── interfaces/        # User interfaces
│   │   ├── api/           # FastAPI REST server
│   │   └── cli/           # Typer CLI
│   ├── models/            # Pydantic models
│   │   ├── opendirect.py        # OpenDirect entities
│   │   ├── flow_state.py        # Flow state models
│   │   ├── buyer_identity.py    # Buyer identity models
│   │   ├── pricing_tiers.py     # Tiered pricing models
│   │   └── ucp.py               # UCP models (embeddings, capabilities)
│   ├── storage/           # Storage backends
│   │   ├── sqlite_backend.py
│   │   └── redis_backend.py
│   └── tools/             # CrewAI tools
│       ├── pricing/       # Pricing tools
│       ├── inventory/     # Inventory tools
│       ├── deals/         # Deal tools
│       └── audience/      # Audience tools (validation, capability, coverage)
├── tests/
│   └── unit/              # Unit tests
└── scripts/               # Test and utility scripts
```

---

## Development

### Run Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
ANTHROPIC_API_KEY=test pytest tests/ -v

# Run with coverage
pytest tests/ --cov=ad_seller --cov-report=html
```

### Code Quality

```bash
# Linting
ruff check src/

# Type checking
mypy src/

# Format code
ruff format src/
```

---

## Troubleshooting

### "ANTHROPIC_API_KEY required"

Make sure your `.env` file exists and contains a valid API key:
```bash
echo "ANTHROPIC_API_KEY=sk-ant-api03-xxxxx" > .env
```

### "Connection refused" to OpenDirect server

The default server is the live IAB Tech Lab server. Verify connectivity:
```bash
curl https://agentic-direct-server-hwgrypmndq-uk.a.run.app/health
```

### Redis connection issues

If using Redis, ensure it's running:
```bash
redis-cli ping
# Should return: PONG
```

---

## Related Projects

- [ad-buyer-system](https://github.com/mobtownlabs/ad-buyer-system) - Buyer-side agent system (agencies, advertisers)

### IAB Tech Lab Resources

- [agentic-direct](https://github.com/InteractiveAdvertisingBureau/agentic-direct) - IAB Tech Lab reference implementation
- [Demo Client](https://agentic-direct-client-hwgrypmndq-uk.a.run.app/) - Hosted web client
- [A2A Server](https://agentic-direct-server-hwgrypmndq-uk.a.run.app/) - Agent-to-Agent protocol endpoint
- [MCP Info](https://agentic-direct-server-hwgrypmndq-uk.a.run.app/mcp/info) - MCP server metadata
- [MCP SSE](https://agentic-direct-server-hwgrypmndq-uk.a.run.app/mcp/sse) - MCP server-sent events endpoint
- [UCP Specification](https://iabtechlab.com/standards/user-context-protocol/) - User Context Protocol documentation

---

## License

MIT
