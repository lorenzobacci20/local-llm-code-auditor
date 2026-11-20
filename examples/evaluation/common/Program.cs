using SampleApp.Services;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
app.MapGet("/quote", (decimal amount, int quantity) =>
    new PricingService().Calculate(amount, quantity));
app.Run();
