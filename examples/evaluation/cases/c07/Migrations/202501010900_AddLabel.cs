using Microsoft.EntityFrameworkCore.Migrations;

namespace Catalog.Migrations;

public sealed class AddLabel : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
        => migrationBuilder.AddColumn<string>(name: "Label", table: "Items", nullable: true);

    protected override void Down(MigrationBuilder migrationBuilder)
        => throw new NotImplementedException();
}
