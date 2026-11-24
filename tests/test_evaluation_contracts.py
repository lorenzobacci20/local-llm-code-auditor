import io
import json
import os
import runpy
import shutil
import subprocess
import sys

import pytest

from scripts.evaluate import DATASET, materialize

CASES = {item["id"]: item for item in json.loads((DATASET / "cases.json").read_text())["cases"]}


@pytest.mark.parametrize("case_id", ["c03", "c04", "c05", "c06"])
def test_pricing_contract(case_id, tmp_path):
    dotnet = shutil.which("dotnet")
    if not dotnet:
        pytest.skip("Pricing probes require a local .NET SDK (8 or newer)")
    version = subprocess.run([dotnet, "--version"], capture_output=True, text=True, cwd=tmp_path)
    if version.returncode or int(version.stdout.strip().split(".")[0]) < 8:
        pytest.skip("Pricing probes require a local .NET SDK (8 or newer)")
    target = "net" + version.stdout.strip().split(".")[0] + ".0"
    (tmp_path / "probe.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        "<ImplicitUsings>enable</ImplicitUsings>"
        f"<TargetFramework>{target}</TargetFramework></PropertyGroup></Project>"
    )
    (tmp_path / "NuGet.Config").write_text(
        "<configuration><packageSources><clear /></packageSources></configuration>"
    )
    shutil.copyfile(
        DATASET / "cases" / case_id / "Services" / "PricingService.cs",
        tmp_path / "PricingService.cs",
    )
    (tmp_path / "Program.cs").write_text(
        "var service = new SampleApp.Services.PricingService();\n"
        "try { Console.WriteLine(service.Calculate(10m, 0)); }\n"
        "catch (ArithmeticException ex) { Console.WriteLine(ex.GetType().Name); }\n"
        "catch (ArgumentException ex) { Console.WriteLine(ex.GetType().Name); }\n"
        "Console.WriteLine(service.Calculate(10m, 10).ToString(System.Globalization.CultureInfo.InvariantCulture));"
    )
    result = subprocess.run(
        [dotnet, "run", "--project", "probe.csproj"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
        env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"},
    )
    error, value = result.stdout.strip().splitlines()[-2:]
    assert error == ("DivideByZeroException" if case_id == "c03" else "ArgumentOutOfRangeException")
    assert float(value) == {"c03": 1, "c04": 1, "c05": 100, "c06": 90}[case_id]


@pytest.mark.parametrize("case_id", ["c09", "c10"])
def test_missing_label(case_id):
    label = runpy.run_path(str(DATASET / "cases" / case_id / "labels.py"))["display_label"]
    assert label("  Oak  ") == "Oak"
    if case_id == "c09":
        with pytest.raises(AttributeError):
            label(None)
    else:
        assert label(None) == "(untitled)"


@pytest.mark.parametrize("case_id", ["c11", "c12"])
def test_invalid_quantity(case_id):
    parse = runpy.run_path(str(DATASET / "cases" / case_id / "quantities.py"))["parse_quantity"]
    assert parse("3") == 3
    if case_id == "c11":
        with pytest.raises(ValueError):
            parse("many")
    else:
        assert parse("many") is None


@pytest.mark.parametrize("case_id", ["c13", "c14"])
def test_overlapping_reservations(case_id):
    stock = runpy.run_path(str(DATASET / "cases" / case_id / "reservations.py"))["Stock"](1)

    class HeldReceipt:
        def __await__(self):
            yield "receipt pending"

    async def ready_receipt():
        return None

    # Step the two real coroutines at one defined suspension point, with no OS scheduling.
    first = stock.reserve(HeldReceipt)
    assert first.send(None) == "receipt pending"
    with pytest.raises(StopIteration) as second:
        stock.reserve(ready_receipt).send(None)
    with pytest.raises(StopIteration) as resumed:
        first.send(None)
    assert (resumed.value.value, second.value.value) == (True, case_id == "c13")
    assert stock.units == (-1 if case_id == "c13" else 0)


@pytest.mark.parametrize("case_id", ["c15", "c16"])
def test_rejected_batch(case_id):
    ledger = runpy.run_path(str(DATASET / "cases" / case_id / "ledger.py"))["Ledger"](5)
    with pytest.raises(ValueError):
        ledger.post([2, -9])
    assert ledger.balance == (7 if case_id == "c15" else 5)


@pytest.mark.parametrize("case_id", ["c17", "c18"])
def test_output_stream_closed_on_failure(case_id):
    class RefusingStream(io.StringIO):
        def write(self, text):
            raise OSError("unavailable")

    stream = RefusingStream()
    export = runpy.run_path(str(DATASET / "cases" / case_id / "exports.py"))["export_row"]
    with pytest.raises(OSError):
        export(lambda: stream, "row")
    assert stream.closed == (case_id == "c18")
    stream.close()


@pytest.mark.parametrize("case_id", ["c19", "c20"])
def test_invoice_through_public_handler(case_id, tmp_path):
    repo = tmp_path / "invoice"
    materialize(CASES[case_id], repo)
    command = (
        "from invoice_handler import handle; print(handle([100])['total'], handle([99])['total'])"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", command],
        cwd=repo,
        text=True,
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert result.stdout.strip() == ("100 99" if case_id == "c19" else "99 99")


def test_clean_controls():
    decision = runpy.run_path(str(DATASET / "cases/c21/approvals.py"))["decision"]
    assert [decision(role) for role in (" Reviewer ", "viewer", None)] == [
        "approved",
        "pending",
        "pending",
    ]
    mean = runpy.run_path(str(DATASET / "cases/c22/windows.py"))["mean"]
    assert mean([]) is None
    assert mean([0]) == 0
