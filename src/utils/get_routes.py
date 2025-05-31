from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from typing import Any

def get_module(name:str, * ,package=None) -> Any:
  "Get the RouteTable for each cog."
  n = importlib.util.resolve_name(name,package)
  spec = importlib.util.find_spec(n)
  lib = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(lib)
  return lib