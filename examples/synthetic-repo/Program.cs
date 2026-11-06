using SampleApp.Services;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
app.MapGet("/", () => "Synthetic code-auditor example");
app.MapGet("/unit-price", (decimal total, int quantity) =>
    PricingService.UnitPrice(total, quantity));
app.Run();
