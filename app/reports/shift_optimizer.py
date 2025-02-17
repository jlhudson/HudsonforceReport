from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from app.dataset.dataset import DataSet, Employee, Shift, EmploymentType
from app.dataset.rules_engine import RulesEngine


@dataclass
class ShiftAssignment:
    shift: Shift
    employee_code: str
    score: float
    shift_difficulty: float
    rejection_reasons: Dict[str, str] = field(default_factory=dict)


class ShiftOptimizer:
    def __init__(self, dataset: DataSet):
        self.dataset = dataset
        self.assigned_shifts: Set[Shift] = set()
        self.rejected_pairs: Set[Tuple[str, Shift]] = set()
        self.employee_assignments: Dict[str, List[Shift]] = defaultdict(list)
        self.shift_difficulties: Dict[Shift, float] = {}
        self.unfillable_shifts: Dict[Shift, Dict[str, str]] = {}
        self._calculate_all_shift_difficulties()

    def _calculate_shift_difficulty(self, shift: Shift) -> float:
        """
        Calculate how difficult a shift is to fill. Higher score means more difficult.
        Score is normalized between 0 and 10, with employee availability being the dominant factor.
        """
        # Get eligible employee count first
        total_employees = len(self.dataset.employees)
        eligible_count = sum(
            1 for employee in self.dataset.employees.values()
            if RulesEngine(employee).can_offer_shift(shift)[0]
        )

        # If no eligible employees, return maximum difficulty
        if eligible_count == 0:
            return 10.0

        # Employee availability is now 50% of the total score (0-5 points)
        employee_score = 5.0 * (1 - (eligible_count / total_employees))

        # Other factors make up the remaining 5 points
        remaining_score = 0.0

        # Shift duration (0-1 points)
        hours_score = abs(shift.gross_hours - 5) / 5
        remaining_score += min(1, hours_score)

        # Time of day (0-1 points)
        hour_diff = abs(shift.start.hour - 12) / 12
        remaining_score += hour_diff

        # Isolation score (0-1 points)
        closest_shift_gap = float('inf')
        for other_shift in self.dataset.combined_unfilled_shifts:
            if other_shift != shift:
                time_diff = abs((other_shift.start - shift.end).total_seconds() / 3600)
                closest_shift_gap = min(closest_shift_gap, time_diff)

        isolation_score = 1.0 if closest_shift_gap == float('inf') else min(1.0, closest_shift_gap / 8)
        remaining_score += isolation_score

        # Day of week (0-1 points)
        weekday = shift.start.weekday()
        if weekday in [5, 6]:  # Weekend
            day_score = 0.0
        else:
            day_score = 1.0 * (1 - abs(weekday - 2) / 4)
        remaining_score += day_score

        # Days until shift (0-1 points)
        days_until = (shift.start - datetime.now()).days
        if days_until > 0:
            future_score = min(1.0, days_until / 30)
            remaining_score += future_score

        return round(employee_score + remaining_score, 2)

    def _calculate_all_shift_difficulties(self):
        """Pre-calculate difficulty scores for all shifts."""
        for shift in self.dataset.combined_unfilled_shifts:
            self.shift_difficulties[shift] = self._calculate_shift_difficulty(shift)

    def _calculate_employee_score(self, employee: Employee, shift: Shift) -> float:
        """Calculate a score for assigning this shift to this employee. Lower is better."""
        # Base weights for different factors
        HOUR_WEIGHT = 0.6
        SHIFT_WEIGHT = 0.3
        ADJACENT_WEIGHT = 0.1

        total_hours = sum(s.gross_hours for s in employee.shifts)
        num_shifts = len(employee.shifts)

        # Normalize hour and shift balance (0-1 scale)
        hour_balance = min(1.0, (total_hours / 76)) * HOUR_WEIGHT
        shift_balance = min(1.0, (num_shifts / 14)) * SHIFT_WEIGHT

        # Preferred shift length factor (4-8 hours is ideal)
        shift_length_score = 1.0
        if 4 <= shift.gross_hours <= 8:
            shift_length_score = 0.7

        # Adjacent shift bonus
        has_adjacent = any(
            abs((s.end - shift.start).total_seconds()) < 3600 or
            abs((shift.end - s.start).total_seconds()) < 3600
            for s in employee.shifts
        )
        adjacent_score = (0.5 if has_adjacent else 1.0) * ADJACENT_WEIGHT

        # Consider work area expertise
        work_area_match = sum(
            1 for wa in employee.work_areas
            if wa.department == shift.work_area.department
        ) / max(1, len(employee.work_areas))

        # Final score calculation (lower is better)
        base_score = (hour_balance + shift_balance + adjacent_score) * shift_length_score
        expertise_adjusted_score = base_score * (2 - work_area_match)

        return expertise_adjusted_score

    def _find_best_employee_for_shift(self, shift: Shift, casual_only: bool = False) -> Optional[ShiftAssignment]:
        """Find the best employee for a given shift."""
        best_assignment = None
        best_score = float('inf')
        rejection_reasons = {}

        for employee in self.dataset.employees.values():
            if casual_only and employee.employment_type != EmploymentType.CASUAL:
                continue

            if (employee.employee_code, shift) in self.rejected_pairs:
                continue

            # Check eligibility using rules engine
            rules = RulesEngine(employee)
            can_offer, reason = rules.can_offer_shift(shift)

            if can_offer:
                score = self._calculate_employee_score(employee, shift)
                if score < best_score:
                    best_score = score
                    best_assignment = ShiftAssignment(
                        shift=shift,
                        employee_code=employee.employee_code,
                        score=score,
                        shift_difficulty=self.shift_difficulties[shift]
                    )
            elif reason:  # Only store non-empty rejection reasons
                rejection_reasons[employee.employee_code] = reason

        if best_assignment is None and rejection_reasons:
            # Store all rejection reasons if shift becomes unfillable
            self.unfillable_shifts[shift] = rejection_reasons
            # Recalculate difficulty since shift is now unfillable
            self.shift_difficulties[shift] = 10.0

        return best_assignment

    def _show_unfillable_shifts(self, shifts: List[Shift], title: str = "UNFILLABLE SHIFTS:"):
        """Helper method to display unfillable shifts and their rejection reasons."""
        unfillable = [s for s in shifts if s in self.unfillable_shifts]
        if unfillable:
            print(f"\n{title}")
            for shift in unfillable:
                print(f"\n{shift}")
                print("Rejection reasons by employee:")
                for emp_code, reason in self.unfillable_shifts[shift].items():
                    if reason:  # Only show non-empty reasons
                        emp_name = self.dataset.employees[emp_code].name
                        print(f"- {emp_name}: {reason}")

    def find_next_best_assignment(self) -> Optional[ShiftAssignment]:
        """Find the next best shift assignment, prioritizing difficult shifts."""
        # Show all unfillable shifts at start if this is our first run
        if not self.assigned_shifts and not self.rejected_pairs:
            all_unfillable = [s for s in self.dataset.combined_unfilled_shifts if s in self.unfillable_shifts]
            if all_unfillable:
                self._show_unfillable_shifts(all_unfillable)

        available_shifts = [s for s in self.dataset.combined_unfilled_shifts
                            if s not in self.assigned_shifts]

        if not available_shifts:
            return None

        # Sort shifts by difficulty (highest first)
        sorted_shifts = sorted(
            available_shifts,
            key=lambda s: self.shift_difficulties[s],
            reverse=True
        )

        # Try to fill the most difficult shifts first
        for shift in sorted_shifts:
            if shift in self.unfillable_shifts:
                continue

            # For difficult shifts, try all employees
            if self.shift_difficulties[shift] > 2.0:
                assignment = self._find_best_employee_for_shift(shift)
                if assignment:
                    return assignment

            # For easier shifts, try casuals first
            elif shift.gross_hours >= 2:
                casual_assignment = self._find_best_employee_for_shift(shift, casual_only=True)
                if casual_assignment:
                    return casual_assignment

            # If no casual found or shift < 2 hours, try all employees
            assignment = self._find_best_employee_for_shift(shift)
            if assignment:
                return assignment

        return None

    def process_assignment_response(self, assignment: ShiftAssignment, accepted: bool) -> None:
        """Process the response to a shift assignment offer."""
        employee = self.dataset.employees[assignment.employee_code]

        if accepted:
            employee.add_shift(assignment.shift)
            self.employee_assignments[assignment.employee_code].append(assignment.shift)
            self.assigned_shifts.add(assignment.shift)
        else:
            self.rejected_pairs.add((assignment.employee_code, assignment.shift))
            # Check if shift becomes unfillable after rejection
            new_assignment = self._find_best_employee_for_shift(assignment.shift)
            if new_assignment is None:
                # Show only this newly unfillable shift
                self._show_unfillable_shifts(
                    [assignment.shift],
                    "WARNING: Shift has become unfillable:"
                )

    def get_optimization_summary(self) -> Dict:
        """Get a summary of the optimization process."""
        return {
            "total_shifts": len(self.dataset.combined_unfilled_shifts),
            "assigned_shifts": len(self.assigned_shifts),
            "remaining_shifts": len(self.dataset.combined_unfilled_shifts) - len(self.assigned_shifts),
            "employee_assignments": {
                emp_code: len(shifts) for emp_code, shifts in self.employee_assignments.items()
            },
            "unfillable_shifts": {
                str(shift): {
                    self.dataset.employees[emp_code].name: reason
                    for emp_code, reason in reasons.items()
                    if reason  # Only include non-empty reasons
                }
                for shift, reasons in self.unfillable_shifts.items()
            }
        }