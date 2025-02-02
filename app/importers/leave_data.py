import loggingfrom datetime import datetime
from pathlib import Path

import pandas as pd

from app.abstract_importer import AbstractImporter
from app.dataset.dataset import DataSet, Leave, LeaveType, LeaveStatus


class LeaveDataImporter(AbstractImporter):
    """Importer for leave data information with updated Excel format"""

    REQUIRED_HEADERS = ['Employee_Code', 'Employee_Name', 'Shift_Type', 'Start_Time', 'End_Time', 'Status']
    PARTIAL_MATCH = True

    @classmethod
    def get_save_as_name(cls) -> str:
        return "leave_data.xlsx"

    def extract_data(self, file_path: Path, dataset: DataSet) -> None:

        if not file_path.exists():
            print(f"Leave data file not found at: {file_path}")
            return

        try:
            df = pd.read_excel(file_path)

            # Check if required headers are present
            missing_headers = [header for header in self.REQUIRED_HEADERS if header not in df.columns]
            if missing_headers:
                print(f"Missing required headers: {missing_headers}")
                return

            # Convert timestamps and filter future leave
            df['Start_Time'] = pd.to_datetime(df['Start_Time'])
            df['End_Time'] = pd.to_datetime(df['End_Time'])

            current_date = pd.Timestamp(datetime.now().date())
            df = df[df['Start_Time'] >= current_date]

            # Track employees we've already warned about
            warned_employees = set()
            warned_leave_types = set()
            warned_statuses = set()

            # Process each leave entry
            processed_count = 0
            for _, row in df.iterrows():
                employee_code = str(row['Employee_Code']).strip()

                if employee_code not in dataset.employees:
                    if employee_code not in warned_employees:
                        print(f"Employee code {employee_code} not found in dataset")
                        warned_employees.add(employee_code)
                    continue

                # Use the existing LeaveType.from_name method
                leave_type = LeaveType.from_name(str(row['Shift_Type']).strip())
                if leave_type is None:
                    leave_type_str = row['Shift_Type'].strip()
                    if leave_type_str not in warned_leave_types:
                        print(f"Unknown Leave Type: '{leave_type_str}'")
                        warned_leave_types.add(leave_type_str)
                    continue

                # Map status
                status = LeaveStatus.from_name(row['Status'].strip())
                if status is None:
                    status_str = row['Status'].strip()
                    if status_str not in warned_statuses:
                        print(f"Unknown status '{status_str}'; defaulting to Requested")
                        warned_statuses.add(status_str)
                    status = LeaveStatus.REQUESTED

                # Process the leave dates
                start_time = pd.to_datetime(row['Start_Time'])
                end_time = pd.to_datetime(row['End_Time'])
                leave_dates = pd.date_range(start=start_time.date(), end=end_time.date()).date

                # Calculate hours (assuming 7.6 hours per day for full days)
                total_duration = (end_time - start_time).total_seconds() / 3600
                hours_per_day = min(total_duration / len(leave_dates), 7.6)

                employee = dataset.employees[employee_code]
                for leave_day in leave_dates:
                    leave_entry = Leave(
                        date=leave_day,
                        status=status,
                        requested_at=datetime.now(),
                        hours=hours_per_day,
                        leave_type=leave_type
                    )
                    employee.add_leave(leave_entry)
                    processed_count += 1

            print(f"Leave import completed. Processed {processed_count} leave entries.")

        except Exception as e:
            print(f"Error processing leave data: {str(e)}")
            import traceback
            print(traceback.format_exc())
