# lib/importers/employee_shift_data.py
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from Lib.abstract_importer import AbstractImporter
from Lib.dataset.dataset import (
    DataSet, Employee, EmploymentType, ContractStatus,
    Shift, WorkArea
)


class EmployeeShiftDataImporter(AbstractImporter):
    """Combined importer for both employee roster and shift data"""

    REQUIRED_HEADERS = [
        # Employee headers
        'Employee',
        'Employee Code',
        'Employee Roster Name',
        'Employment Type',
        # Shift headers
        'End Time',
        'Non Attended',
        'Role',
        'Location',
        'Date',
        'Department',
        'Start Time',
        'Published',
        'Comments'
    ]
    PARTIAL_MATCH = True

    IGNORE_KEYWORDS = ["DNR", "UNABLE", "CANCELLED", "NOT WORKED"]

    @classmethod
    def get_save_as_name(cls) -> str:
        return "employee_shift_data.xlsx"

    def extract_data(self, file_path: Path, dataset: DataSet) -> None:
        """Extract both employee and shift data in two passes"""
        logger = logging.getLogger(__name__)
        df = pd.read_excel(file_path)

        # First pass: Create all employees
        self._import_employees(df, dataset)

        # Second pass: Create and assign shifts
        self._import_shifts(df, dataset)

    def _import_employees(self, df: pd.DataFrame, dataset: DataSet) -> None:
        """First pass: Import all employees"""
        logger = logging.getLogger(__name__)

        for _, row in df.iterrows():
            name = str(row['Employee']).strip() if pd.notna(row['Employee']) else ""
            roster_code = str(row['Employee Roster Name']).strip() if pd.notna(row['Employee Roster Name']) else ""

            # Skip if no name or roster code
            if not name or not roster_code:
                continue

            # Skip ignored employees
            if any(keyword in name.upper() for keyword in self.IGNORE_KEYWORDS):
                continue

            employee_code = row['Employee Code']
            if not pd.notna(employee_code):
                continue

            # Only create employee if they don't already exist
            if employee_code not in dataset.employees:
                employment_type = EmploymentType.from_name(row['Employment Type'])
                contract_status = ContractStatus.from_roster_name(roster_code)

                employee = Employee(name, employee_code, roster_code, employment_type, contract_status)
                dataset.add_employee(employee)

    def _import_shifts(self, df: pd.DataFrame, dataset: DataSet) -> None:
        """Second pass: Import all shifts"""
        logger = logging.getLogger(__name__)
        unassigned_shift_count = 0

        for _, row in df.iterrows():
            # Create WorkArea
            location = str(row['Location']).strip()
            department = str(row['Department']).strip()
            role = str(row['Role']).strip()
            work_area = WorkArea(location, department, role)

            # Parse shift times
            try:
                date_str = str(row['Date']).split(" ")[0]
                start_datetime = datetime.fromisoformat(f"{date_str}T{row['Start Time']}")
                end_datetime = datetime.fromisoformat(f"{date_str}T{row['End Time']}")
                if end_datetime < start_datetime:
                    end_datetime += timedelta(days=1)
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing dates for row: {e}")
                continue

            # Create shift
            shift = Shift(
                start=start_datetime,
                end=end_datetime,
                work_area=work_area,
                published=bool(row['Published']),
                comment=row['Comments'],
                is_attended=not bool(row['Non Attended']),
                pay_cycle=Shift.calculate_pay_cycle(start_datetime)
            )

            # Assign shift
            employee_code = row['Employee Code']
            if pd.notna(employee_code) and employee_code in dataset.employees:
                dataset.employees[employee_code].add_shift(shift)
            else:
                dataset.add_unassigned_shift(shift)
                unassigned_shift_count += 1

        logger.info(f"Unassigned Shifts Imported: {unassigned_shift_count}")