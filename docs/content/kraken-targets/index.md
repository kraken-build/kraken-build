---
title: Kraken Targets
---

# Kraken Targets

The `kraken-targets` package provides a declarative interface for defining your Kraken build graph. Targets define
an aspect of your project, such as a library, executable, test suite, package registry, or other build artifact. The
targets are then processed by rules that define how to wire them together into a build graph.

__Example:__

```python
from kraken.targets import python_project, jtd_schema

jtd_schema(
    name = "config",
    srcs = ["src/config-schema.jtd"],
)

python_project(
    name = "main",
    deps = ["config"],
    settings = {
        "jtd.codegen": {
            "prefix": "src/mypackage/generated"
        }
    }
)
```
