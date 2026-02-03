# -*- coding: utf-8 -*-
"""
Star Detector for Alignment Monitor.

Provides star detection and centroid extraction using the SEP library
(Source Extractor in Python).

Third-Party Library:
    SEP is licensed under LGPLv3 with BSD/MIT options.
    https://github.com/kbarbary/sep

    If you use SEP in a publication, please cite:
    - Barbary, K. (2016). "SEP: Source Extractor as a library."
    - Bertin, E. & Arnouts, S. (1996). "SExtractor: Software for source extraction."
"""

import logging
from dataclasses import dataclass
from typing import Optional, List

import numpy as np

# Import SEP for star detection
try:
    import sep
    SEP_AVAILABLE = True
except ImportError:
    SEP_AVAILABLE = False
    sep = None


@dataclass
class DetectedStar:
    """Single detected star centroid."""
    x: float  # pixel x coordinate (column)
    y: float  # pixel y coordinate (row)
    flux: float  # integrated flux (ADU)
    peak: float  # peak pixel value (ADU)
    a: float  # semi-major axis (pixels)
    b: float  # semi-minor axis (pixels)
    theta: float  # position angle (radians)


@dataclass
class DetectionResult:
    """Star detection results."""
    stars: List[DetectedStar]
    centroids: np.ndarray  # Nx2 array of (x, y) centroids
    background_mean: float
    background_rms: float
    detection_threshold: float
    star_count: int


class StarDetector:
    """Star detection using SEP (Source Extractor in Python).

    Provides background subtraction and star centroid extraction
    optimized for plate solving applications.

    Thread Safety:
        This class is thread-safe for concurrent detect_stars() calls
        as each call operates on independent data.

    Attributes:
        DEFAULT_THRESHOLD: Default detection threshold in sigma.
        DEFAULT_MIN_AREA: Default minimum pixels for a valid detection.
        MAX_STARS: Default maximum stars to return.
    """

    DEFAULT_THRESHOLD = 5.0  # sigma above background
    DEFAULT_MIN_AREA = 5  # minimum pixels for detection
    MAX_STARS = 100  # limit for plate solving efficiency

    def __init__(self, logger: logging.Logger):
        """Initialize star detector.

        Args:
            logger: Logger instance for detection operations.
        """
        self._logger = logger

        if not SEP_AVAILABLE:
            self._logger.warning(
                "SEP library not available - star detection disabled. "
                "Install with: pip install sep"
            )

    def detect_stars(
        self,
        image_data: np.ndarray,
        threshold_sigma: float = DEFAULT_THRESHOLD,
        min_area: int = DEFAULT_MIN_AREA,
        max_stars: int = MAX_STARS
    ) -> Optional[DetectionResult]:
        """Detect stars in image and extract centroids.

        Performs background subtraction followed by source extraction
        to identify stars. Returns the brightest stars sorted by flux.

        Args:
            image_data: 2D numpy array of image data (must be float-compatible).
            threshold_sigma: Detection threshold in sigma above background.
            min_area: Minimum number of pixels for valid detection.
            max_stars: Maximum number of stars to return (brightest first).

        Returns:
            DetectionResult with detected stars and centroids,
            or None if detection fails or SEP is not available.
        """
        if not SEP_AVAILABLE:
            self._logger.error("Cannot detect stars: SEP not available")
            return None

        if image_data is None or image_data.size == 0:
            self._logger.error("Cannot detect stars: empty image data")
            return None

        try:
            # Ensure correct data type and byte order for SEP
            # SEP requires native byte order and contiguous array
            data = self._prepare_array(image_data)

            # Background estimation and subtraction
            self._logger.debug("Estimating background...")
            bkg = sep.Background(data)
            background_mean = float(bkg.globalback)
            background_rms = float(bkg.globalrms)

            self._logger.debug(
                f"Background: mean={background_mean:.1f}, rms={background_rms:.1f}"
            )

            # Subtract background
            data_sub = data - bkg.back()

            # Source extraction
            self._logger.debug(
                f"Extracting sources (threshold={threshold_sigma}sigma, "
                f"minarea={min_area})..."
            )

            objects = sep.extract(
                data_sub,
                threshold_sigma,
                err=bkg.rms(),
                minarea=min_area
            )

            if len(objects) == 0:
                self._logger.warning("No stars detected in image")
                return DetectionResult(
                    stars=[],
                    centroids=np.array([]).reshape(0, 2),
                    background_mean=background_mean,
                    background_rms=background_rms,
                    detection_threshold=threshold_sigma,
                    star_count=0
                )

            # Sort by flux (brightest first) and limit
            sorted_idx = np.argsort(objects['flux'])[::-1][:max_stars]
            objects = objects[sorted_idx]

            # Build result structures
            stars = [
                DetectedStar(
                    x=float(obj['x']),
                    y=float(obj['y']),
                    flux=float(obj['flux']),
                    peak=float(obj['peak']),
                    a=float(obj['a']),
                    b=float(obj['b']),
                    theta=float(obj['theta'])
                )
                for obj in objects
            ]

            # Create centroids array for plate solving
            centroids = np.column_stack([objects['x'], objects['y']])

            self._logger.info(
                f"Detected {len(stars)} stars "
                f"(brightest flux={stars[0].flux:.0f} ADU)"
            )

            return DetectionResult(
                stars=stars,
                centroids=centroids,
                background_mean=background_mean,
                background_rms=background_rms,
                detection_threshold=threshold_sigma,
                star_count=len(stars)
            )

        except Exception as e:
            self._logger.error(f"Star detection failed: {e}")
            return None

    def _prepare_array(self, data: np.ndarray) -> np.ndarray:
        """Prepare array for SEP processing.

        SEP requires:
        - Native byte order
        - C-contiguous memory layout
        - Float data type

        Args:
            data: Input numpy array.

        Returns:
            Prepared numpy array suitable for SEP.
        """
        # Convert to float64 for precision
        result = np.asarray(data, dtype=np.float64)

        # Ensure native byte order
        if result.dtype.byteorder not in ('=', '|', '<' if np.little_endian else '>'):
            result = result.astype(result.dtype.newbyteorder('='))

        # Ensure C-contiguous
        if not result.flags['C_CONTIGUOUS']:
            result = np.ascontiguousarray(result)

        return result

    @staticmethod
    def is_available() -> bool:
        """Check if SEP library is available.

        Returns:
            True if SEP is available, False otherwise.
        """
        return SEP_AVAILABLE
