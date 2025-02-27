import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


class EmailService:
    def __init__(self, template_path: str):
        """Initialize EmailService with required template path"""
        if not template_path:
            raise ValueError("Template path is required")

        self.outlook = None
        self.template = ""
        try:
            import win32com.client
            self.outlook = win32com.client.Dispatch("Outlook.Application")
        except ImportError:
            print("win32com not found. To install, run: pip install pywin32")
            sys.exit(1)
        except Exception as e:
            print(f"Error initializing Outlook: {e}")
            sys.exit(1)

        # Load template
        self.load_template(template_path)

    def load_template(self, template_path: str) -> None:
        """Load HTML email template from file"""
        try:
            template_file = Path(template_path)
            if not template_file.exists():
                print(f"Template file not found: {template_path}")
                sys.exit(1)

            with open(template_file, 'r', encoding='utf-8') as f:
                self.template = f.read()

            print(f"Successfully loaded email template from {template_path}")

            required_placeholders = ['{first_name}', '{shift_list}', '{review_date}']
            missing_placeholders = [p for p in required_placeholders if p not in self.template]
            if missing_placeholders:
                print(f"Template is missing required placeholders: {', '.join(missing_placeholders)}")
                sys.exit(1)

        except Exception as e:
            print(f"Error loading template: {e}")
            sys.exit(1)

    def _format_weekday_with_week(self, weekday: str, week_num: int) -> str:
        """Format weekday with week number"""
        day_abbrev = weekday[:3].capitalize()
        return f"{day_abbrev}-Wk{week_num}"

    def _clean_role(self, role: str) -> str:
        """Clean role name based on rules"""
        role = re.sub(r'\([^)]*\)', '', role)
        role = re.sub(r'\d+', '', role)
        if "-" in role:
            parts = role.split("-")
            role = parts[0]
        return role.strip()

    def _clean_department(self, department: str) -> str:
        """Clean department name based on rules"""
        department = re.sub(r'\([^)]*\)', '', department)
        department = department.strip()

        if "ENGAGE" in department:
            return "ENGAGE"
        if "ACC" in department:
            parts = department.split("-")
            return parts[-1].strip()
        return department

    def _format_shift_list(self, shifts: List[dict]) -> str:
        """Format shifts into an HTML table format"""
        if not shifts:
            return "<tr><td colspan='6' style='border: 1px solid black; text-align: center;'>No shifts available</td></tr>"

        shift_lines = []
        for shift in shifts:
            department = self._clean_department(shift['Department'])
            role = self._clean_role(shift['Role'])
            time_range = f"{shift['Start']}-{shift['End']}"
            weekday_with_week = self._format_weekday_with_week(shift['Weekday'], shift['WeekNum'])

            row = f'''    <tr>
        <td style="border: 1px solid black; text-align: left; padding: 2px 5px;">{department}</td>
        <td style="border: 1px solid black; text-align: left; padding: 2px 5px;">{role}</td>
        <td style="border: 1px solid black; text-align: left; padding: 2px 5px;">{weekday_with_week}</td>
        <td style="border: 1px solid black; text-align: left; padding: 2px 5px;">{shift['Date']}</td>
        <td style="border: 1px solid black; text-align: left; padding: 2px 5px;">{time_range}</td>
        <td style="border: 1px solid black; text-align: center; padding: 2px 5px;"></td>
    </tr>'''
            shift_lines.append(row)

        return "\n".join(shift_lines)

    def _calculate_review_date(self) -> str:
        """Calculate the review date:
        - Minimum 48 hours from now
        - Must be at 17:00 (5:00 PM)
        - Must be Monday-Friday
        - If lands on weekend, add 24 hours until it's a weekday
        """
        current_date = datetime.now()

        # Add minimum 48 hours
        review_date = current_date + timedelta(hours=48)

        # Set to 17:00 (5:00 PM)
        review_date = review_date.replace(hour=16, minute=30, second=0, microsecond=0)

        # If it's past 17:00 today, move to next day
        if current_date.hour >= 17:
            review_date += timedelta(days=1)

        # Keep adding 24 hours until we land on a weekday (Monday=0 ... Friday=4)
        while review_date.weekday() > 4:  # While it's Saturday(5) or Sunday(6)
            review_date += timedelta(days=1)

        return review_date.strftime("%A, %d/%m/%Y at %H%M")

    def _calculate_send_time(self) -> datetime:
        """Calculate the next business day send time at 9 AM"""
        current_time = datetime.now()

        # Start with today at 9 AM
        send_time = current_time.replace(hour=9, minute=0, second=0, microsecond=0)

        # If current time is after 9 AM, move to tomorrow
        if send_time <= current_time:
            send_time += timedelta(days=1)

        # Skip weekends (Monday-Friday are 0-4)
        while send_time.weekday() > 4:
            send_time += timedelta(days=1)

        return send_time

    def process_shift_emails(self, eligible_shifts: Dict[str, List[dict]], employee_data: dict) -> None:
        """Process and create draft emails for eligible shifts"""
        for emp_name, shifts in eligible_shifts.items():
            if self._display_email_preview(emp_name, shifts):
                if self.outlook:
                    self._create_draft_email(emp_name, shifts, employee_data.get(emp_name, {}).get('email'))

    def _display_email_preview(self, emp_name: str, shifts: List[dict]) -> bool:
        """Display email preview and get user confirmation"""
        first_name = emp_name.split(' ')[0]
        shift_list = self._format_shift_list(shifts)
        review_date = self._calculate_review_date()

        email_content = self.template.format(
            first_name=first_name,
            shift_list=shift_list,
            review_date=review_date
        )

        print("\n" + "=" * 50)
        print(f"Email Preview for: {emp_name}")

        if self.outlook:
            response = input("Press Enter to create draft email or 'n' to skip: ").lower()
            return response != 'n'
        else:
            input("Press Enter to continue to next preview (Outlook not available)...")
            return False

    def _create_draft_email(self, emp_name: str, shifts: List[dict], email_address: str = None) -> None:
        """Create a draft email in Outlook Desktop with send later feature for next 9:00 AM"""
        try:
            if not self.outlook:
                raise Exception("Outlook not initialized")

            if not email_address:
                print(f"No email address found for {emp_name}")
                return

            first_name = emp_name.split(' ')[0]
            shift_list = self._format_shift_list(shifts)
            review_date = self._calculate_review_date()

            email_body = self.template.format(
                first_name=first_name,
                shift_list=shift_list,
                review_date=review_date
            )

            # Outlook expects local time in a specific COM-compatible format
            import win32com.client
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)

            current_time = datetime.now()

            current_month = current_time.strftime('%b')
            next_month = (current_time.replace(day=1) + timedelta(days=32)).strftime('%b')

            mail.Subject = f"Shift Offers, Limestone Coast {current_month} - {next_month} {current_time.year}"
            mail.HTMLBody = email_body
            mail.To = email_address
            mail.CC = "RosteringLimeStoneCoast@claust.com.au"
            mail.SentOnBehalfOfName = "RosteringLimeStoneCoast@claust.com.au"

            mail.Save()

            print(f"Draft email created for {emp_name}")

        except Exception as e:
            print(f"Error creating draft email for {emp_name}: {e}")
            sys.exit(1)
