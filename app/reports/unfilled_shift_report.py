from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill

from app.reportlogger import report_logger
from app.reports.shift_change_tracker import ShiftChangeTracker


class UnfilledShiftReport:
    PRIORITIES = {
        'critical': {'max_days': 2, 'color': 'FF0000'},  # Red
        'urgent': {'max_days': 5, 'color': '000000'},    # Black
        'standard': {'max_days': 8, 'color': '000000'}   # Black
    }

    def __init__(self, dataset):
        self.dataset = dataset
        self.report_path = Path("Humanforce Reports")
        self.ensure_report_directory()
        self.working_days_ahead = 8
        self.shift_tracker = ShiftChangeTracker()

    def ensure_report_directory(self):
        """Ensure the report directory exists."""
        self.report_path.mkdir(parents=True, exist_ok=True)

    def is_working_day(self, date):
        """Check if the given date is a working day (not weekend)."""
        return date.weekday() < 5  # 0-4 are Monday to Friday

    def get_next_working_days(self, start_date, num_working_days):
        """Get a list of the next N working days."""
        working_days = []
        current_date = start_date
        while len(working_days) < num_working_days:
            if self.is_working_day(current_date):
                working_days.append(current_date)
            current_date += timedelta(days=1)
        return working_days

    def get_priority(self, shift_date):
        """Determine priority based on working days ahead."""
        today = datetime.now().date()
        working_days_until = sum(1 for d in self.get_next_working_days(today, self.working_days_ahead)
                                 if d <= shift_date and self.is_working_day(d))

        if working_days_until <= self.PRIORITIES['critical']['max_days']:
            return 'critical'
        elif working_days_until <= self.PRIORITIES['urgent']['max_days']:
            return 'urgent'
        else:
            return 'standard'

    def get_escalation_status(self, comment):
        """
        Return the escalation status based on keywords in the comment.
        Checks first 5 lines of comments for escalation status indicators.
        """
        import re

        if comment is None or pd.isna(comment) or not isinstance(comment, str):
            return "Not Escalated"

        # Get first 5 lines of the comment
        lines = str(comment).split('\n')[:5]

        # Patterns for detecting escalated status
        escalated_patterns = [
            r'\besc\b',
            r'\bescalated\b',
            r'\besclated\b',
            r'\beskalated\b',
        ]

        # Patterns for detecting ready to escalate status
        ready_patterns = [
            r'ready.*(?:esc|escalate)',
            r'(?:ready|rdy).*(?:2|to).*(?:esc|escalate)',
        ]

        # Compile all patterns (case insensitive)
        escalated_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in escalated_patterns]
        ready_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in ready_patterns]

        # Check each line against our patterns
        for line in lines:
            # Check escalated patterns first (takes precedence)
            if any(pattern.search(line) for pattern in escalated_patterns):
                return "Escalated"

        # If not escalated, check ready patterns
        for line in lines:
            if any(pattern.search(line) for pattern in ready_patterns):
                return "Ready to Escalate"

        return "Not Escalated"

    def format_date(self, date):
        """Format date in South Australian standard."""
        return date.strftime('%a, %d %b %Y')

    def generate_report(self):
        """Generate the unfilled shifts report in Excel format."""
        # First, let the tracker process the shifts - it will handle escalation notifications
        self.shift_tracker.process_shifts(self.dataset.unassigned_shifts)

        # Get working days range
        today = datetime.now().date()
        working_days = self.get_next_working_days(today, self.working_days_ahead)

        # Group shifts by location
        shifts_by_location = defaultdict(list)

        for shift in self.dataset.unassigned_shifts:
            shift_date = shift.start.date()
            # Only include shifts on working days within our range
            if shift_date in working_days:
                priority = self.get_priority(shift_date)

                shifts_by_location[shift.work_area.location].append({
                    'Department': shift.work_area.department,
                    'Start Date': shift_date,
                    'Start Time': shift.start.strftime('%H:%M'),
                    'End Time': shift.end.strftime('%H:%M'),
                    'Role': shift.work_area.role,
                    'Priority': priority.title(),
                    'Color': self.PRIORITIES[priority]['color'],
                    'Escalation Status': self.get_escalation_status(shift.comment)
                })

        if not shifts_by_location:
            report_logger.info("No unfilled shifts found for the next 8 working days.")
            return None

        # Create Excel writer with datetime in filename
        current_time = datetime.now().strftime('%d %b')
        excel_path = self.report_path / f'Unfilled Shifts Report {current_time}.xlsx'

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            for location, shifts in shifts_by_location.items():
                if not shifts:
                    continue

                # Convert shifts to DataFrame
                df = pd.DataFrame(shifts)

                # Convert Start Date to datetime and create a combined datetime field
                df['Start Date'] = pd.to_datetime(df['Start Date'])
                df['Start DateTime'] = df.apply(lambda x: x['Start Date'].replace(
                    hour=int(x['Start Time'].split(':')[0]),
                    minute=int(x['Start Time'].split(':')[1])
                ), axis=1)

                # Calculate average start time per department for sorting
                dept_avg_times = df.groupby('Department')['Start DateTime'].mean().reset_index()
                dept_avg_times = dept_avg_times.sort_values('Start DateTime')

                # Create a department rank for sorting
                dept_order = {dept: idx for idx, dept in enumerate(dept_avg_times['Department'])}
                df['Dept_Rank'] = df['Department'].map(dept_order)

                # Sort and format
                df = df.sort_values(['Dept_Rank', 'Start Date', 'Start Time'])
                df = df.drop(['Start DateTime', 'Dept_Rank'], axis=1)
                df['Start Date'] = df['Start Date'].apply(self.format_date)

                # Prepare Excel version of dataframe
                df_excel = df.drop(['Color'], axis=1)
                column_order = ['Priority', 'Department', 'Role', 'Start Date', 'Start Time', 'End Time', 'Escalation Status']
                df_excel = df_excel[column_order]

                sheet_name = f"{str(location)[:25]} ({len(shifts)})"[:31]
                df_excel.to_excel(writer, sheet_name=sheet_name, index=False)

                # Format worksheet
                worksheet = writer.sheets[sheet_name]
                self._format_worksheet(worksheet, df)

        report_logger.info(f"\nExcel report generated: {excel_path}")
        return excel_path

    def _format_worksheet(self, worksheet, df):
        """Apply formatting to the worksheet with consistent row coloring."""
        # Format header row with bold black text
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color='000000')

        # Format data rows based on priority
        for excel_row, row in enumerate(worksheet.iter_rows(min_row=2), start=2):
            # Find the priority of this row from the first column (Priority column)
            priority_cell_value = row[0].value  # Priority is in the first column

            # Default to black
            row_color = '000000'

            # Only set to red if it's explicitly a Critical priority
            if priority_cell_value == 'Critical':
                row_color = 'FF0000'

            # Apply the same color to all cells in the row
            for cell in row:
                cell.font = Font(color=row_color, bold=False)
                cell.fill = PatternFill(fill_type=None)
                cell.border = None

        # Auto-size columns
        for column_cells in worksheet.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2