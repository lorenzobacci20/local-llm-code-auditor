namespace SampleApp.Services;

public sealed class PricingService
{
    // Return the total for a non-negative unit price and a strictly positive quantity.
    // Invalid arguments are rejected with ArgumentOutOfRangeException.
    public decimal Calculate(decimal unitPrice, int quantity)
    {
        if (unitPrice < 0) throw new ArgumentOutOfRangeException(nameof(unitPrice));
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity));
        return unitPrice * quantity;
    }
}
