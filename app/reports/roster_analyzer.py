import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from ..dataset.rules_engine import RulesEngine


class RosterAnalyzer:
    MIN_SHIFTS_FOR_EMAIL = 3  # Minimum number of shifts required for email

    def __init__(self, dataset):
        self.dataset = dataset
        self.report_folder = Path("Humanforce Reports")
        self.report_folder.mkdir(exist_ok=True)

    def generate_shift_analysis_report(self, filename: str) -> Dict[str, List[dict]]:
        """
        Generate shift analysis report and return eligible shifts for employees with sufficient shifts

        Args:
            filename: Name of the Excel report file to generate

        Returns:
            Dictionary of eligible shifts by employee (only for those with >= MIN_SHIFTS_FOR_EMAIL shifts)
        """
        output_path = self.report_folder / filename

        # Remove existing file if it exists
        if output_path.exists():
            try:
                os.remove(output_path)
            except Exception as e:
                print(f"Error removing existing file: {str(e)}")

        # Get eligible shifts for all employees
        all_eligible_shifts = self._get_all_eligible_shifts()

        # Filter out employees with insufficient shifts
        filtered_eligible_shifts = {
            emp_name: shifts
            for emp_name, shifts in all_eligible_shifts.items()
            if len(shifts) >= self.MIN_SHIFTS_FOR_EMAIL
        }

        try:
            # Generate Excel report with all eligible shifts (including those below threshold)
            self._generate_excel_report(output_path, all_eligible_shifts)
            print(f"Generated report at {output_path}")

            # Return only shifts for employees meeting the minimum threshold
            if filtered_eligible_shifts:
                print(f"Found {len(filtered_eligible_shifts)} employees with {self.MIN_SHIFTS_FOR_EMAIL}+ eligible shifts")
            else:
                print(f"No employees found with {self.MIN_SHIFTS_FOR_EMAIL}+ eligible shifts")

            return filtered_eligible_shifts

        except Exception as e:
            print(f"Error generating Excel report: {str(e)}")
            raise

    def _get_all_eligible_shifts(self) -> Dict[str, List[dict]]:
        """Get all eligible shifts for all employees"""
        eligible_shifts = {}

        for emp in self.dataset.employees.values():
            emp_eligible = self._get_eligible_shifts(emp)
            if emp_eligible:  # Only include employees with any eligible shifts
                # Sort shifts by date and start time
                sorted_shifts = sorted(emp_eligible,
                                       key=lambda x: (datetime.strptime(x['Date'], '%d/%m'), x['Start']))
                eligible_shifts[emp.name] = sorted_shifts

        return eligible_shifts

    def _generate_excel_report(self, output_path: Path, eligible_shifts: Dict[str, List[dict]]) -> None:
        """Generate Excel report with eligible shifts"""
        with pd.ExcelWriter(output_path, engine='openpyxl', mode='w') as writer:
            if not eligible_shifts:
                pd.DataFrame({"Status": ["No eligible shifts found"]}).to_excel(
                    writer,
                    sheet_name="No Data",
                    index=False
                )
            else:
                # Create summary sheet
                summary_data = []
                for emp_name, shifts in eligible_shifts.items():
                    summary_data.append({
                        'Employee': emp_name,
                        'Number of Eligible Shifts': len(shifts),
                        'Email Status': 'Will be sent' if len(shifts) >= self.MIN_SHIFTS_FOR_EMAIL else 'Insufficient shifts'
                    })

                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)

                # Individual employee sheets
                for emp_name, shifts in eligible_shifts.items():
                    df = pd.DataFrame(shifts)
                    sheet_name = emp_name[:31]  # Excel sheet name limit
                    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)

                    # Add employee name header and email status
                    worksheet = writer.sheets[sheet_name]
                    email_status = 'Will receive email' if len(shifts) >= self.MIN_SHIFTS_FOR_EMAIL else f'No email (minimum {self.MIN_SHIFTS_FOR_EMAIL} shifts required)'
                    worksheet.cell(row=1, column=1, value=f"Eligible Shifts for: {emp_name} - {email_status}")

    def _get_eligible_shifts(self, emp) -> List[dict]:
        """Get eligible shifts for an employee"""
        engine = RulesEngine(emp)
        eligible_shifts = []

        for shift in self.dataset.combined_unfilled_shifts:
            # Skip unpaid breaks
            if "UNPAID BREAK" in shift.work_area.role.upper():
                continue

            if engine.can_offer_shift(shift):
                formatted_shift = self._format_shift(shift, emp)
                eligible_shifts.append(formatted_shift)

        return eligible_shifts

    def _format_shift(self, shift, emp) -> dict:
        """Format shift information for report and email"""
        department = self._clean_department(shift.work_area.department)
        role = self._clean_role(shift.work_area.role)
        existing_hours = self._calculate_existing_hours(emp, shift.start.date())

        return {
            'Location': shift.work_area.location,
            'Department': department,
            'Role': role,
            'Weekday': shift.start.strftime('%a'),
            'Date': shift.start.strftime('%d/%m'),
            'Start': shift.start.strftime('%H%M'),
            'End': shift.end.strftime('%H%M'),
            'Current Hours': existing_hours,
            'WeekNum': shift.week_num
        }

    def _clean_department(self, department: str) -> str:
        """Clean department name based on rules"""
        # Remove content in brackets including brackets
        department = re.sub(r'\([^)]*\)', '', department)
        department = department.strip()

        if "ENGAGE" in department:
            return "ENGAGE"

        if "ACC" in department:
            parts = department.split("-")
            return parts[-1].strip()

        return department

    def _clean_role(self, role: str) -> str:
        """Clean role name based on rules"""
        # Remove content in brackets including brackets
        role = re.sub(r'\([^)]*\)', '', role)
        # Remove numbers
        role = re.sub(r'\d+', '', role)

        # Handle hyphens
        if "-" in role:
            parts = role.split("-")
            role = parts[0]

        return role.strip()

    def _calculate_existing_hours(self, emp, date) -> float:
        """Calculate total hours already worked on a given date"""
        total_hours = sum(
            shift.net_hours
            for shift in emp.shifts
            if shift.start.date() == date
            and "UNPAID BREAK" not in shift.work_area.role.upper()
        )
        return total_hours if total_hours > 0 else None
