from dataclasses import dataclass
from datetime import timedelta, datetime, time
from typing import Tuple

from app.dataset.dataset import Employee, Shift, EmploymentType, ContractStatus


@dataclass
class RuleResult:
    passed: bool
    reason: str = ""


class RulesEngine:
    def __init__(self, employee: Employee):
        self.employee = employee

    def _can_work_area(self, shift: Shift) -> RuleResult:
        """
        Check if employee is authorized to work in the shift's work area.
        For combined shifts from non-special departments, check if employee works in the department
        (any role in that department is acceptable).
        """
        # For IHS and SOCIAL departments, require exact match
        if any(shift.work_area.department.startswith(prefix) for prefix in ["IHS", "SOCIAL"]):
            if shift.work_area not in self.employee.work_areas:
                return RuleResult(False, "Employee not authorized for IHS/SOCIAL department work area")
            return RuleResult(True)

        # For support worker shifts or regular departments
        for wa in self.employee.work_areas:
            if (wa.location == shift.work_area.location and
                    wa.department == shift.work_area.department and
                    (wa.role == shift.work_area.role or "SUPPORT WORKER" in shift.work_area.department.upper())):
                return RuleResult(True)

        return RuleResult(False, f"Employee not authorized for work area: {shift.work_area.department}")

    # def _adjacent_to_existing_shift(self, shift: Shift) -> RuleResult:
    #     """Check if short shifts have an adjacent shift."""
    #     if shift.gross_hours >= 2:
    #         return RuleResult(True)
    #
    #     for existing_shift in self.employee.shifts:
    #         if existing_shift.end == shift.start or existing_shift.start == shift.end:
    #             return RuleResult(True)
    #
    #     return RuleResult(False, "Short shift (<2 hours) requires adjacent shift")

    def _within_fortnight_days(self, shift: Shift) -> RuleResult:
        pay_cycle = Shift.calculate_pay_cycle(shift.start)
        existing_days = set()

        for s in self.employee.shifts:
            if Shift.calculate_pay_cycle(s.start) == pay_cycle:
                current_date = s.start.date()
                while current_date <= s.end.date():
                    existing_days.add(current_date)
                    current_date += timedelta(days=1)

        new_start = shift.start.date()
        new_end = shift.end.date()
        current_date = new_start
        while current_date <= new_end:
            existing_days.add(current_date)
            current_date += timedelta(days=1)

        max_days = 14 if self.employee.employment_type == EmploymentType.CASUAL else 10
        if len(existing_days) > max_days:
            return RuleResult(False, f"Exceeds maximum {max_days} days per fortnight")
        return RuleResult(True)

    def _within_12_hour_window(self, shift: Shift) -> RuleResult:
        day_shifts = [s for s in self.employee.shifts
                      if s.start.date() == shift.start.date()]

        if not day_shifts:
            return RuleResult(True)

        first_shift_start = min(s.start for s in day_shifts)
        window_end = first_shift_start + timedelta(hours=12)

        if first_shift_start <= shift.start <= window_end:
            relevant_shifts = [s for s in day_shifts if first_shift_start <= s.start <= window_end]
            total_hours = sum(s.net_hours for s in relevant_shifts)
            if (total_hours + shift.net_hours) > 10:
                return RuleResult(False, "Exceeds 10 hours in 12-hour window")

        return RuleResult(True)

    def _within_max_hours(self, shift: Shift) -> RuleResult:
        pay_cycle = Shift.calculate_pay_cycle(shift.start)
        current_hours = sum(
            s.net_hours for s in self.employee.shifts
            if Shift.calculate_pay_cycle(s.start) == pay_cycle
        )
        if (current_hours + shift.net_hours) > 76:
            return RuleResult(False, "Exceeds 76 hours per pay cycle")
        return RuleResult(True)

    def _meets_ifa_requirements(self, shift: Shift) -> RuleResult:
        if self._is_sleepover_shift(shift):
            if self.employee.contract_status != ContractStatus.FULL_IFA:
                return RuleResult(False, "Sleepover shift requires Full IFA status")
        return RuleResult(True)

    def _no_existing_commitments(self, shift: Shift) -> RuleResult:
        for s in self.employee.shifts:
            if s.start <= shift.end and s.end >= shift.start:
                return RuleResult(False, "Overlaps with existing shift")
        return RuleResult(True)

    def _not_on_leave(self, shift: Shift) -> RuleResult:
        shift_start_datetime = shift.start
        shift_end_datetime = shift.end

        for leave in self.employee.leave_dates:
            leave_start = datetime.combine(leave.date, time.min)
            leave_end = datetime.combine(leave.date, time.max)

            if shift_start_datetime <= leave_end and shift_end_datetime >= leave_start:
                return RuleResult(False, "Employee on leave during shift period")

        return RuleResult(True)

    def _not_already_working_unless_longer(self, shift: Shift) -> RuleResult:
        shift_date = shift.start.date()
        existing_hours = sum(
            s.net_hours for s in self.employee.shifts
            if s.start.date() == shift_date
        )

        if existing_hours > 0 and shift.net_hours <= existing_hours:
            return RuleResult(False, "New shift must be longer than existing shifts for the day")
        return RuleResult(True)

    @staticmethod
    def _is_sleepover_shift(shift: Shift) -> bool:
        return shift.start.date() != shift.end.date()

    def can_offer_shift(self, shift: Shift) -> Tuple[bool, str]:
        """Check all business rules for shift eligibility and return result with reason if failed."""
        # Check each rule in order
        rules_to_check = [
            (self._can_work_area, "Work Area Authorization"),
            (self._within_fortnight_days, "Fortnight Days Limit"),
            (self._within_12_hour_window, "12-Hour Window"),
            (self._within_max_hours, "Maximum Hours"),
            (self._meets_ifa_requirements, "IFA Requirements"),
            (self._no_existing_commitments, "Existing Commitments"),
            (self._not_on_leave, "Leave Conflict"),
            (self._not_already_working_unless_longer, "Shift Length Priority")
        ]

        for rule_func, rule_name in rules_to_check:
            result = rule_func(shift)
            if not result.passed:
                # Skip displaying work area authorization rejections
                if rule_name == "Work Area Authorization":
                    return False, ""
                return False, f"{rule_name}: {result.reason}"

        # # Special handling for short shifts
        # if shift.gross_hours < 2:
        #     result = self._adjacent_to_existing_shift(shift)
        #     if not result.passed:
        #         return False, f"Adjacent Shift Rule: {result.reason}"

        return True, ""