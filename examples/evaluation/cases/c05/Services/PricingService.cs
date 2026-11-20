namespace SampleApp.Services;

public sealed class PricingService
{
    // Return the order total. Quantities of ten or more receive a ten percent discount.
    // Unit price must be non-negative; quantity must be strictly positive.
    // Invalid arguments are rejected with ArgumentOutOfRangeException.
    public decimal Calculate(decimal unitPrice, int quantity)
    {
        if (unitPrice < 0) throw new ArgumentOutOfRangeException(nameof(unitPrice));
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity));
        decimal total = unitPrice * quantity;
        return quantity > 10 ? total * 0.9m : total;
    }
}
