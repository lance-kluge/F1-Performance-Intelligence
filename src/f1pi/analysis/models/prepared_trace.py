"""Prepared telemetry trace data."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class PreparedTrace:
    distance: NDArray[np.float64]
    elapsed: NDArray[np.float64]
    speed: NDArray[np.float64]
    throttle: NDArray[np.float64]
    brake: NDArray[np.float64]
    x: NDArray[np.float64]
    y: NDArray[np.float64]

    @property
    def length_metres(self) -> float:
        return float(self.distance[-1])
