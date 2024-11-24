import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.abstract_importer import AbstractImporter
from app.dataset.dataset import DataSet, Leave, LeaveType, LeaveStatus


class LeaveDataImporter(AbstractImporter):
    """Importer for leave data information with updated Excel format"""

    REQUIRED_HEADERS = [
        'Employee_Code',
        'Employee_Name',
        'Shift_Type',
        'Start_Time',
        'End_Time',
        'Status'
    ]
    PARTIAL_MATCH = True

    @classmethod
    def get_save_as_name(cls) -> str:
        return "leave_data.xlsx"

    def extract_data(self, file_path: Path, dataset: DataSet) -> None:
        logger = logging.getLogger(__name__)
        df = pd.read_excel(file_path)

        # Filter to only process future leave
        df['Start_Time'] = pd.to_datetime(df['Start_Time'])
        df = df[df['Start_Time'] >= pd.Timestamp(datetime.now().date())]

        for _, row in df.iterrows():
            employee_code = str(row['Employee_Code']).strip()
            if employee_code not in dataset.employees:
                logger.warning(f"Employee code {employee_code} not found in dataset; leave entry skipped.")
                continue

            # Use the existing LeaveType.from_name method
            leave_type = LeaveType.from_name(str(row['Shift_Type'].trim()))
            if leave_type is None:
                logger.error(f"Unknown Leave Type: '{row['Shift_Type'].trim()}' for Employee Code: {employee_code}")
                continue

            # Map status
            status = LeaveStatus.from_name(row['Status'].trim())
            if status is None:
                logger.warning(f"Unknown status '{row['Status'].trim()}' for Employee Code: {employee_code}; defaulting to Requested")
                status = LeaveStatus.REQUESTED

            # Calculate hours from start and end time
            start_time = pd.to_datetime(row['Start_Time'])
            end_time = pd.to_datetime(row['End_Time'])
            hours = round(min((end_time - start_time).total_seconds() / 3600, 7.6), 2)

            # Process each day in the leave range
            leave_dates = pd.date_range(start=start_time.date(), end=end_time.date()).date

            employee = dataset.employees[employee_code]
            for leave_day in leave_dates:
                leave_entry = Leave(
                    date=leave_day,
                    status=status,
                    requested_at=datetime.now(),  # Since we don't have this in new format, use current time
                    hours=hours,
                    leave_type=leave_type
                )
                employee.add_leave(leave_entry)
