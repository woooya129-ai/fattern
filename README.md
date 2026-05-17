# Fattern

DXF-based rough marker yield estimator for garment pattern workflows.

Fattern parses supported DXF pattern outlines, calculates deterministic piece metrics, creates a rough marker layout, renders SVG preview output, and writes a Markdown report.

This tool estimates 가요척. It does not produce 확정 요척 or replace a commercial marker system.

## CLI

Run from the repository root:

```powershell
python -m fattern --help
```

Example:

```powershell
python -m fattern estimate tests\fixtures\rectangle_lwpolyline.dxf --fabric-width 10 --unit cm --seam-allowance-included yes --one-way-fabric no --out fattern-output
```

On Windows, the local wrapper also works:

```powershell
.\fattern.cmd --help
```

## Development

Run the test suite:

```powershell
python -m unittest discover -s tests
```

`pytest` is optional and is not required by the current test plan.

## License

This project is source-available under the PolyForm Noncommercial License 1.0.0.

You may use, study, modify, and share it for noncommercial purposes under the license terms.

Commercial use, production use, paid consulting, resale, hosted service use, or integration into commercial workflows requires a separate written commercial license from the copyright holder.

See:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)

This project is not OSI-approved open source because commercial use is restricted.
