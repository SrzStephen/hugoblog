---
title: "uv modules"
date: 2026-02-14
draft: false
description: "How to configure uv's build backend to expose multiple Python packages from a src/ layout using the module-name setting in pyproject.toml."
tags: ["python"]
categories: ["Python"]
---

I always forget how to set up [uv](https://docs.astral.sh/uv/) properly so that it allows me to do something like

```python
from agents import ...
```

```tree
.
├── src/
│   ├── agents/
│   │   └── __init__.py
│   └── client/
│       └── __init__.py
├── test/
└── pyproject.toml
```

The answer is [modules](https://docs.astral.sh/uv/concepts/build-backend/#modules)

```toml
[build-system]
requires = ["uv_build>=0.10.0,<0.11.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = ["agents", "client"]
module-root = "src"
```