---
title: "Python uv: Things I forget"
date: 2026-02-14
draft: false
description: "Expose packages via UV, expose scripts as uv tools"
tags: ["python"]
categories: ["Python"]
---
# Packaging
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
# Tools

To expose a python function as a [tool](https://docs.astral.sh/uv/#tools) you need both a `script` and `build backend`.

There's a lot of guides that tell you to use `setuptools` or `hatch` a holdover from pre [March 2025](https://pypi.org/project/uv-build/0.6.3/)
when UV created its own build backend - try it first.

```toml
[project.scripts]
agent_example = "src.agents.__init__.py:main"

[build-system]
requires = ["uv_build>=0.10.7,<0.11.0"]
build-backend = "uv_build"
```

Then you can run it with `uvx agent_example`
