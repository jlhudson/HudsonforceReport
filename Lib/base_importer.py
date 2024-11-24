# lib/base_importer.py
import logging
import shutil
from pathlib import Path
from typing import Type

import pandas as pd

from Lib.dataset.dataset import DataSet
from Lib.dataset.dataset_reporter import DatasetReporter
from abstract_importer import AbstractImporter
# Import all importers
from importers.employee_shift_data import EmployeeShiftDataImporter
from importers.leave_data import LeaveDataImporter
from importers.work_area_assignment import WorkAreaAssignmentImporter


class BaseImporter:
    # List importers in priority order
    # Note: employee/shift data must be imported before leave data and work area assignments
    IMPORTERS = [
        EmployeeShiftDataImporter,  # First to create employees
        LeaveDataImporter,  # Requires employees to exist
        WorkAreaAssignmentImporter,  # Also requires employees to exist
    ]

    @classmethod
    def run_import(cls, dataset: DataSet) -> None:
        """Main method to run the import process"""
        logger = logging.getLogger(__name__)

        # Setup paths
        source_folder = Path(__file__).parent.parent / "Downloads"
        destination_folder = Path(__file__).parent.parent / "Humanforce Reports"
        destination_folder.mkdir(exist_ok=True)

        logger.info("Starting import process...")

        # Get all Excel files sorted by modification time (newest first)
        excel_files = []
        for ext in ['.xlsx', '.xls']:
            excel_files.extend(source_folder.glob(f'*{ext}'))

        excel_files = sorted(
            excel_files,
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        # Process each Excel file
        for file_path in excel_files:
            try:
                cls._process_file(file_path, destination_folder)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")

        # Now extract data from all matched files
        logger.info("Extracting data from matched files...")
        for importer_class in cls.IMPORTERS:
            try:
                cls._extract_data(importer_class, destination_folder, dataset)
            except Exception as e:
                logger.error(f"Error with {importer_class.__name__}: {str(e)}")

        # Generate comprehensive report
        report_path = destination_folder / "dataset_report.txt"
        try:
            DatasetReporter.generate_report(dataset, report_path)
            logger.info(f"Dataset report generated: {report_path}")
        except Exception as e:
            logger.error(f"Error generating dataset report: {str(e)}")

    @classmethod
    def _process_file(cls, file_path: Path, destination_folder: Path) -> None:
        """Process a single Excel file"""
        logger = logging.getLogger(__name__)

        try:
            # Read just the headers
            df = pd.read_excel(file_path, nrows=0)
            headers = df.columns.tolist()

            # Try each importer
            for importer_class in cls.IMPORTERS:
                if importer_class.check_headers(headers):
                    new_path = destination_folder / importer_class.get_save_as_name()
                    shutil.copy2(file_path, new_path)
                    logger.info(f"Matched and copied {file_path.name} as {new_path.name}")
                    break

        except Exception as e:
            logger.error(f"Error reading {file_path}: {str(e)}")

    @classmethod
    def _extract_data(cls, importer_class: Type[AbstractImporter],
                      destination_folder: Path, dataset: DataSet) -> None:
        """Extract data using the specified importer"""
        file_path = destination_folder / importer_class.get_save_as_name()
        if file_path.exists():
            importer = importer_class()
            importer.extract_data(file_path, dataset)
