# lib/abstract_importer.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from Lib.dataset.dataset import DataSet


class AbstractImporter(ABC):
    """Abstract base class for all importers"""

    # These should be overridden by each importer
    REQUIRED_HEADERS: List[str] = []
    PARTIAL_MATCH: bool = False

    @classmethod
    @abstractmethod
    def get_save_as_name(cls) -> str:
        """Return the name to save the file as"""
        pass

    @classmethod
    def check_headers(cls, headers: List[str]) -> bool:
        """
        Check if the headers match this importer's requirements.

        Args:
            headers: List of headers from the Excel file

        Returns:
            bool: True if headers match requirements, False otherwise
        """
        headers_lower = {h.lower().strip() for h in headers}
        required_lower = {h.lower().strip() for h in cls.REQUIRED_HEADERS}

        if cls.PARTIAL_MATCH:
            # All required headers must be present, but additional headers are allowed
            return required_lower.issubset(headers_lower)
        else:
            # Headers must match exactly (same headers, no more, no less)
            return headers_lower == required_lower

    @abstractmethod
    def extract_data(self, file_path: Path, dataset: DataSet) -> None:
        """Extract data from the file into the dataset"""
        pass
