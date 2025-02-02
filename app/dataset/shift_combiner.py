from datetime import time, datetime
from typing import List

from app.dataset.dataset import Shift, WorkArea


class ShiftCombiner:
    def __init__(self, dataset):
        self.dataset = dataset
        self.combined_shifts = []

    def combine_shifts(self):
        """Main method to process all shift combining rules"""
        print("Starting shift combination process...")
        processed_shifts = set()

        # First try combining shifts up to 10 hours
        self._combine_regular_shifts(processed_shifts)

        # Then handle short shifts
        self._combine_short_shifts(processed_shifts)

        # Finally combine sleepover shifts
        self._combine_sleepover_shifts(processed_shifts)

        # Add remaining uncombined shifts
        for shift in self.dataset.unassigned_shifts:
            if shift not in processed_shifts:
                self.combined_shifts.append(shift)

        self.dataset.combined_unfilled_shifts = self.combined_shifts
        print(f"Completed shift combination. Total shifts: {len(self.combined_shifts)}")

    def _combine_regular_shifts(self, processed_shifts):
        """Combine shifts with same Location, Department & Role up to 10 hours total"""
        sorted_shifts = sorted(self.dataset.unassigned_shifts, key=lambda s: (s.start, s.work_area.location,
                                                                              s.work_area.department, s.work_area.role))

        i = 0
        while i < len(sorted_shifts):
            if sorted_shifts[i] in processed_shifts:
                i += 1
                continue

            current_group = [sorted_shifts[i]]
            total_hours = current_group[0].gross_hours
            j = i + 1

            while j < len(sorted_shifts):
                next_shift = sorted_shifts[j]

                # Skip if already processed or would exceed 10 hours
                if next_shift in processed_shifts or total_hours + next_shift.gross_hours > 10:
                    j += 1
                    continue

                # Check if shifts can be combined
                if self._can_combine_regular_shifts(current_group[-1], next_shift):
                    current_group.append(next_shift)
                    total_hours += next_shift.gross_hours

                j += 1

            # If we found shifts to combine
            if len(current_group) > 1:
                combined = self._merge_shifts(*current_group)
                self.combined_shifts.append(combined)
                processed_shifts.update(current_group)
                print(
                    f"Combined {len(current_group)} shifts into {total_hours:.2f} hour shift: "
                    f"{combined.work_area.department} ({combined.start.strftime('%H:%M')}-{combined.end.strftime('%H:%M')})"
                )

            i = j

    def _combine_short_shifts(self, processed_shifts):
        """Combine shifts less than 2 hours with adjacent shifts"""
        sorted_shifts = sorted(self.dataset.unassigned_shifts, key=lambda s: s.start)

        for i, shift in enumerate(sorted_shifts):
            if shift in processed_shifts or shift.gross_hours >= 2:
                continue

            candidates = []
            if i > 0: candidates.append(sorted_shifts[i - 1])
            if i < len(sorted_shifts) - 1: candidates.append(sorted_shifts[i + 1])

            for candidate in candidates:
                if candidate not in processed_shifts and self._can_combine_short_shifts(shift, candidate):
                    combined = self._merge_shifts(shift, candidate)
                    self.combined_shifts.append(combined)
                    processed_shifts.update({shift, candidate})

                    print(
                        f"Combined shifts: {shift.work_area.department} ({shift.start.strftime('%H:%M')}-{shift.end.strftime('%H:%M')}) "
                        f"with {candidate.work_area.department} ({candidate.start.strftime('%H:%M')}-{candidate.end.strftime('%H:%M')})"
                    )
                    break

    def _combine_sleepover_shifts(self, processed_shifts):
        """Combine sleepover shifts with their components"""
        sorted_shifts = sorted(self.dataset.unassigned_shifts, key=lambda s: s.start)

        for shift in sorted_shifts:
            if shift in processed_shifts or not self._is_sleepover_shift(shift):
                continue

            components = self._find_sleepover_components(shift)
            if components and not any(comp in processed_shifts for comp in components):
                combined = self._merge_shifts(*components)
                self.combined_shifts.append(combined)
                processed_shifts.update(components)

                print(
                    f"Combined sleepover shift: {shift.work_area.department} "
                    f"({shift.start.strftime('%H:%M')}-{shift.end.strftime('%H:%M')})"
                )

    def _can_combine_regular_shifts(self, s1: Shift, s2: Shift) -> bool:
        """Check if shifts can be combined under the 10-hour rule"""
        # Must have exact matches
        if (s1.work_area.location != s2.work_area.location or
                s1.work_area.department != s2.work_area.department or
                s1.work_area.role != s2.work_area.role):
            return False

        # Must be chronologically adjacent
        return s2.start == s1.end

    def _can_combine_short_shifts(self, s1: Shift, s2: Shift) -> bool:
        """Check if two short shifts can be combined"""
        if s1.gross_hours >= 2 or s2.gross_hours >= 2:
            return False

        # Check for IHS/SOCIAL departments
        if self._is_special_department(s1) or self._is_special_department(s2):
            return (s1.work_area.location == s2.work_area.location and
                    s1.work_area.department == s2.work_area.department and
                    s1.work_area.role == s2.work_area.role)

        # Try different combination levels
        return any([
            self._match_level(s1, s2, level=3),  # Location, Dept, Role
            self._match_level(s1, s2, level=2),  # Location, Dept
            self._match_level(s1, s2, level=2, gsw=True)  # With role simplification
        ])

    def _find_sleepover_components(self, main_shift: Shift) -> List[Shift]:
        """Find 4-hour before and 2-hour after components for sleepover"""
        components = [main_shift]

        # Find 4-hour component before
        four_hour_before = next((
            s for s in self.dataset.unassigned_shifts
            if s.end == main_shift.start and
               s.gross_hours == 4 and
               s.work_area.department == main_shift.work_area.department and
               s.work_area.location == main_shift.work_area.location
        ), None)

        if four_hour_before:
            components.append(four_hour_before)

        # Find 2-hour component after if needed
        if main_shift.end.time() < time(6, 0):
            two_hour_after = next((
                s for s in self.dataset.unassigned_shifts
                if s.start == main_shift.end and
                   s.gross_hours == 2 and
                   s.work_area.department == main_shift.work_area.department and
                   s.work_area.location == main_shift.work_area.location
            ), None)

            if two_hour_after:
                components.append(two_hour_after)

        return components

    def _merge_shifts(self, *shifts: Shift) -> Shift:
        start = min(s.start for s in shifts)
        end = max(s.end for s in shifts)
        work_area = self._resolve_work_area(shifts)

        # Calculate gross and net hours separately
        total_gross_hours = 0
        total_net_hours = 0

        for s in shifts:
            if "SLEEPOVER" in s.work_area.role.upper():
                # For sleepover shifts, calculate active hours
                sleep_start = datetime.combine(s.start.date(), time(22, 0))
                sleep_end = datetime.combine(s.end.date(), time(6, 0))

                # Calculate hours before sleep
                if s.start < sleep_start:
                    before_sleep = (sleep_start - s.start).total_seconds() / 3600
                    total_gross_hours += before_sleep
                    total_net_hours += before_sleep if s.is_attended else 0

                # Calculate hours after sleep
                if s.end > sleep_end:
                    after_sleep = (s.end - sleep_end).total_seconds() / 3600
                    total_gross_hours += after_sleep
                    total_net_hours += after_sleep if s.is_attended else 0
            else:
                total_gross_hours += s.gross_hours
                total_net_hours += s.net_hours if s.is_attended else 0

        combined = Shift(
            start=start,
            end=end,
            work_area=work_area,
            published=False,
            comment=f"Combined {len(shifts)} shifts",
            is_attended=False,
            pay_cycle=shifts[0].pay_cycle
        )

        # Set the hours correctly
        combined.gross_hours = total_gross_hours
        combined.net_hours = total_net_hours

        return combined

    def _resolve_work_area(self, shifts: List[Shift]) -> WorkArea:
        """Determine work area for combined shifts"""
        if any(self._is_special_department(s) for s in shifts):
            return shifts[0].work_area

        roles = {s.work_area.role for s in shifts}
        departments = {s.work_area.department for s in shifts}
        locations = {s.work_area.location for s in shifts}

        if len(departments) == 1 and len(locations) == 1:
            return WorkArea(
                location=locations.pop(),
                department=departments.pop(),
                role="SUPPORT WORKER" if len(roles) > 1 else roles.pop()
            )

        return WorkArea("Combined", "General Support", "Support Worker")

    def _is_special_department(self, shift: Shift) -> bool:
        """Check if shift is in IHS/SOCIAL department"""
        return any(shift.work_area.department.startswith(prefix)
                   for prefix in ["IHS", "SOCIAL"])

    def _is_sleepover_shift(self, shift: Shift) -> bool:
        """Check if shift is an overnight sleepover shift"""
        return (shift.start.time() < time(23, 0) and
                shift.end.time() > time(0, 0) and
                "SLEEPOVER" in shift.work_area.role.upper())

    def _match_level(self, s1: Shift, s2: Shift, level: int, gsw=False) -> bool:
        """Check shift compatibility at different combination levels"""
        time_gap = (s2.start - s1.end).total_seconds() / 3600

        if abs(time_gap) > 1:  # Max 1 hour between shifts
            return False

        match level:
            case 3:  # Full match
                return (s1.work_area.location == s2.work_area.location and
                        s1.work_area.department == s2.work_area.department and
                        (s1.work_area.role == s2.work_area.role or gsw))
            case 2:  # Department match
                return (s1.work_area.location == s2.work_area.location and
                        s1.work_area.department == s2.work_area.department)
            case _:
                return False
