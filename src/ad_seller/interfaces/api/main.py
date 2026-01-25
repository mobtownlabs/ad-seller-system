"""REST API interface for programmatic access.

Provides endpoints for:
- Product catalog
- Pricing queries
- Proposal submission
- Deal generation
"""

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Ad Seller System API",
    description="IAB OpenDirect 2.1 compliant seller API",
    version="0.1.0",
)


# =============================================================================
# Request/Response Models
# =============================================================================


class PricingRequest(BaseModel):
    """Request for pricing information."""

    product_id: str
    buyer_tier: str = "public"
    agency_id: Optional[str] = None
    advertiser_id: Optional[str] = None
    volume: int = 0


class PricingResponse(BaseModel):
    """Pricing response."""

    product_id: str
    base_price: float
    final_price: float
    currency: str
    tier_discount: float
    volume_discount: float
    rationale: str


class ProposalRequest(BaseModel):
    """Request to submit a proposal."""

    product_id: str
    deal_type: str
    price: float
    impressions: int
    start_date: str
    end_date: str
    buyer_id: Optional[str] = None
    agency_id: Optional[str] = None
    advertiser_id: Optional[str] = None


class ProposalResponse(BaseModel):
    """Proposal submission response."""

    proposal_id: str
    recommendation: str
    status: str
    counter_terms: Optional[dict[str, Any]] = None
    errors: list[str] = []


class DealRequest(BaseModel):
    """Request to generate a deal."""

    proposal_id: str
    dsp_platform: Optional[str] = None


class DealResponse(BaseModel):
    """Deal generation response."""

    deal_id: str
    deal_type: str
    price: float
    pricing_model: str
    openrtb_params: dict[str, Any]
    activation_instructions: dict[str, str]


class DiscoveryRequest(BaseModel):
    """Discovery query request."""

    query: str
    buyer_tier: str = "public"
    agency_id: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/")
async def root():
    """API root."""
    return {
        "name": "Ad Seller System API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/products")
async def list_products():
    """List all products in the catalog."""
    from ...flows import ProductSetupFlow

    flow = ProductSetupFlow()
    await flow.kickoff()

    products = []
    for product in flow.state.products.values():
        products.append({
            "product_id": product.product_id,
            "name": product.name,
            "description": product.description,
            "inventory_type": product.inventory_type,
            "base_cpm": product.base_cpm,
            "floor_cpm": product.floor_cpm,
            "deal_types": [dt.value for dt in product.supported_deal_types],
        })

    return {"products": products}


@app.get("/products/{product_id}")
async def get_product(product_id: str):
    """Get a specific product."""
    from ...flows import ProductSetupFlow

    flow = ProductSetupFlow()
    await flow.kickoff()

    product = flow.state.products.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "product_id": product.product_id,
        "name": product.name,
        "description": product.description,
        "inventory_type": product.inventory_type,
        "base_cpm": product.base_cpm,
        "floor_cpm": product.floor_cpm,
        "deal_types": [dt.value for dt in product.supported_deal_types],
    }


