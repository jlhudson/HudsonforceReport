from datetime import datetime, date
from enum import Enum
from typing import Optional


class EmploymentType(Enum):
    CASUAL = ("Casual", 14, 76)
    PART_TIME = ("Part Time", 10, 76)
    FULL_TIME = ("Full Time", 10, 76)
    UNKNOWN = ("Unknown", None, 0)

    def __init__(self, type_name: str, days: Optional[int], hours_per_paycycle: Optional[int]):
        self.hours_per_paycycle = hours_per_paycycle  # Maximum ours of work allowed per PayCycle.
        self.type_name = type_name  # Identifier Name.
        self.days = days  # Maximum Days of Work per fortnight.

    @classmethod
    def from_name(cls, name: str):
        for et in cls:
            if et.type_name.lower() == name.lower():
                return et
        return cls.UNKNOWN


class ContractStatus(Enum):
    FULL_IFA = ("Full IFA", "*", 8, True, True)
    PARTIAL_IFA = ("Partial IFA", "@", 10, True, True)
    NO_IFA = ("No IFA", "#", 10, False, False)
    UNKNOWN = ("Unknown", "", 0, False, False)

    def __init__(self, status_name: str, status_char: str, minimum_break: int, is_attended_considered_break: bool, is_allowed_work_around_sleepover: bool):
        self.status_name = status_name
        self.status_char = status_char
        self.minimum_break = minimum_break
        self.is_attended_considered_break = is_attended_considered_break
        self.is_allowed_work_around_sleepover = is_allowed_work_around_sleepover

    @classmethod
    def from_name(cls, name: str):
        for status in cls:
            if status.status_name.lower() in name.lower() or status.status_char in name:
                return status
        return cls.UNKNOWN

    @staticmethod
    def from_roster_name(roster_name: str):
        if "*" in roster_name:
            return ContractStatus.FULL_IFA
        elif "@" in roster_name:
            return ContractStatus.PARTIAL_IFA
        elif "#" in roster_name:
            return ContractStatus.NO_IFA
        else:
            return ContractStatus.UNKNOWN  # Return UNKNOWN if no symbol is found


class LeaveStatus(Enum):
    REQUESTED = ("Requested", False)
    APPROVED = ("Approved", True)
    DENIED = ("Denied", False)

    def __init__(self, display_name: str, is_approved: bool):
        self.display_name = display_name  # For user-friendly display
        self.is_approved = is_approved  # Boolean to check if the leave is counted as approved

    @classmethod
    def days_since_requested(cls, requested_at: datetime) -> int:
        """Calculates the days since the leave was requested."""
        return (datetime.now() - requested_at).days

    @classmethod
    def from_name(cls, name: str):
        for ls in cls:
            if ls.display_name.lower() == name.lower():
                return ls
        return None


class LeaveType(Enum):
    ANNUAL_LEAVE = ("Annual Leave", True)
    ANNUAL_LEAVE_CORP = ("Annual Leave Corp", True)
    STOOD_DOWN_WITH_PAY = ("Stood Down With Pay", True)
    UNAVAILABLE_DUE_TO_LEAVE = ("Unavailable due to Leave", False)
    CASUAL_UNPAID_LEAVE = ("Casual Unpaid Leave", False)
    LEAVE_WITHOUT_PAY = ("Leave without Pay", False)
    PERSONAL_CARERS_LEAVE = ("Personal/Carers Leave", True)
    ANNUAL_LEAVE_EXHAUSTED = ("Annual Leave Exhausted", False)
    CASUAL_PERSONAL_CARERS_LEAVE = ("Casual Personal/Carers Leave", True)
    UNPAID_PERSONAL_CARERS_LEAVE = ("Unpaid Personal/Carers Leave", False)
    CASUAL_COMPASSIONATE_LEAVE = ("Casual Compassionate Leave (unpaid)", False)
    PERSONAL_CARERS_LEAVE_CERT = ("Personal/Carers Leave w/ Cert.", True)
    PUBLIC_HOLIDAY_NOT_WORKED = ("PH Not Worked", False)

    def __init__(self, display_name: str, counts_towards_hours: bool):
        self.display_name = display_name  # Changed from `self.name` to avoid conflict
        self.counts_towards_hours = counts_towards_hours

    @classmethod
    def from_name(cls, name: str):
        for item in cls:
            if item.display_name.lower() == name.lower():
                return item
        return None


class WorkArea:
    def __init__(self, location: str, department: str, role: str):
        self.location = location
        self.department = department
        self.role = role

    def __eq__(self, other):
        return (self.location, self.department, self.role) == (other.location, other.department, other.role)

    def __hash__(self):
        return hash((self.location, self.department, self.role))


