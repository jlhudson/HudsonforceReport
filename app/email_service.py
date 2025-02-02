import re
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Dict, List


class EmailService:
    def __init__(self, template_path: str):
        """Initialize EmailService with required template path"""
        if not template_path:
            raise ValueError("Template path is required")

        self.outlook = None
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

    def _format_weekday_with_week(self, weekday: str, week_num: int) -> str:
        """Format weekday with week number"""
        # Extract first three letters of weekday and capitalize
        day_abbrev = weekday[:3].capitalize()
        return f"{day_abbrev}-Wk{week_num}"

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

            required_placeholders = ['{first_name}', '{shift_list}']
            missing_placeholders = [p for p in required_placeholders if p not in self.template]
            if missing_placeholders:
                print(f"Template is missing required placeholders: {', '.join(missing_placeholders)}")
                sys.exit(1)

        except Exception as e:
            print(f"Error loading template: {e}")
            sys.exit(1)

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

    def _format_shift_list(self, shifts: List[dict]) -> str:
        """Format shifts into an HTML table format"""
        if not shifts:
            return "<tr><td colspan='7' style='border: 1px solid black; text-align: center;'>No shifts available</td></tr>"

        shift_lines = []
        for shift in shifts:
            # Clean department and role
            department = self._clean_department(shift['Department'])
            role = self._clean_role(shift['Role'])

            # Format the time range
            time_range = f"{shift['Start']}-{shift['End']}"

            # Format weekday with week number
            weekday_with_week = self._format_weekday_with_week(shift['Weekday'], shift['WeekNum'])

            # Create a row with consistent styling
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

        email_content = self.template.format(
            first_name=first_name,
            shift_list=shift_list
        )

        print("\n" + "=" * 50)
        print(f"Email Preview for: {emp_name}")
        print("=" * 50)
        print(email_content)
        print("=" * 50)

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

            email_body = self.template.format(
                first_name=first_name,
                shift_list=shift_list
            )

            mail = self.outlook.CreateItem(0)  # 0 = olMailItem

            # Calculate send time
            current_time = datetime.now()
            today_9am = current_time.replace(hour=9, minute=0, second=0, microsecond=0)

            # If it's before 9 AM, send today at 9 AM
            # If it's after 9 AM, send tomorrow at 9 AM
            if current_time < today_9am:
                send_time = today_9am
            else:
                send_time = today_9am + timedelta(days=1)

            # Get current month and next month for subject line
            current_month = current_time.strftime('%b')
            next_month = (current_time.replace(day=1) + timedelta(days=32)).strftime('%b')

            mail.Subject = f"Shift Offers Limestone Coast {current_month} - {next_month} {current_time.year}"
            mail.HTMLBody = email_body
            mail.To = email_address
            mail.CC = "james.hudson89@gmail.com"
            mail.SentOnBehalfOfName = "james.hudson89@gmail.com"

            # Set the deferred delivery time
            mail.DeferredDeliveryTime = send_time

            # Save as draft
            mail.Save()

            print(f"Draft email created for {emp_name} - Scheduled to send at {send_time.strftime('%Y-%m-%d %H:%M')}")

        except Exception as e:
            print(f"Error creating draft email for {emp_name}: {e}")
            sys.exit(1)