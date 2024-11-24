# lib/dataset_reporter.py
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Set, Union, Dict

from app.dataset.dataset import DataSet, Employee, Shift, Leave, WorkArea


class DatasetReporter:
    @classmethod
    def generate_report(cls, dataset: DataSet, output_path: Path) -> None:
        """Generate a comprehensive report of the dataset"""
        lines: List[str] = []

        # Header with timestamp and dataset overview
        total_shifts = sum(len(emp.shifts) for emp in dataset.employees.values())
        total_leave = sum(len(emp.leave_dates) for emp in dataset.employees.values())

        lines.extend([
            "=== DATASET REPORT ===",
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Employees: {len(dataset.employees)}",
            f"Total Shifts: {total_shifts}",
            f"Total Leave Entries: {total_leave}",
            f"Total Unassigned Shifts: {len(dataset.unassigned_shifts)}",
            "\n"
        ])

        # Employee Details
        lines.append("=== EMPLOYEES ===")
        for emp_code, employee in sorted(dataset.employees.items()):
            lines.extend(cls._format_employee(employee))
            lines.append("\n")

        # Unassigned Shifts
        if dataset.unassigned_shifts:
            lines.extend([
                "=== UNASSIGNED SHIFTS ===",
                cls._format_shifts(dataset.unassigned_shifts),
                "\n"
            ])

        # Write to file
        output_path.write_text("\n".join(lines), encoding='utf-8')

    @classmethod
    def _format_employee(cls, employee: Employee) -> List[str]:
        """Format employee details including their shifts and leave"""
        # Calculate statistics
        total_shifts = len(employee.shifts)
        total_work_areas = len(employee.work_areas)
        total_leave = len(employee.leave_dates)
        total_gross_hours = sum(shift.gross_hours for shift in employee.shifts)
        total_net_hours = sum(shift.net_hours for shift in employee.shifts)
        attended_shifts = sum(1 for shift in employee.shifts if shift.is_attended)

        lines = [
            f"=== {employee.name} ===",
            f"Employee Code: {employee.employee_code}",
            f"Roster Name: {employee.roster_code}",
            "",
            "Quick Statistics:",
            f"- Total Shifts: {total_shifts}",
            f"- Attended Shifts: {attended_shifts}",
            f"- Work Areas: {total_work_areas}",
            f"- Leave Entries: {total_leave}",
            f"- Total Gross Hours: {total_gross_hours:.2f}",
            f"- Total Net Hours: {total_net_hours:.2f}",
            "",
            "Employment Details:",
            f"- Type: {employee.employment_type.type_name}",
            f"  • Max Hours per Pay Cycle: {employee.employment_type.hours_per_paycycle}",
            f"  • Max Days per Fortnight: {employee.employment_type.days}",
            f"- Contract Status: {employee.contract_status.status_name}",
            f"  • Minimum Break: {employee.contract_status.minimum_break} hours",
            f"  • Attended Considered Break: {employee.contract_status.is_attended_considered_break}",
            f"  • Allowed Work Around Sleepover: {employee.contract_status.is_allowed_work_around_sleepover}",
            ""
        ]

        # Organize work areas hierarchically
        work_areas_hierarchy = cls._organize_work_areas_hierarchy(employee.work_areas)
        lines.extend(["Work Areas:"])
        lines.extend(cls._format_work_areas_hierarchy(work_areas_hierarchy))
        lines.append("")

        # Add shifts
        if employee.shifts:
            lines.extend([
                "Shifts:",
                cls._format_shifts(employee.shifts)
            ])

        # Add leave
        if employee.leave_dates:
            lines.extend([
                "",
                "Leave:",
                cls._format_leave(employee.leave_dates)
            ])

        return lines

    @classmethod
    def _organize_work_areas_hierarchy(cls, work_areas: Set[WorkArea]) -> Dict:
        """Organize work areas into a hierarchical structure"""
        hierarchy = defaultdict(lambda: defaultdict(set))
        for area in work_areas:
            hierarchy[area.location][area.department].add(area.role)
        return hierarchy

    @classmethod
    def _format_work_areas_hierarchy(cls, hierarchy: Dict) -> List[str]:
        """Format the work areas hierarchy for display"""
        lines = []
        for location, departments in sorted(hierarchy.items()):
            lines.append(f"- Location: {location}")
            for department, roles in sorted(departments.items()):
                lines.append(f"  • Department: {department}")
                for role in sorted(roles):
                    lines.append(f"    ◦ Role: {role}")
        return lines

    @classmethod
    def _format_shifts(cls, shifts: Union[List[Shift], Set[Shift]]) -> str:
        """Format shift details"""
        if not shifts:
            return "  No shifts"

        shift_lines = []
        for shift in sorted(shifts, key=lambda s: s.start):
            area = shift.work_area
            shift_lines.append(
                f"  {shift.start.strftime('%Y-%m-%d %H:%M')} - "
                f"{shift.end.strftime('%H:%M')} | "
                f"{area.location}/{area.department}/{area.role} | "
                f"Published: {shift.published} | "
                f"Attended: {shift.is_attended} | "
                f"PC: {shift.pay_cycle} | "
                f"Hours (G/N): {shift.gross_hours:.2f}/{shift.net_hours:.2f}"
            )
            if shift.comment:
                shift_lines.append(f"    Comment: {shift.comment}")

        return "\n".join(shift_lines)

    @classmethod
    def _format_leave(cls, leave_entries: Set[Leave]) -> str:
        """Format leave details"""
        if not leave_entries:
            return "  No leave"

        leave_lines = []
        for leave in sorted(leave_entries, key=lambda l: l.date):
            leave_lines.append(
                f"  {leave.date.strftime('%Y-%m-%d')} | "
                f"{leave.leave_type.display_name} | "
                f"Status: {leave.status.display_name} | "
                f"Hours: {leave.calculate_hours():.2f} | "
                f"Requested: {leave.requested_at.strftime('%Y-%m-%d %H:%M')}"
            )

        return "\n".join(leave_lines)
