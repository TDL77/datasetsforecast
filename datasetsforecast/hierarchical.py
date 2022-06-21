# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/hierarchical.ipynb (unless otherwise specified).

__all__ = ['Labour', 'Tourism', 'TourismLarge', 'TourismSmall', 'Traffic', 'Wiki2', 'HierarchicalInfo']

# Cell
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import pandas as pd

from .utils import download_file, Info

# Cell
@dataclass
class Labour:
    freq = 'M'

# Cell
@dataclass
class Tourism:
    freq = 'Q'

# Cell
@dataclass
class TourismLarge:
    freq = 'M'

# Cell
@dataclass
class TourismSmall:
    freq = 'Q'

# Cell
@dataclass
class Traffic:
    freq = 'D'

# Cell
@dataclass
class Wiki2:
    freq = 'D'

# Cell
HierarchicalInfo = Info(
    (
        Labour, Tourism, TourismLarge,
        TourismSmall,
        Traffic, Wiki2
    )
)