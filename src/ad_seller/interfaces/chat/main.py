"""Conversational chat interface for buyer interactions.

Enables natural language conversations with buyers for:
- Discovery and inquiry
- Deal negotiation
- Non-agentic DSP workflows
"""

from typing import Any, Optional

from ...flows import DiscoveryInquiryFlow, NonAgenticDSPFlow, ProductSetupFlow
from ...models.buyer_identity import BuyerContext, BuyerIdentity, AccessTier


class ChatInterface:
    """Chat interface for conversational buyer interactions.

    Supports:
    - Natural language inventory queries
    - Pricing inquiries with tiered responses
    - Deal creation for non-agentic DSPs
    - Negotiation workflows

    Example:
        chat = ChatInterface()
        response = chat.process_message(
            "What CTV inventory do you have available?",
            buyer_context=context,
        )
    """

    def __init__(self) -> None:
        """Initialize the chat interface."""
        self._products: dict[str, Any] = {}
        self._conversation_history: list[dict[str, str]] = []
        self._buyer_context: Optional[BuyerContext] = None

    async def initialize(self) -> None:
        """Initialize products and resources."""
        flow = ProductSetupFlow()
        await flow.kickoff()
        self._products = flow.state.products

    def set_buyer_context(self, context: BuyerContext) -> None:
        """Set the buyer context for the conversation.

        Args:
            context: Buyer identity and authentication context
        """
        self._buyer_context = context

    def process_message(
        self,
        message: str,
        buyer_context: Optional[BuyerContext] = None,
    ) -> dict[str, Any]:
        """Process a chat message from a buyer.

        Args:
            message: The buyer's message
            buyer_context: Optional buyer context (uses session context if not provided)

        Returns:
            Response dict with text and any structured data
        """
        context = buyer_context or self._buyer_context or self._default_context()

        # Add to conversation history
        self._conversation_history.append({
            "role": "user",
            "content": message,
        })

        # Determine message intent
        message_lower = message.lower()
        response: dict[str, Any]

        if self._is_deal_request(message_lower):
            response = self._handle_deal_request(message, context)
        elif self._is_pricing_inquiry(message_lower):
            response = self._handle_pricing_inquiry(message, context)
        elif self._is_availability_inquiry(message_lower):
            response = self._handle_availability_inquiry(message, context)
        else:
            response = self._handle_general_inquiry(message, context)

        # Add response to history
        self._conversation_history.append({
            "role": "assistant",
            "content": response.get("text", ""),
        })

        return response

    def _default_context(self) -> BuyerContext:
        """Create default anonymous buyer context."""
        return BuyerContext(
            identity=BuyerIdentity(),
            is_authenticated=False,
        )

    def _is_deal_request(self, message: str) -> bool:
        """Check if message is a deal creation request."""
        deal_keywords = ["create deal", "book", "buy inventory", "want to buy", "make a deal"]
        return any(keyword in message for keyword in deal_keywords)

    def _is_pricing_inquiry(self, message: str) -> bool:
        """Check if message is a pricing inquiry."""
        pricing_keywords = ["price", "cost", "cpm", "rate", "how much"]
        return any(keyword in message for keyword in pricing_keywords)

    def _is_availability_inquiry(self, message: str) -> bool:
        """Check if message is an availability inquiry."""
        avail_keywords = ["available", "inventory", "impressions", "capacity"]
        return any(keyword in message for keyword in avail_keywords)

    def _handle_deal_request(
        self,
        message: str,
        context: BuyerContext,
    ) -> dict[str, Any]:
        """Handle a deal creation request."""
        flow = NonAgenticDSPFlow()
        result = flow.process_request(
            request_text=message,
            buyer_context=context,
        )

        return {
            "text": result["response"],
            "type": "deal",
            "deal": result.get("deal"),
            "status": result["status"],
        }

    def _handle_pricing_inquiry(
        self,
        message: str,
        context: BuyerContext,
    ) -> dict[str, Any]:
        """Handle a pricing inquiry."""
        tier = context.effective_tier

        # Build pricing response based on tier
        if tier == AccessTier.PUBLIC:
            text = """
Here are our typical pricing ranges:

| Inventory Type | Price Range |
|----------------|-------------|
| Display        | $10-15 CPM  |
| Video          | $20-30 CPM  |
| CTV            | $28-42 CPM  |
| Mobile App     | $15-22 CPM  |
| Native         | $8-12 CPM   |

For exact pricing, please authenticate with your agency credentials.
"""
        else:
            discount = 10 if tier == AccessTier.AGENCY else 15
            text = f"""
As a {tier.value} tier buyer, you receive a {discount}% discount from our standard rates:

| Inventory Type | Your Rate |
|----------------|-----------|
| Display        | ${12 * (1 - discount/100):.2f} CPM |
| Video          | ${25 * (1 - discount/100):.2f} CPM |
| CTV            | ${35 * (1 - discount/100):.2f} CPM |
| Mobile App     | ${18 * (1 - discount/100):.2f} CPM |
| Native         | ${10 * (1 - discount/100):.2f} CPM |

Volume discounts are available for orders over 5M impressions.
Ready to create a deal? Just let me know!
"""

        return {
            "text": text.strip(),
            "type": "pricing",
            "tier": tier.value,
        }

    def _handle_availability_inquiry(
        self,
        message: str,
        context: BuyerContext,
    ) -> dict[str, Any]:
        """Handle an availability inquiry."""
        tier = context.effective_tier

        if tier == AccessTier.PUBLIC:
            text = """
We have inventory available across all channels:

- **Display**: High availability
- **Video**: Moderate availability
- **CTV**: Premium availability
- **Mobile App**: High availability
- **Native**: Moderate availability

For specific impression counts and dates, please authenticate.
"""
        else:
            text = """
Current inventory availability (next 30 days):

| Inventory Type | Available Impressions | Fill Rate |
|----------------|----------------------|-----------|
| Display        | 15M+                 | 72%       |
| Video          | 8M+                  | 85%       |
| CTV            | 5M+                  | 78%       |
| Mobile App     | 12M+                 | 68%       |
| Native         | 10M+                 | 75%       |

What inventory type and volume are you interested in?
"""

        return {
            "text": text.strip(),
            "type": "availability",
            "tier": tier.value,
        }

    def _handle_general_inquiry(
        self,
        message: str,
        context: BuyerContext,
    ) -> dict[str, Any]:
        """Handle a general inquiry."""
        text = """
I can help you with:

1. **Inventory Discovery** - Ask about available inventory types
2. **Pricing** - Get pricing for specific products or ranges
3. **Availability** - Check impression availability
4. **Deal Creation** - Create deals for DSP activation

What would you like to know?

Example questions:
- "What CTV inventory do you have?"
- "How much does video inventory cost?"
- "I want to create a deal for 5M display impressions"
"""

        return {
            "text": text.strip(),
            "type": "general",
        }

    def get_conversation_history(self) -> list[dict[str, str]]:
        """Get the conversation history."""
        return self._conversation_history.copy()

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._conversation_history = []