@app.post("/pricing", response_model=PricingResponse)
async def get_pricing(request: PricingRequest):
    """Get pricing for a product based on buyer context."""
    from ...engines.pricing_rules_engine import PricingRulesEngine
    from ...models.buyer_identity import BuyerContext, BuyerIdentity, AccessTier
    from ...models.pricing_tiers import TieredPricingConfig
    from ...flows import ProductSetupFlow

    # Get products
    flow = ProductSetupFlow()
    await flow.kickoff()

    product = flow.state.products.get(request.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Create buyer context
    tier_map = {
        "public": AccessTier.PUBLIC,
        "seat": AccessTier.SEAT,
        "agency": AccessTier.AGENCY,
        "advertiser": AccessTier.ADVERTISER,
    }
    access_tier = tier_map.get(request.buyer_tier.lower(), AccessTier.PUBLIC)

    identity = BuyerIdentity(
        agency_id=request.agency_id,
        advertiser_id=request.advertiser_id,
    )
    context = BuyerContext(
        identity=identity,
        is_authenticated=access_tier != AccessTier.PUBLIC,
    )

    # Calculate price
    config = TieredPricingConfig(seller_organization_id="default")
    engine = PricingRulesEngine(config)

    decision = engine.calculate_price(
        product_id=request.product_id,
        base_price=product.base_cpm,
        buyer_context=context,
        volume=request.volume,
    )

    return PricingResponse(
        product_id=request.product_id,
        base_price=decision.base_price,
        final_price=decision.final_price,
        currency=decision.currency,
        tier_discount=decision.tier_discount,
        volume_discount=decision.volume_discount,
        rationale=decision.rationale,
    )


@app.post("/proposals", response_model=ProposalResponse)
async def submit_proposal(request: ProposalRequest):
    """Submit a proposal for review."""
    from ...flows import ProposalHandlingFlow, ProductSetupFlow
    from ...models.buyer_identity import BuyerContext, BuyerIdentity
    import uuid

    # Get products
    setup_flow = ProductSetupFlow()
    await setup_flow.kickoff()

    # Create buyer context
    identity = BuyerIdentity(
        agency_id=request.agency_id,
        advertiser_id=request.advertiser_id,
    )
    context = BuyerContext(
        identity=identity,
        is_authenticated=request.agency_id is not None,
    )

    # Process proposal
    proposal_id = f"prop-{uuid.uuid4().hex[:8]}"
    proposal_data = {
        "product_id": request.product_id,
        "deal_type": request.deal_type,
        "price": request.price,
        "impressions": request.impressions,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "buyer_id": request.buyer_id,
    }

    flow = ProposalHandlingFlow()
    result = flow.handle_proposal(
        proposal_id=proposal_id,
        proposal_data=proposal_data,
        buyer_context=context,
        products=setup_flow.state.products,
    )

    return ProposalResponse(
        proposal_id=proposal_id,
        recommendation=result["recommendation"],
        status=result["status"],
        counter_terms=result.get("counter_terms"),
        errors=result.get("errors", []),
    )


@app.post("/deals", response_model=DealResponse)
async def generate_deal(request: DealRequest):
    """Generate a deal from an accepted proposal."""
    from ...flows import DealGenerationFlow

    flow = DealGenerationFlow()
    result = flow.generate_deal(
        proposal_id=request.proposal_id,
        proposal_data={
            "status": "accepted",
            "deal_type": "preferred_deal",
            "price": 15.0,
            "product_id": "display",
            "impressions": 1000000,
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        },
    )

    if not result.get("deal_id"):
        raise HTTPException(status_code=400, detail="Failed to generate deal")

    return DealResponse(
        deal_id=result["deal_id"],
        deal_type=result["deal_type"],
        price=result["price"],
        pricing_model=result["pricing_model"],
        openrtb_params=result["openrtb_params"],
        activation_instructions=result["activation_instructions"],
    )


@app.post("/discovery")
async def discovery_query(request: DiscoveryRequest):
    """Process a discovery query about inventory."""
    from ...flows import DiscoveryInquiryFlow, ProductSetupFlow
    from ...models.buyer_identity import BuyerContext, BuyerIdentity, AccessTier

    # Get products
    setup_flow = ProductSetupFlow()
    await setup_flow.kickoff()

    # Create buyer context
    tier_map = {
        "public": AccessTier.PUBLIC,
        "agency": AccessTier.AGENCY,
        "advertiser": AccessTier.ADVERTISER,
    }
    access_tier = tier_map.get(request.buyer_tier.lower(), AccessTier.PUBLIC)

    identity = BuyerIdentity(agency_id=request.agency_id)
    context = BuyerContext(
        identity=identity,
        is_authenticated=access_tier != AccessTier.PUBLIC,
    )

    # Process discovery
    flow = DiscoveryInquiryFlow()
    response = flow.query(
        query=request.query,
        buyer_context=context,
        products=setup_flow.state.products,
    )

    return response
