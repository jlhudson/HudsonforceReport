import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Cannot parse header or footer so it will be ignored")

# Add lib directory to Python path
current_dir = Path(__file__).resolve().parent
lib_path = current_dir / 'lib'
sys.path.append(str(lib_path))

from app.base_importer import BaseImporter
from app.dataset.dataset import DataSet
from app.reports.report_generator import ReportGenerator
from app.reports.unfilled_shift_report import UnfilledShiftReport


def setup_logging():
    """Configure basic logging for the application."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)


def filter_employees_by_region(dataset):
    """
    Filter employees based on work area locations.
    Keep employees who work in at least one of: FLEURIEU, KANGAROO ISLAND, or METRO.
    """
    REQUIRED_LOCATIONS = {"FLEURIEU", "KANGAROO ISLAND", "METRO"}

    employees_to_remove = []

    for emp_code, employee in dataset.employees.items():
        # Get all unique locations where this employee works
        employee_locations = {work_area.location for work_area in employee.work_areas}

        # If none of the employee's locations are in our required locations, mark for removal
        if not employee_locations.intersection(REQUIRED_LOCATIONS):
            employees_to_remove.append(emp_code)

    # Remove marked employees
    for emp_code in employees_to_remove:
        del dataset.employees[emp_code]

    return dataset


def main():
    # Setup logging
    logger = setup_logging()
    logger.info("Starting import and report generation process...")

    try:
        # Create dataset and run import
        dataset = DataSet()
        BaseImporter.run_import(dataset)
        logger.info(f"Import complete! Dataset contains {len(dataset.employees)} employees")

        # Filter employees based on regions
        dataset = filter_employees_by_region(dataset)
        logger.info(f"After filtering, dataset contains {len(dataset.employees)} employees")

        # Generate Unfilled Shifts Report first
        logger.info("Generating Unfilled Shifts Report...")
        unfilled_report = UnfilledShiftReport(dataset)
        unfilled_report.generate_report()
        logger.info("Unfilled Shifts Report completed")

        # Generate employee validation reports
        logger.info("Starting employee validation reports...")
        report_generator = ReportGenerator(dataset)
        report_generator.generate()  # This will run all the employee validations

        logger.info("All report generation complete!")

    except Exception as e:
        logger.error(f"An error occurred during processing: {str(e)}")
        raise


if __name__ == "__main__":
    main()
