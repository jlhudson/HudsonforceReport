# app/main.py

import warnings

from app.base_importer import BaseImporter
from app.dataset.dataset import DataSet
from app.dataset.shift_combiner import ShiftCombiner
from app.reports.shift_optimizer import ShiftOptimizer

# Suppress specific warnings
warnings.filterwarnings("ignore", message="Cannot parse header or footer so it will be ignored")

def filter_employees_by_region(dataset):
    """
    Filter employees based on work area locations.
    Keep employees who work in the LIMESTONE COAST region.
    """
    required_locations = {"LIMESTONE COAST"}
    employees_to_remove = []

    for emp_code, employee in dataset.employees.items():
        employee_locations = {work_area.location for work_area in employee.work_areas}
        if not employee_locations.intersection(required_locations):
            employees_to_remove.append(emp_code)

    # Remove marked employees
    for emp_code in employees_to_remove:
        del dataset.employees[emp_code]

    return dataset


def process_shift_assignments(optimizer):
    """Process shift assignments interactively."""
    while True:
        assignment = optimizer.find_next_best_assignment()
        if not assignment:
            print("\nNo more valid assignments available!")
            break

        employee = optimizer.dataset.employees[assignment.employee_code]
        print("\nProposed Assignment:")
        print(f"Employee: {employee.name}")
        print(f"Contract: {employee.contract_status.status_name}")
        print(f"Employment: {employee.employment_type.type_name}")

        # Show combined shift components if applicable
        shift = assignment.shift
        if "SUPPORT WORKER" in shift.work_area.department.upper():
            print("\nCombined Shift Components:")
            for component in shift.components:  # You'll need to ensure components are stored in the Shift class
                print(f"- {component.work_area.department}, {component.work_area.role}: "
                      f"{component.start.strftime('%H%M')}-{component.end.strftime('%H%M')} "
                      f"({component.gross_hours:.1f}hrs)")

        print(f"\nShift: {assignment.shift}")
        print(f"Score: {assignment.score:.2f}")
        print(f"Difficulty: {assignment.shift_difficulty:.2f}")

        while True:
            response = input("\nAccept this assignment? (y/n): ").lower()
            if response in ['y', 'n']:
                break
            print("Please enter 'y' for yes or 'n' for no.")

        optimizer.process_assignment_response(assignment, response == 'y')

def main():
    print("Starting import and report generation process...")

    try:
        # Initialize dataset
        dataset = DataSet()

        # Run the base import
        print("Starting data import...")
        BaseImporter.run_import(dataset)
        print(f"Import complete! Dataset contains {len(dataset.employees)} employees")

        # Filter employees based on regions
        dataset = filter_employees_by_region(dataset)
        print(f"After filtering, dataset contains {len(dataset.employees)} employees")

        # Combine shifts according to rules
        print("Combining shifts...")
        combiner = ShiftCombiner(dataset)
        combiner.combine_shifts()
        initial_shifts = len(dataset.combined_unfilled_shifts)
        print(f"Total combined/unfilled shifts: {initial_shifts}")

        # Start the interactive shift assignment process
        print("\nStarting interactive shift assignment process...")
        optimizer = ShiftOptimizer(dataset)
        process_shift_assignments(optimizer)

        # Print final summary
        summary = optimizer.get_optimization_summary()
        print("\nFinal Assignment Summary:")
        print(f"Total shifts: {summary['total_shifts']}")
        print(f"Assigned shifts: {summary['assigned_shifts']}")
        print(f"Remaining shifts: {summary['remaining_shifts']}")

        print("\nAssignments by employee:")
        for emp_code, num_shifts in summary['employee_assignments'].items():
            emp_name = dataset.employees[emp_code].name
            print(f"{emp_name}: {num_shifts} shifts")

        print("\nProcess completed successfully")
        return 0

    except Exception as e:
        print(f"Error: An error occurred during processing: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
