namespace SampleApp.Services;

public sealed class PricingService
{
    // Return the per-item price for a non-negative total and a strictly positive quantity.
    // Invalid arguments are rejected with ArgumentOutOfRangeException.
    public decimal Calculate(decimal total, int quantity)
    {
        if (total < 0) throw new ArgumentOutOfRangeException(nameof(total));
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity));
        return total / quantity;
    }
}
