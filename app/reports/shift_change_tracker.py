# shift_change_tracker.py
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pythoncom
import win32com.client as win32


class ShiftChangeTracker:
    def __init__(self):
        self.storage_path = Path("Humanforce Reports") / "previous_shifts.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.outlook = None
        self.max_future_days = 10  # Only process shifts within next 10 days

    def initialize_outlook(self):
        """Try to initialize Outlook connection."""
        try:
            pythoncom.CoInitialize()  # Initialize COM
            self.outlook = win32.Dispatch('Outlook.Application')
            return True
        except Exception as e:
            print(f"Could not initialize Outlook: {e}")
            return False

    def get_shift_key(self, shift, is_grouped=False):
        """Create a unique identifier for a shift or group of shifts."""
        if not is_grouped:
            return f"{shift.start.isoformat()}_{shift.end.isoformat()}_{shift.work_area.location}_{shift.work_area.department}_{shift.work_area.role}"
        else:
            # For grouped shifts, create a composite key
            role_str = "_".join(shift.roles) if hasattr(shift, 'roles') else shift.work_area.role
            return f"GROUP_{shift.start.isoformat()}_{shift.end.isoformat()}_{shift.work_area.location}_{shift.work_area.department}_{role_str}"

    def can_join_shifts(self, shift1, shift2):
        """Check if two shifts can be joined based on business rules."""
        # Check location and department match
        if (shift1.work_area.location != shift2.work_area.location or
                shift1.work_area.department != shift2.work_area.department):
            return False

        # Check if they're back-to-back
        if shift1.end != shift2.start and shift2.end != shift1.start:
            return False

        # Check duration criteria
        short_shift = shift1.gross_hours <= 2 or shift2.gross_hours <= 2
        overnight = (shift1.start.date() != shift1.end.date() or
                     shift2.start.date() != shift2.end.date())

        return short_shift or overnight

    def join_shifts(self, shift1, shift2):
        """Create a virtual joined shift from two shifts."""
        from collections import namedtuple

        # Determine which shift comes first
        first, second = (shift1, shift2) if shift1.start < shift2.start else (shift2, shift1)

        # Create a combined virtual shift
        VirtualShift = namedtuple('VirtualShift', ['start', 'end', 'work_area', 'roles', 'comment', 'is_escalated'])
        return VirtualShift(
            start=first.start,
            end=second.end,
            work_area=first.work_area,
            roles=[first.work_area.role, second.work_area.role],
            comment=f"{first.comment or ''}\n{second.comment or ''}".strip(),
            is_escalated=bool(
                ('esc' in (first.comment or '').lower() or 'escalated' in (first.comment or '').lower()) or
                ('esc' in (second.comment or '').lower() or 'escalated' in (second.comment or '').lower())
            )
        )

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
        if not self.outlook:
            return False

        try:
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
            return True
        except Exception as e:
            print(f"Error creating draft email: {e}")
            return False

    def process_shifts(self, current_shifts):
        """Process individual and grouped shifts that are escalated within the time window."""
        # Try to initialize Outlook first
        if not self.initialize_outlook():
            print("Outlook is not available. Skipping shift processing entirely.")
            return

        # Load previously processed shifts
        try:
            with open(self.storage_path, 'r') as f:
                processed_shift_keys = set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            processed_shift_keys = set()

        # Calculate the cutoff date
        today = datetime.now().date()
        cutoff_date = today + timedelta(days=self.max_future_days)

        # Track which shifts we successfully process
        newly_processed_shifts = set()

        # First, find potential shift groups
        sorted_shifts = sorted(current_shifts, key=lambda x: x.start)
        grouped_shifts = []
        processed_in_group = set()

        # Look for shifts that can be grouped
        for i in range(len(sorted_shifts)):
            if i in processed_in_group:
                continue

            current = sorted_shifts[i]

            # Look for a shift to join with
            for j in range(len(sorted_shifts)):
                if i == j or j in processed_in_group:
                    continue

                other = sorted_shifts[j]
                if self.can_join_shifts(current, other):
                    virtual_shift = self.join_shifts(current, other)
                    grouped_shifts.append(virtual_shift)
                    processed_in_group.add(i)
                    processed_in_group.add(j)
                    break

        # Process all shifts (grouped and individual)
        all_shifts = grouped_shifts + [s for i, s in enumerate(sorted_shifts) if i not in processed_in_group]

        for shift in all_shifts:
            is_grouped = hasattr(shift, 'roles')
            shift_key = self.get_shift_key(shift, is_grouped=is_grouped)

            # Skip if:
            # 1. We've already processed this shift
            # 2. It's beyond our 10-day window
            # 3. It's not marked as escalated
            # For grouped shifts, check the is_escalated flag
            is_escalated = (hasattr(shift, 'is_escalated') and shift.is_escalated) or \
                           (not hasattr(shift, 'is_escalated') and shift.comment and \
                            isinstance(shift.comment, str) and \
                            ('esc' in shift.comment.lower() or 'escalated' in shift.comment.lower()))

            # Allow shifts that end within 11 days if they're part of a group
            end_cutoff = cutoff_date + timedelta(days=1) if hasattr(shift, 'roles') else cutoff_date

            if (shift_key in processed_shift_keys or
                    shift.start.date() > cutoff_date or
                    shift.end.date() > end_cutoff or
                    not is_escalated):
                continue

            # If we get here, we have an escalated shift within our window that needs processing
            print(f"\n[ESCALATED SHIFT]")
            print(f"Location: {shift.work_area.location}")
            print(f"Department: {shift.work_area.department}")
            print(f"Role: {shift.work_area.role}")
            print(
                f"Time: {self.format_date(shift.start)} {shift.start.strftime('%H:%M')} - {shift.end.strftime('%H:%M')}")
            print("Press Enter to create draft email (or type 'skip' to skip)...")

            response = input().strip().lower()
            if response != 'skip':
                if self.create_draft_email(shift):
                    newly_processed_shifts.add(shift_key)

        # Clean up COM
        try:
            pythoncom.CoUninitialize()
        except:
            pass

        # Update our record of processed shifts
        if self.outlook and newly_processed_shifts:
            processed_shift_keys.update(newly_processed_shifts)
            with open(self.storage_path, 'w') as f:
                json.dump(list(processed_shift_keys), f)
