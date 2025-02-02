# main.py

import sys
import warnings
from datetime import datetime
from pathlib import Path

# Add lib directory to Python path
current_dir = Path(__file__).resolve().parent
lib_path = current_dir / 'lib'
sys.path.append(str(lib_path))

from app.base_importer import BaseImporter
from app.dataset.dataset import DataSet
from app.dataset.shift_combiner import ShiftCombiner
from app.reports.roster_analyzer import RosterAnalyzer
from app.email_service import EmailService

# Suppress specific warnings
warnings.filterwarnings("ignore", message="Cannot parse header or footer so it will be ignored")


def filter_employees_by_region(dataset):
    """
    Filter employees based on work area locations.
    Keep employees who work in the LIMESTONE COAST region.
    """
    REQUIRED_LOCATIONS = {"LIMESTONE COAST"}
    employees_to_remove = []

    for emp_code, employee in dataset.employees.items():
        employee_locations = {work_area.location for work_area in employee.work_areas}
        if not employee_locations.intersection(REQUIRED_LOCATIONS):
            employees_to_remove.append(emp_code)

    # Remove marked employees
    for emp_code in employees_to_remove:
        del dataset.employees[emp_code]

    return dataset


def main():
    # Setup logging
    print("Starting import and report generation process...")

    try:
        # Set cutoff date
        cutoff_date = datetime(2025, 3, 26)
        print(f"Using cutoff date: {cutoff_date.strftime('%d/%m/%Y')}")

        # Initialize dataset with existing data and cutoff date
        dataset = DataSet()
        dataset.cutoff_date = cutoff_date

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
        print(f"Initial shifts after combining: {initial_shifts}")

        # Initialize services
        analyzer = RosterAnalyzer(dataset)
        # In main.py or wherever you initialize the EmailService
        email_service = EmailService(template_path="email_template.html")

        # Generate report and get eligible shifts
        print("Generating shift analysis report...")
        eligible_shifts = analyzer.generate_shift_analysis_report("roster_analysis.xlsx")
        print(f"Found eligible shifts for {len(eligible_shifts)} employees")

        # Process emails if there are eligible shifts
        if eligible_shifts:
            # Create employee data dictionary with email addresses
            employee_data = {
                emp.name: {
                    'email': emp.email,
                    'first_name': emp.first_name,
                    'last_name': emp.last_name
                }
                for emp in dataset.employees.values()
            }

            # Process emails
            print("Starting email processing...")
            email_service.process_shift_emails(eligible_shifts, employee_data)
            print("Email processing complete")

        # Print summary
        print("\nProcessing Summary:")
        print(f"  - Total employees processed: {len(dataset.employees)}")
        print(f"  - Total shifts processed: {initial_shifts}")
        print(f"  - Employees with eligible shifts: {len(eligible_shifts)}")
        print(f"  - Report generated: roster_analysis.xlsx")

        print("Process completed successfully")
        return 0  # Successful execution

    except Exception as e:
        print(f"Error: An error occurred during processing: {str(e)}")
        return 1  # Error occurred


if __name__ == "__main__":
    sys.exit(main())
