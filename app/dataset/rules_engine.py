# rules_engine.py (updated)
from datetime import timedelta, datetime, time

from app.dataset.dataset import Employee, Shift, EmploymentType, ContractStatus


class RulesEngine:
    def __init__(self, employee: Employee):
        self.employee = employee

    def _adjacent_to_existing_shift(self, shift: Shift) -> bool:
        """
        For shifts under 2 hours, check if the employee has an adjacent shift
        either immediately before or after this shift.
        """
        # Only apply this rule to short shifts
        if shift.gross_hours >= 2:
            return True

        for existing_shift in self.employee.shifts:
            # Check if the new shift is immediately after an existing shift
            if existing_shift.end == shift.start:
                return True

            # Check if the new shift is immediately before an existing shift
            if existing_shift.start == shift.end:
                return True

        return False

    def can_offer_shift(self, shift: Shift) -> bool:
        """Check all business rules for shift eligibility"""
        standard_rules = all([
            self._within_fortnight_days(shift),
            self._within_12_hour_window(shift),
            self._within_max_hours(shift),
            self._meets_ifa_requirements(shift),
            self._no_existing_commitments(shift),
            self._not_on_leave(shift),
            self._not_already_working_unless_longer(shift)
        ])

        # For short shifts, also check adjacency
        if shift.gross_hours < 2:
            return standard_rules and self._adjacent_to_existing_shift(shift)

        return standard_rules

    def _within_fortnight_days(self, shift: Shift) -> bool:
        pay_cycle = Shift.calculate_pay_cycle(shift.start)
        existing_days = set()

        # Collect all days from existing shifts in the same pay cycle
        for s in self.employee.shifts:
            if Shift.calculate_pay_cycle(s.start) == pay_cycle:
                start_date = s.start.date()
                end_date = s.end.date()
                current_date = start_date
                while current_date <= end_date:
                    existing_days.add(current_date)
                    current_date += timedelta(days=1)

        # Add days from the new shift
        new_start = shift.start.date()
        new_end = shift.end.date()
        current_date = new_start
        while current_date <= new_end:
            existing_days.add(current_date)
            current_date += timedelta(days=1)

        max_days = 14 if self.employee.employment_type == EmploymentType.CASUAL else 10
        return len(existing_days) <= max_days

    def _within_12_hour_window(self, shift: Shift) -> bool:
        # Find first shift of the day
        day_shifts = [s for s in self.employee.shifts
                      if s.start.date() == shift.start.date()]

        if not day_shifts:
            return True  # No shifts that day, so window hasn't started

        first_shift_start = min(s.start for s in day_shifts)
        window_end = first_shift_start + timedelta(hours=12)

        # Check if proposed shift falls within window
        if first_shift_start <= shift.start <= window_end:
            # Calculate total hours within window
            relevant_shifts = [s for s in day_shifts if first_shift_start <= s.start <= window_end]
            total_hours = sum(s.net_hours for s in relevant_shifts)
            return (total_hours + shift.net_hours) <= 10

        return True  # Outside the 12-hour window

    def _within_max_hours(self, shift: Shift) -> bool:
        pay_cycle = Shift.calculate_pay_cycle(shift.start)
        current_hours = sum(
            s.net_hours for s in self.employee.shifts
            if Shift.calculate_pay_cycle(s.start) == pay_cycle
        )
        return (current_hours + shift.net_hours) <= 76

    def _meets_ifa_requirements(self, shift: Shift) -> bool:
        if self._is_sleepover_shift(shift):
            return self.employee.contract_status == ContractStatus.FULL_IFA
        return True

    def _no_existing_commitments(self, shift: Shift) -> bool:
        return not any(
            s.start <= shift.end and s.end >= shift.start
            for s in self.employee.shifts
        )

    def _not_on_leave(self, shift: Shift) -> bool:
        """
        Check if the employee has any leave (regardless of type or status) that overlaps with the shift.
        A shift cannot be offered if there is ANY overlap with a leave period.

        Args:
            shift (Shift): The shift to check

        Returns:
            bool: True if the employee is NOT on leave during any part of the shift, False otherwise
        """
        shift_start_datetime = shift.start
        shift_end_datetime = shift.end

        for leave in self.employee.leave_dates:
            # Convert leave date to datetime at start and end of day
            leave_start = datetime.combine(leave.date, time.min)  # Start of day (00:00)
            leave_end = datetime.combine(leave.date, time.max)  # End of day (23:59:59)

            # Check for any overlap between shift and leave period
            if shift_start_datetime <= leave_end and shift_end_datetime >= leave_start:
                return False  # Overlap found, cannot offer shift

        return True  # No overlap with any leave periods

    def _not_already_working_unless_longer(self, shift: Shift) -> bool:
        """Check if the new shift has more hours than existing shifts for the day"""
        shift_date = shift.start.date()
        existing_hours = sum(
            s.net_hours for s in self.employee.shifts
            if s.start.date() == shift_date
        )

        return shift.net_hours > existing_hours if existing_hours > 0 else True

    @staticmethod
    def _is_sleepover_shift(shift: Shift) -> bool:
        return shift.start.date() != shift.end.date()
