
# IMAS IDS Python Tools

## Description

A comprehensive Python-based collection of data analysis and visualization tools for the ITER Modeling and Analysis Suite (IMAS) framework. This package provides physicists and engineers with powerful utilities to interact with the IDS (IMAS Data Structure) database, enabling efficient analysis and visualization of fusion simulation and experimental data.

## Features

- **Compute Module**: Advanced calculations and data processing for various physics domains (core profiles, equilibrium, magnetics, waves, etc.)
- **View Module**: Visualization and printing tools for analysis results
- **Domain Module**: Cross-IDS operations and kinetic profile analysis
- **Database Tools**: CLI scripts for database operations, performance analysis, and data conversion
- **Validation**: Schema-based validation for ITER scenarios
- **Conversion Tools**: EQDSK to IDS conversion capabilities

## Installation

### On SDCC at ITER

The tools are pre-installed on the SDCC computing platform and available as shell commands.

### Local Installation

```shell
git clone ssh://git@git.iter.org/imas/idstools.git
cd idstools
pip install . [--user]
```

### Requirements

- Python 3.8+
- IMAS module/environment

## Available Commands

The package installs several command-line tools grouped by functionality:

- **IDS Operations**: `idslist`, `idscp`, `idsdiff`, `idsperf`, `idsquery`, `idsresample`, `idssize`, `idsprint`
- **Visualization**: `plotequilibrium`, `plotscenario`, `plotcoresources`, `plotcoretransport`, `plotedgeprofiles`, and many more `plot*` commands
- **Database Management**: `dblist`, `dbselector`, `create_db_entry`, `show_db_entry`, `dbconverter`
- **Analysis & Summary**: `scenario_summary`, `disruption_summary`, `md_status`
- **Conversion**: `eqdsk2ids`

## Quick Start

Visit the [project repository](https://git.iter.org/projects/IMAS/repos/idstools/browse) for documentation and examples.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

## License

See [LICENSE.md](LICENSE.md) for licensing information.

