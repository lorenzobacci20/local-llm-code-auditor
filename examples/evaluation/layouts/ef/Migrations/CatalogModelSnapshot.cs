using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace Catalog.Migrations;

internal sealed class CatalogModelSnapshot : ModelSnapshot
{
    protected override void BuildModel(ModelBuilder builder)
    {
        builder.Entity("Item", item =>
        {
            item.ToTable("Items");
            item.Property<int>("Id");
            item.Property<string>("Label");
            item.HasKey("Id");
        });
    }
}
