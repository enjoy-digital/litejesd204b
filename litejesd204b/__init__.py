#
# This file is part of LiteJESD204
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# Compatibility shim: LiteJESD204B has been renamed LiteJESD204 (the core now covers JESD204B and
# JESD204C). The litejesd204b package is kept for two LiteX release cycles and simply aliases the
# litejesd204 modules, so that `from litejesd204b.core import LiteJESD204BCoreTX` keeps working and
# returns the very same objects as `from litejesd204.core import LiteJESD204BCoreTX`.

import sys
import importlib
import warnings

warnings.warn(
    "The litejesd204b package has been renamed litejesd204; update your imports "
    "(from litejesd204b.xxx import ... -> from litejesd204.xxx import ...). "
    "The litejesd204b compatibility package will be removed in LiteX 2027.04.",
    DeprecationWarning, stacklevel=2)

__path__ = [] # Namespace-less: every submodule is resolved through the aliases below.

for _name in ["common", "core", "core_204c", "link", "link_204c", "transport"]:
    _module = importlib.import_module("litejesd204." + _name)
    sys.modules["litejesd204b." + _name] = _module
    globals()[_name] = _module
