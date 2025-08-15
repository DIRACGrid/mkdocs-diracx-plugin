# MkDocs DiracX Plugin

An MkDocs plugin that aggregates documentation from multiple DiracX ecosystem repositories into a unified documentation site.

## Installation

```bash
pip install git+https://github.com/DIRACGrid/mkdocs-diracx-plugin.git
```

## Usage

Add the plugin to your `mkdocs.yml` configuration:

```yaml
plugins:
  - diracx:
      repos:
        - url: https://github.com/DIRACGrid/diracx-charts
          branch: master
          include:
            - docs
            - diracx
        - url: https://github.com/DIRACGrid/diracx-web
          branch: main
          include:
            - docs
```

## Configuration

### Repository Options

- **`url`**: Repository URL (remote) or local filesystem path
- **`branch`**: Git branch to checkout (ignored for local paths) 
- **`include`**: List of directories/files to include from the repository

### Example Configurations

**Remote repositories:**
```yaml
plugins:
  - diracx:
      repos:
        - url: https://github.com/DIRACGrid/diracx-charts
          branch: master
          include: [docs, diracx]
```

**Local repositories:**
```yaml
plugins:
  - diracx:
      repos:
        - url: /path/to/local/repo
          include: [docs]
```

## How It Works

1. Creates a temporary directory during the build process
2. Copies the main documentation repository  
3. For each configured repository:
   - **Remote**: Clones and uses git sparse-checkout for efficiency
   - **Local**: Copies specified directories directly
4. Merges all documentation into a single site structure
5. Supports live reload during `mkdocs serve`

