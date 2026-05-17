# Fattern

[Korean](README.md)

Source-available DXF rough marker yield estimator for garment pattern workflows.

Fattern parses supported DXF pattern outlines, calculates deterministic piece metrics, creates a rough marker layout under a fabric-width constraint, renders an SVG preview, and writes a Markdown report.

This tool estimates rough marker yield. It does not produce final marker yield and does not replace a commercial marker system.

## License Summary

**PolyForm Noncommercial License 1.0.0 + separate Commercial License**

This repository is source-available and permits noncommercial use only.

Commercial use, production use, paid consulting, resale, hosted service use, or integration into commercial workflows requires a separate written commercial license from the copyright holder.

## Features

- Extracts piece candidates from closed DXF LWPOLYLINE entities
- Calculates area, perimeter, and bounding boxes
- Creates rough marker layouts from fabric width, rotation rules, and clearance
- Validates overlap, fabric width, and grainline rules
- Renders SVG previews
- Generates Markdown reports
- Includes MCP tool wrappers and orchestration regression tests

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

## Supported Scope

The current implementation is MVP-scoped.

- Focused on closed LWPOLYLINE input
- Uses a bbox shelf rough marker strategy
- DXF layer convention detection is limited
- Advanced nesting optimization, print matching, and full commercial CAD compatibility are out of scope

## License Details

This project is source-available under the **PolyForm Noncommercial License 1.0.0**.

You may use, study, modify, and share it for noncommercial purposes under the license terms.

Commercial use, production use, paid consulting, resale, hosted service use, or integration into commercial workflows requires a separate written commercial license from the copyright holder.

See:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)

This project is not OSI-approved open source because commercial use is restricted.
