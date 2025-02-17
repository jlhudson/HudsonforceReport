from collections import defaultdict
from datetime import timedelta, datetime
from typing import List, Tuple

from app.dataset.dataset import WorkArea, Shift


class ShiftCombiner:
    def __init__(self, dataset):
        self.dataset = dataset
        self.combined_shifts = []
        self.combination_details = defaultdict(list)
        self.uncombined_short_shifts = []  # Track short shifts that couldn't be combined

    def _is_sleepover_shift(self, shift: Shift) -> bool:
        """Check if a shift crosses midnight"""
        return shift.start.date() != shift.end.date()

    def _find_sleepover_components(self, shifts: List[Shift]) -> List[Tuple[List[Shift], float, float]]:
        """
        Find sleepover shifts and their adjacent components.
        Returns list of (shifts_to_combine, total_gross_hours, total_net_hours)
        """
        sleepover_combinations = []
        used_shifts = set()

        # Sort shifts by start time
        sorted_shifts = sorted(shifts, key=lambda s: s.start)

        for shift in sorted_shifts:
            if shift in used_shifts:
                continue

            if self._is_sleepover_shift(shift):
                # Find pre-sleepover shifts (up to 4 hours before)
                pre_shifts = []
                pre_shift_start = shift.start - timedelta(hours=4)
                for s in sorted_shifts:
                    if s.end == shift.start and s.start >= pre_shift_start:
                        pre_shifts.append(s)
                        used_shifts.add(s)

                # Find post-sleepover shifts (up to 4 hours after, before 6 AM)
                post_shifts = []
                if shift.end.hour < 6:
                    post_shift_end = shift.end.replace(hour=6, minute=0)
                    for s in sorted_shifts:
                        if s.start == shift.end and s.end <= post_shift_end:
                            post_shifts.append(s)
                            used_shifts.add(s)

                # Calculate total hours
                all_shifts = pre_shifts + [shift] + post_shifts
                if all_shifts:
                    total_gross = sum(s.gross_hours for s in all_shifts)
                    # For net hours, count everything except sleepover period
                    total_net = sum(s.net_hours for s in pre_shifts + post_shifts)

                    used_shifts.add(shift)
                    sleepover_combinations.append((all_shifts, total_gross, total_net))

        return sleepover_combinations

    def _get_role_prefix(self, role: str) -> str:
        """Extract the role prefix (part before the hyphen)"""
        return role.split('-')[0].strip() if '-' in role else role

    def can_combine_shifts(self, shift1: Shift, shift2: Shift) -> bool:
        """Check if two shifts can be combined based on rules"""
        # Don't combine IHS departments
        if "IHS" in shift1.work_area.department or "IHS" in shift2.work_area.department:
            return False

        # Must be same department
        if shift1.work_area.department != shift2.work_area.department:
            return False

        # Must be same location
        if shift1.work_area.location != shift2.work_area.location:
            return False

        # Must be adjacent (no gap)
        if shift1.end != shift2.start and shift2.end != shift1.start:
            return False

        # If either shift is part of a sleepover, don't combine
        if self._is_sleepover_shift(shift1) or self._is_sleepover_shift(shift2):
            return False

        # Combined length must not exceed 10 hours
        total_hours = shift1.gross_hours + shift2.gross_hours
        return total_hours <= 10

    def _find_regular_combinations(self, shifts: List[Shift]) -> List[List[Shift]]:
        """Find all possible combinations of regular (non-sleepover) shifts"""
        if not shifts:
            return []

        # Filter out shifts that are part of sleepover combinations
        regular_shifts = [s for s in shifts if not self._is_sleepover_shift(s)]

        # Sort shifts by start time
        sorted_shifts = sorted(regular_shifts, key=lambda s: s.start)

        # Group shifts by role prefix
        role_groups = defaultdict(list)
        for shift in sorted_shifts:
            prefix = self._get_role_prefix(shift.work_area.role)
            role_groups[prefix].append(shift)

        all_combinations = []

        # First try combining within same role prefix groups
        for prefix, group_shifts in role_groups.items():
            combinations = self._find_combinations_in_group(group_shifts)
            all_combinations.extend(combinations)

        # Track which shifts have been used in same-prefix combinations
        used_shifts = {shift for combo in all_combinations for shift in combo}

        # Then try combining remaining shifts across different prefixes
        remaining_shifts = [s for s in sorted_shifts if s not in used_shifts]
        cross_prefix_combinations = self._find_combinations_in_group(remaining_shifts)
        all_combinations.extend(cross_prefix_combinations)

        return all_combinations

    def _find_combinations_in_group(self, shifts: List[Shift]) -> List[List[Shift]]:
        """Find valid combinations within a group of shifts"""
        combinations = []
        n = len(shifts)

        # Try all possible lengths of combinations
        for size in range(2, min(n + 1, 5)):  # Limit to reasonable chunk sizes
            for i in range(n - size + 1):
                chunk = shifts[i:i + size]
                total_hours = sum(s.gross_hours for s in chunk)

                # Check if this is a valid combination
                if total_hours <= 10 and all(
                        chunk[j].end == chunk[j + 1].start
                        for j in range(len(chunk) - 1)
                ):
                    # At least one shift must be less than 2 hours
                    if any(s.gross_hours < 2 for s in chunk):
                        combinations.append(chunk)

        return combinations

    def _merge_shifts(self, shifts: List[Shift], override_gross_hours=None, override_net_hours=None) -> Shift | None:
        """Merge multiple shifts into one, with optional hour overrides for sleepover shifts"""
        if not shifts:
            return None

        start = min(s.start for s in shifts)
        end = max(s.end for s in shifts)

        work_area = WorkArea(
            location=shifts[0].work_area.location,
            department=shifts[0].work_area.department,
            role="SUPPORT WORKER"
        )

        total_gross_hours = override_gross_hours if override_gross_hours is not None else sum(s.gross_hours for s in shifts)
        total_net_hours = override_net_hours if override_net_hours is not None else sum(s.net_hours for s in shifts)

        shift_type = "sleepover" if self._is_sleepover_shift(shifts[0]) else "regular"
        combined = Shift(
            start=start,
            end=end,
            work_area=work_area,
            published=False,
            comment=f"Combined {len(shifts)} shifts ({shift_type})",
            is_attended=any(s.is_attended for s in shifts),
            pay_cycle=shifts[0].pay_cycle
        )

        combined.gross_hours = total_gross_hours
        combined.net_hours = total_net_hours

        return combined

    def combine_shifts(self):
        """Main method to find and apply optimal shift combinations"""
        print("\nStarting shift combination process...\n")

        # Filter out shifts before today
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        current_shifts = [
            shift for shift in self.dataset.unassigned_shifts
            if shift.start >= today
        ]

        print(f"Processing {len(current_shifts)} unfilled shifts from today onwards")

        # Group shifts by department and location
        dept_shifts = defaultdict(list)
        for shift in current_shifts:
            key = (shift.work_area.department, shift.work_area.location)
            dept_shifts[key].append(shift)

        final_shifts = []
        used_shifts = set()

        # Process each department separately
        for (dept, location), shifts in dept_shifts.items():
            if "IHS" in dept:
                final_shifts.extend(shifts)
                continue

            # First, find and process sleepover combinations
            sleepover_combinations = self._find_sleepover_components(shifts)
            for combo_shifts, gross_hours, net_hours in sleepover_combinations:
                combined = self._merge_shifts(combo_shifts, gross_hours, net_hours)
                final_shifts.append(combined)
                self.combination_details[combined] = sorted(combo_shifts, key=lambda s: s.start)
                used_shifts.update(combo_shifts)

            # Then process remaining regular shifts
            remaining_shifts = [s for s in shifts if s not in used_shifts]
            regular_combinations = self._find_regular_combinations(remaining_shifts)

            for combo in regular_combinations:
                if not any(s in used_shifts for s in combo):
                    combined = self._merge_shifts(combo)
                    final_shifts.append(combined)
                    self.combination_details[combined] = sorted(combo, key=lambda s: s.start)
                    used_shifts.update(combo)

            # Add remaining uncombined shifts
            for s in shifts:
                if s not in used_shifts:
                    final_shifts.append(s)
                    if s.gross_hours < 2:
                        self.uncombined_short_shifts.append(s)

        self.combined_shifts = sorted(final_shifts, key=lambda s: (
            s.work_area.department,
            s.start
        ))
        self.dataset.combined_unfilled_shifts = self.combined_shifts

        # Print summary
        self._print_shift_summary()

    def _print_shift_summary(self):
        """Print a clear summary of all shifts"""
        print(f"Total Unfilled Shifts: {len(self.combined_shifts)}")
        print(f"Uncombined Short Shifts: {len(self.uncombined_short_shifts)}\n")

        if self.uncombined_short_shifts:
            print("WARNING: The following short shifts (<2 hours) could not be combined:")
            print("-" * 80)
            for shift in sorted(self.uncombined_short_shifts, key=lambda s: s.start):
                shift_time = f"{shift.start.strftime('%d/%m/%Y %H:%M')} - {shift.end.strftime('%H:%M')}"
                print(f"{shift.work_area.department} - {shift.work_area.role}")
                print(f"  └─ {shift_time} ({shift.gross_hours:.1f}h)")
            print("\n" + "=" * 80 + "\n")

        print("Shift Details:")
        print("=" * 80)

        current_dept = None
        for shift in self.combined_shifts:
            # Print department header if it changes
            if current_dept != shift.work_area.department:
                current_dept = shift.work_area.department
                print(f"\nDepartment: {current_dept}")
                print("-" * 80)

            # Format the shift time and duration
            shift_time = f"{shift.start.strftime('%d/%m/%Y %H:%M')} - {shift.end.strftime('%H:%M')}"
            hours_info = f"(Gross: {shift.gross_hours:.1f}h, Net: {shift.net_hours:.1f}h)"
            role_prefix = self._get_role_prefix(shift.work_area.role)

            # Check if this is a combined shift
            if shift in self.combination_details:
                print(f"\n{shift.work_area.role} [{role_prefix}] {shift_time} {hours_info}")
                for component in self.combination_details[shift]:
                    comp_time = f"{component.start.strftime('%H:%M')} - {component.end.strftime('%H:%M')}"
                    comp_hours = f"(Gross: {component.gross_hours:.1f}h, Net: {component.net_hours:.1f}h)"
                    comp_prefix = self._get_role_prefix(component.work_area.role)
                    print(f"  └─ {component.work_area.role} [{comp_prefix}] {comp_time} {comp_hours}")
            else:
                # Regular uncombined shift
                print(f"\n{shift.work_area.role} [{role_prefix}] {shift_time} {hours_info}")
