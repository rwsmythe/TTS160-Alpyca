# -*- coding: utf-8 -*-
"""
Plate Solver for Alignment Monitor.

Provides astrometric plate solving using the tetra3 library
developed by ESA (European Space Agency).

Third-Party Library:
    tetra3 is licensed under the Apache License 2.0.
    https://github.com/esa/tetra3

    tetra3 is a fast lost-in-space plate solver for star trackers,
    providing ~10ms solve times with ~10 arcsecond accuracy.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

# Import tetra3 for plate solving
try:
    import tetra3
    TETRA3_AVAILABLE = True
except ImportError:
    TETRA3_AVAILABLE = False
    tetra3 = None


@dataclass
class SolveResult:
    """Plate solve result."""
    success: bool
    ra: float  # Right Ascension in hours (0-24)
    dec: float  # Declination in degrees (-90 to +90)
    roll: float  # Roll angle in degrees
    fov: float  # Field of view in degrees
    solve_time_ms: float  # Solve time in milliseconds
    matched_stars: int  # Number of matched stars
    rmse: float  # RMS error in arcseconds
    confidence: float  # Match confidence (0.0 - 1.0)
    error_message: str = ""


class PlateSolver:
    """Plate solving using tetra3.

    Provides fast astrometric plate solving from star centroids
    without requiring prior position information (lost-in-space solving).

    Thread Safety:
        The solve_from_centroids() method is thread-safe as tetra3
        operates on immutable database and input data.

    Attributes:
        DEFAULT_FOV: Default field of view estimate in degrees.
        DEFAULT_FOV_ERROR: Default FOV search range as fraction of FOV.
    """

    DEFAULT_FOV = 1.0  # degrees
    DEFAULT_FOV_ERROR = 0.2  # 20% tolerance

    def __init__(
        self,
        logger: logging.Logger,
        fov_estimate: float = DEFAULT_FOV,
        database_path: Optional[str] = None
    ):
        """Initialize plate solver.

        Args:
            logger: Logger instance for solver operations.
            fov_estimate: Estimated field of view in degrees.
            database_path: Path to tetra3 star pattern database.
                          If None or not found, uses default database.
        """
        self._logger = logger
        self._fov_estimate = fov_estimate
        self._database_path = database_path
        self._solver: Optional[tetra3.Tetra3] = None
        self._database_loaded = False

        if not TETRA3_AVAILABLE:
            self._logger.warning(
                "tetra3 library not available - plate solving disabled. "
                "Install with: pip install tetra3"
            )
        else:
            self._initialize_solver()

    def _initialize_solver(self) -> None:
        """Initialize tetra3 solver with database."""
        try:
            if self._database_path:
                db_path = Path(self._database_path)
                if db_path.exists():
                    self._solver = tetra3.Tetra3(str(db_path))
                    self._database_loaded = True
                    self._logger.info(f"Loaded tetra3 database from {db_path}")
                else:
                    self._logger.warning(
                        f"tetra3 database not found at {db_path}, "
                        "using default database"
                    )
                    self._solver = tetra3.Tetra3()
                    self._database_loaded = True
            else:
                # Use default database
                self._solver = tetra3.Tetra3()
                self._database_loaded = True
                self._logger.info("Initialized tetra3 with default database")

        except Exception as e:
            self._logger.error(f"Failed to initialize tetra3: {e}")
            self._solver = None
            self._database_loaded = False

    def solve_from_centroids(
        self,
        centroids: np.ndarray,
        image_width: int,
        image_height: int,
        fov_estimate: Optional[float] = None,
        timeout_ms: Optional[int] = None
    ) -> SolveResult:
        """Solve plate from star centroids.

        Args:
            centroids: Nx2 array of (x, y) star centroids in pixels.
            image_width: Image width in pixels.
            image_height: Image height in pixels.
            fov_estimate: Estimated field of view in degrees.
                         If None, uses instance default.
            timeout_ms: Solve timeout in milliseconds.
                       If None, no timeout.

        Returns:
            SolveResult with solved position or error information.
        """
        if not TETRA3_AVAILABLE or self._solver is None:
            return SolveResult(
                success=False,
                ra=0.0, dec=0.0, roll=0.0, fov=0.0,
                solve_time_ms=0.0, matched_stars=0, rmse=0.0, confidence=0.0,
                error_message="tetra3 not available or not initialized"
            )

        if centroids is None or len(centroids) == 0:
            return SolveResult(
                success=False,
                ra=0.0, dec=0.0, roll=0.0, fov=0.0,
                solve_time_ms=0.0, matched_stars=0, rmse=0.0, confidence=0.0,
                error_message="No star centroids provided"
            )

        if len(centroids) < 4:
            return SolveResult(
                success=False,
                ra=0.0, dec=0.0, roll=0.0, fov=0.0,
                solve_time_ms=0.0, matched_stars=len(centroids), rmse=0.0, confidence=0.0,
                error_message=f"Insufficient stars for solving ({len(centroids)} < 4)"
            )

        try:
            start_time = time.perf_counter()

            fov = fov_estimate or self._fov_estimate
            fov_error = fov * self.DEFAULT_FOV_ERROR

            self._logger.debug(
                f"Solving with {len(centroids)} stars, "
                f"FOV estimate={fov:.2f}+/-{fov_error:.2f} deg"
            )

            # tetra3 expects star_centroids as list of (y, x) tuples
            # Our centroids are (x, y), so we need to swap
            star_centroids = [(float(c[1]), float(c[0])) for c in centroids]

            # Call tetra3 solver
            result = self._solver.solve_from_centroids(
                star_centroids,
                (image_height, image_width),
                fov_estimate=fov,
                fov_max_error=fov_error,
                solve_timeout=timeout_ms
            )

            solve_time_ms = (time.perf_counter() - start_time) * 1000

            # Check if solution was found
            if result.get('RA') is not None:
                # tetra3 returns RA in degrees (0-360), convert to hours (0-24)
                ra_hours = result['RA'] / 15.0
                dec_deg = result['Dec']
                roll_deg = result['Roll']
                fov_deg = result['FOV']
                rmse = result.get('RMSE', 0.0)
                matched = result.get('Matches', len(centroids))
                p_match = result.get('P_match', 1.0)

                self._logger.info(
                    f"Plate solve successful: "
                    f"RA={ra_hours:.4f}h, Dec={dec_deg:.4f}deg, "
                    f"Roll={roll_deg:.1f}deg, FOV={fov_deg:.3f}deg, "
                    f"RMSE={rmse:.1f}arcsec, time={solve_time_ms:.1f}ms"
                )

                return SolveResult(
                    success=True,
                    ra=ra_hours,
                    dec=dec_deg,
                    roll=roll_deg,
                    fov=fov_deg,
                    solve_time_ms=solve_time_ms,
                    matched_stars=matched,
                    rmse=rmse,
                    confidence=p_match
                )
            else:
                self._logger.warning(
                    f"Plate solve failed: no solution found "
                    f"({len(centroids)} stars, {solve_time_ms:.1f}ms)"
                )
                return SolveResult(
                    success=False,
                    ra=0.0, dec=0.0, roll=0.0, fov=0.0,
                    solve_time_ms=solve_time_ms,
                    matched_stars=0,
                    rmse=0.0,
                    confidence=0.0,
                    error_message="No solution found"
                )

        except Exception as e:
            self._logger.error(f"Plate solving failed: {e}")
            return SolveResult(
                success=False,
                ra=0.0, dec=0.0, roll=0.0, fov=0.0,
                solve_time_ms=0.0, matched_stars=0, rmse=0.0, confidence=0.0,
                error_message=str(e)
            )

    def set_fov_estimate(self, fov_degrees: float) -> None:
        """Update the default FOV estimate.

        Args:
            fov_degrees: New FOV estimate in degrees.
        """
        self._fov_estimate = fov_degrees
        self._logger.debug(f"FOV estimate set to {fov_degrees:.2f} degrees")

    def is_initialized(self) -> bool:
        """Check if solver is initialized with database.

        Returns:
            True if solver is ready, False otherwise.
        """
        return self._solver is not None and self._database_loaded

    @staticmethod
    def is_available() -> bool:
        """Check if tetra3 library is available.

        Returns:
            True if tetra3 is available, False otherwise.
        """
        return TETRA3_AVAILABLE