class Shift:
    REFERENCE_DATE = datetime(2024, 10, 1)  # Tuesday, October 1st, 2024

    def __init__(self, start: datetime, end: datetime, work_area: WorkArea, published: bool, comment: str, is_attended: bool, pay_cycle: int = None):
        self.start = start
        self.end = end
        self.work_area = work_area
        self.published = published
        self.comment = comment
        self.is_attended = is_attended
        self.pay_cycle = self.calculate_pay_cycle(start) if pay_cycle is None else pay_cycle
        self.week_num = self.calculate_week_num(start)
        self.gross_hours = self.calculate_gross_hours()
        self.net_hours = self.calculate_net_hours()

    def calculate_gross_hours(self) -> float:
        duration = (self.end - self.start).total_seconds() / 3600
        return round(duration, 2)

    def calculate_net_hours(self) -> float:
        if not self.is_attended:
            return 0.0
        return round(self.gross_hours, 2)

    def __str__(self):
        start_date = self.start.strftime('%a %d/%m')
        start_str = self.start.strftime('%H%M')
        end_str = self.end.strftime('%H%M')
        return f"{self.work_area.department}, {self.work_area.role} on {start_date} from {start_str}-{end_str} (G:{self.gross_hours:.1f}hrs, N:{self.net_hours:.1f}hrs, {'Attended' if self.is_attended else 'Not Attended'})"

    @classmethod
    def calculate_pay_cycle(cls, start_date) -> int:
        """Calculate pay cycle number based on reference date (Oct 1, 2024)"""
        # Convert date to datetime if needed
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, datetime.min.time())

        # Calculate days difference
        delta = start_date - cls.REFERENCE_DATE
        days = delta.days

        # Calculate pay cycle (1-based, 14-day periods)
        return (days // 14) + 1

    @classmethod
    def calculate_week_num(cls, start_date) -> int:
        """Calculate week number (1 or 2) based on reference date"""
        # Convert date to datetime if needed
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, datetime.min.time())

        # Calculate days difference
        delta = start_date - cls.REFERENCE_DATE
        days = delta.days

        # Calculate week number (1-based, alternating every 7 days)
        return (days // 7) % 2 + 1


class Leave:
    def __init__(self, date: datetime, status: LeaveStatus, requested_at: datetime, hours: float, leave_type: LeaveType):
        self.date = date
        self.status = status
        self.requested_at = requested_at
        self.hours = hours
        self.leave_type = leave_type  # LeaveType enum instance

    def calculate_hours(self) -> float:
        """Returns the requested hours, capped at a maximum of 7.6."""
        return min(self.hours, 7.6)

    def __str__(self):
        leave_date_str = self.date.strftime('%a %d/%m')
        return f"Leave on {leave_date_str} ({self.leave_type.display_name}, {self.status.display_name}, {self.calculate_hours()} Hrs)"


class Employee:
    def __init__(self, name: str, employee_code: str, roster_code: str, employment_type: EmploymentType, contract_status: ContractStatus, email: str = None, first_name: str = None, last_name: str = None):
        self.name = name
        self.employee_code = employee_code
        self.roster_code = roster_code
        self.employment_type = employment_type
        self.contract_status = contract_status
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.shifts = set()  # Stores unique shifts by start, end, and work area
        self.work_areas = set()  # Unique work areas automatically handled by set
        self.leave_dates = set()  # Stores unique Leave objects by date

    @staticmethod
    def parse_name(name: str):
        """Parse a full name into first name, last name, and full name, handling bracketed names.

        Args:
            name: The full name string to parse

        Returns:
            List containing [first_name, last_name, full_name]
        """
        # Check for bracketed name
        if '(' in name and ')' in name:
            start = name.find('(')
            end = name.find(')')
            if start < end:  # Valid brackets
                bracketed_name = name[start + 1:end].strip()
                # Split bracketed name into first and last
                name_parts = bracketed_name.split(' ', 1)
                if len(name_parts) > 1:
                    return [name_parts[0], name_parts[1], name]
                return [bracketed_name, "", name]

        # Regular name handling
        name_parts = name.split(' ', 1)
        if len(name_parts) > 1:
            return [name_parts[0], name_parts[1], name]
        return [name, "", name]

    def add_shift(self, new_shift: Shift):
        """Adds a shift ensuring no duplicates based on start, end, and work area."""
        if new_shift not in self.shifts:
            self.shifts.add(new_shift)
            self.work_areas.add(new_shift.work_area)

    def add_leave(self, new_leave: Leave):
        """Adds a leave entry ensuring unique dates and resolving conflicts by requested_at timestamp."""
        for existing_leave in self.leave_dates:
            if existing_leave.date == new_leave.date:
                # Resolve conflict by keeping the most recently requested leave
                if new_leave.requested_at > existing_leave.requested_at:
                    self.leave_dates.remove(existing_leave)
                    self.leave_dates.add(new_leave)
                return
        self.leave_dates.add(new_leave)

    def sort_shifts(self):
        """Sorts the shifts by start time; used when necessary for reporting or processing."""
        self.shifts = sorted(self.shifts, key=lambda shift: shift.start)

    def __str__(self):
        locations = ', '.join({work_area.location for work_area in self.work_areas})
        return f"{self.name} ({self.roster_code}, {self.employment_type.type_name}, {self.contract_status.status_name}, [{locations}], Shifts: {len(self.shifts)}, Leave: {len(self.leave_dates)})"


class DataSet:
    def __init__(self):
        self.employees = {}
        self.unassigned_shifts = []
        self.combined_unfilled_shifts = []
        self.work_areas = set()
        self.cutoff_date = None

    def add_employee(self, employee: Employee):
        if employee.employee_code not in self.employees:
            self.employees[employee.employee_code] = employee

    def add_unassigned_shift(self, shift: Shift):
        # Only add shifts before cutoff date
        if self.cutoff_date and shift.start >= self.cutoff_date:
            return
        self.unassigned_shifts.append(shift)

    def add_shift_to_employee(self, employee: Employee, shift: Shift):
        # Only add shifts before cutoff date
        if self.cutoff_date and shift.start >= self.cutoff_date:
            return False
        employee.add_shift(shift)
        return True

    def get_sorted_employees(self):
        return sorted(self.employees.values(), key=lambda emp: emp.name)

    def get_all_shifts(self):
        return [shift for emp in self.employees.values() for shift in emp.shifts] + self.unassigned_shifts
