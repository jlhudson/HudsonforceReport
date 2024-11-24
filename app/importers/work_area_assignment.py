import logging
from pathlib import Path

import pandas as pd

from app.abstract_importer import AbstractImporter
from app.dataset.dataset import DataSet, WorkArea


class WorkAreaAssignmentImporter(AbstractImporter):
    """Importer for employee work area assignments"""

    REQUIRED_HEADERS = [
        'Employee_Code',
        'Employee_Name',
        'Location',
        'Department',
        'Role'
    ]
    PARTIAL_MATCH = True

    @classmethod
    def get_save_as_name(cls) -> str:
        return "work_area_assignments.xlsx"

    def extract_data(self, file_path: Path, dataset: DataSet) -> None:
        """Extract work area assignments and add them to employees"""
        logger = logging.getLogger(__name__)
        df = pd.read_excel(file_path)

        # Process each row in the spreadsheet
        for _, row in df.iterrows():
            employee_code = str(row['Employee_Code']).strip()

            # Skip if employee not found in dataset
            if employee_code not in dataset.employees:
                # logger.warning(f"Employee code {employee_code} not found in dataset; work area assignment skipped.")
                continue

            # Create WorkArea object
            work_area = WorkArea(
                location=str(row['Location']).strip(),
                department=str(row['Department']).strip(),
                role=str(row['Role']).strip()
            )

            # Add work area to employee
            employee = dataset.employees[employee_code]
            employee.work_areas.add(work_area)  # Using set to automatically handle duplicates
