namespace SampleApp.Services;

public static class PricingService
{
    // Deliberate synthetic defect for optional LLM review: quantity can be zero.
    public static decimal UnitPrice(decimal total, int quantity) => total / quantity;
}
