# lib/importers/employee_shift_data.py
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from app.abstract_importer import AbstractImporter
from app.dataset.dataset import (DataSet, Employee, EmploymentType, ContractStatus, Shift, WorkArea)


class EmployeeShiftDataImporter(AbstractImporter):
    """Combined importer for both employee roster and shift data"""

    REQUIRED_HEADERS = [  # Employee headers
        'Employee', 'Employee Code', 'Employee Roster Name', 'Employment Type', 'Email',
        # Shift headers
        'End Time', 'Non Attended', 'Role', 'Location', 'Date', 'Department', 'Start Time', 'Published', 'Comments']
    PARTIAL_MATCH = True

    IGNORE_KEYWORDS = ["DNR", "UNABLE", "CANCELLED", "NOT WORKED"]

    @classmethod
    def get_save_as_name(cls) -> str:
        return "employee_shift_data.xlsx"

    def extract_data(self, file_path: Path, dataset: DataSet) -> None:
        """Extract both employee and shift data in two passes"""
        df = pd.read_excel(file_path)

        # First pass: Create all employees
        self._import_employees(df, dataset)

        # Second pass: Create and assign shifts
        self._import_shifts(df, dataset)

    def _import_employees(self, df: pd.DataFrame, dataset: DataSet) -> None:
        """First pass: Import all employees"""
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

            # Get email if available
            email = str(row['Email']).strip() if pd.notna(row.get('Email')) else None

            # Only create employee if they don't already exist
            if employee_code not in dataset.employees:
                employment_type = EmploymentType.from_name(row['Employment Type'])
                contract_status = ContractStatus.from_roster_name(roster_code)

                # Parse name components
                name_parts = Employee.parse_name(name)
                first_name, last_name, full_name = name_parts[0], name_parts[1], name_parts[2]

                employee = Employee(
                    name=full_name,
                    employee_code=employee_code,
                    roster_code=roster_code,
                    employment_type=employment_type,
                    contract_status=contract_status,
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )
                dataset.add_employee(employee)
            elif email and not dataset.employees[employee_code].email:
                # Update email if it wasn't previously set
                dataset.employees[employee_code].email = email

    def _import_shifts(self, df: pd.DataFrame, dataset: DataSet) -> None:
        """Second pass: Import all shifts"""
        unassigned_shift_count = 0
        filtered_shift_count = 0
        cutoff_filtered_count = 0

        for _, row in df.iterrows():
            try:
                # Create WorkArea
                location = str(row['Location']).strip()
                department = str(row['Department']).strip()
                role = str(row['Role']).strip()
                work_area = WorkArea(location, department, role)

                # Parse shift times
                date_str = str(row['Date']).split(" ")[0]
                start_datetime = datetime.fromisoformat(f"{date_str}T{row['Start Time']}")
                end_datetime = datetime.fromisoformat(f"{date_str}T{row['End Time']}")

                # Handle shifts that cross midnight
                if end_datetime < start_datetime:
                    end_datetime += timedelta(days=1)

                # Skip shifts after cutoff date
                if dataset.cutoff_date and start_datetime >= dataset.cutoff_date:
                    cutoff_filtered_count += 1
                    continue

                # Create shift (PayCycle and WeekNum will be calculated automatically)
                shift = Shift(
                    start=start_datetime,
                    end=end_datetime,
                    work_area=work_area,
                    published=bool(row['Published']),
                    comment=str(row['Comments']) if pd.notna(row['Comments']) else "",
                    is_attended=not bool(row['Non Attended']),
                    pay_cycle=None  # Will be calculated based on Oct 1, 2024 reference date
                )

                # Process employee assignment
                employee_code = row['Employee Code']
                employee_name = str(row['Employee']).strip() if pd.notna(row['Employee']) else ""

                # Handle unassigned shifts
                if not pd.notna(employee_code) or not employee_name:
                    dataset.add_unassigned_shift(shift)
                    unassigned_shift_count += 1
                    continue

                # Skip shifts for ignored employees
                if any(keyword in employee_name.upper() for keyword in self.IGNORE_KEYWORDS):
                    filtered_shift_count += 1
                    continue

                # Add shift to employee if they exist
                if employee_code in dataset.employees:
                    if dataset.add_shift_to_employee(dataset.employees[employee_code], shift):
                        continue
                    else:
                        cutoff_filtered_count += 1
                else:
                    filtered_shift_count += 1

            except (ValueError, TypeError) as e:
                print(f"Error processing shift row: {e}")
                continue

        # Log import statistics
        print(f"Unassigned Shifts Imported: {unassigned_shift_count}")
        print(f"Filtered Employee Shifts Skipped: {filtered_shift_count}")
        print(f"Shifts filtered due to cutoff date: {cutoff_filtered_count}")

        # Additional validation
        if unassigned_shift_count == 0 and filtered_shift_count == 0:
            print("No shifts were imported. This might indicate a data issue.")
