# shift_change_tracker.py
import json
import re
from pathlib import Path

import win32com.client as win32


class ShiftChangeTracker:
    def __init__(self):
        self.storage_path = Path("Humanforce Reports") / "previous_shifts.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        # Initialize Outlook
        self.outlook = win32.Dispatch('Outlook.Application')

    def get_shift_key(self, shift):
        """Create a unique identifier for a shift."""
        return f"{shift.start.isoformat()}_{shift.end.isoformat()}_{shift.work_area.location}_{shift.work_area.department}_{shift.work_area.role}"

    def format_date(self, date):
        """Format date in the specified format."""
        return date.strftime('%a, %d %b %Y')

    def clean_comments(self, comment):
        """Clean up the comments by removing extra characters and normalizing line breaks."""
        if not comment:
            return ""

        # Replace various line ending characters and clean up
        cleaned = comment.replace('_x000d_', '\n')  # Replace _x000d_ with newline
        cleaned = re.sub(r'\*x000d\*', '\n', cleaned)  # Replace *x000d* with newline
        cleaned = re.sub(r'\s*\n\s*', '\n', cleaned)  # Remove extra spaces around newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Reduce multiple newlines to maximum of 2
        cleaned = cleaned.strip()  # Remove leading/trailing whitespace

        return cleaned

    def create_draft_email(self, shift):
        """Create a draft email for an escalated shift."""
        mail = self.outlook.CreateItem(0)  # 0 represents olMailItem

        # Set email properties
        mail.To = "rostering.southcoast@claust.com.au"
        shift_date = self.format_date(shift.start)
        mail.Subject = f"{shift.work_area.department}, {shift.work_area.role}, {shift_date}"

        # Clean up the comments
        cleaned_comments = self.clean_comments(shift.comment)
        comments_html = cleaned_comments.replace('\n', '<br>')

        # Create the HTML body with formatted text - with minimal spacing between elements
        body_parts = [
            "<div style='line-height:1.2'>",  # Reduce line height for the whole email
            "Hi @<br>",
            f"Please see below for Escalation for {shift_date}<br><br>",
            f"<span style='color:#FF0000;font-weight:bold'>{shift.work_area.location}</span><br>",
            f"<span style='color:#FF0000;font-weight:bold'>{shift.work_area.department}</span><br>",
            f"<span style='color:#FF0000;font-weight:bold'>{shift.work_area.role}</span><br>",
            f"<span style='color:#FF0000;font-weight:bold'>{shift_date}, {shift.start.strftime('%H:%M')} - {shift.end.strftime('%H:%M')}</span><br><br>",
            "<b>Notes:</b><br>",
            f"{comments_html}<br><br>",
            "Regards,<br>James.",
            "</div>"
        ]

        mail.HTMLBody = ''.join(body_parts)
        mail.Save()
        print(f"Created draft email for {shift.work_area.department} - {shift.work_area.role}")

    def process_shifts(self, current_shifts):
        """Check current shifts against previous state and create draft emails for new escalations."""
        # Load previous shift keys
        try:
            with open(self.storage_path, 'r') as f:
                previous_shift_keys = set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            previous_shift_keys = set()

        # Get current escalated shifts
        current_shift_keys = set()
        new_escalated_shifts = []

        # First, collect all new escalated shifts
        for shift in current_shifts:
            if shift.comment and isinstance(shift.comment, str):
                if 'esc' in shift.comment.lower() or 'escalated' in shift.comment.lower():
                    shift_key = self.get_shift_key(shift)
                    current_shift_keys.add(shift_key)

                    # If this is a new escalated shift
                    if shift_key not in previous_shift_keys:
                        new_escalated_shifts.append(shift)

        # If there are new escalated shifts, process them one by one
        if new_escalated_shifts:
            print("\nNew Escalated Shifts Found:")
            for i, shift in enumerate(new_escalated_shifts, 1):
                print(f"\n[ESCALATED SHIFT {i}/{len(new_escalated_shifts)}]")
                print(f"Location: {shift.work_area.location}")
                print(f"Department: {shift.work_area.department}")
                print(f"Role: {shift.work_area.role}")
                print(f"Time: {self.format_date(shift.start)} {shift.start.strftime('%H:%M')} - {shift.end.strftime('%H:%M')}")
                print("Press Enter to create draft email (or type 'skip' to skip)...")

                response = input().strip().lower()
                if response != 'skip':
                    self.create_draft_email(shift)

        # Save current state for next comparison
        with open(self.storage_path, 'w') as f:
            json.dump(list(current_shift_keys), f)

        if new_escalated_shifts:
            print("\nFinished processing all new escalated shifts.")
