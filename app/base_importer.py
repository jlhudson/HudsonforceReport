# lib/base_importer.py
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from app.dataset.dataset import DataSet
from app.importers.employee_shift_data import EmployeeShiftDataImporter
from app.importers.leave_data import LeaveDataImporter
from app.importers.work_area_assignment import WorkAreaAssignmentImporter


class BaseImporter:
    IMPORTERS = [EmployeeShiftDataImporter, LeaveDataImporter, WorkAreaAssignmentImporter, ]

    @classmethod
    def run_import(cls, dataset: DataSet) -> None:
        source_folder = Path(__file__).parent.parent / "Downloads"
        destination_folder = Path(__file__).parent.parent / "Humanforce Reports"
        destination_folder.mkdir(exist_ok=True)

        print("Starting import process...")

        # Get all Excel files from both folders
        excel_files: Dict[Path, List[Tuple[Path, float]]] = {source_folder: [], destination_folder: []}

        for folder in excel_files:
            for ext in ['.xlsx', '.xls']:
                for file_path in folder.glob(f'*{ext}'):
                    try:
                        # Use creation time instead of modified time
                        creation_time = os.path.getctime(file_path)
                        excel_files[folder].append((file_path, creation_time))
                    except Exception as e:
                        print(f"Error getting creation time for {file_path}: {str(e)}")

        # Process files for each importer
        processed_files = set()
        for importer_class in cls.IMPORTERS:
            newest_match = None
            newest_time = 0
            matched_folder = None

            # Check both folders for matching files
            for folder, files in excel_files.items():
                for file_path, creation_time in files:
                    if file_path in processed_files:
                        continue

                    try:
                        df = pd.read_excel(file_path, nrows=0)
                        headers = df.columns.tolist()

                        if importer_class.check_headers(headers):
                            if creation_time > newest_time:
                                newest_match = file_path
                                newest_time = creation_time
                                matched_folder = folder
                    except Exception as e:
                        print(f"Error reading {file_path}: {str(e)}")

            # Process the newest matching file
            if newest_match:
                try:
                    new_path = destination_folder / importer_class.get_save_as_name()

                    # Only copy if source is from Downloads folder
                    if matched_folder == source_folder:
                        shutil.copy2(newest_match, new_path)
                        print(f"Copied newest version from Downloads: {newest_match.name}")
                    elif matched_folder == destination_folder and newest_match.name != new_path.name:
                        # If newest is in Humanforce Reports but with different name, rename it
                        shutil.move(newest_match, new_path)
                        print(f"Renamed newest version in Humanforce Reports: {newest_match.name}")

                    processed_files.add(newest_match)
                except Exception as e:
                    print(f"Error processing {newest_match}: {str(e)}")

        # Extract data from matched files
        print("Extracting data from newest matched files...")
        for importer_class in cls.IMPORTERS:
            try:
                file_path = destination_folder / importer_class.get_save_as_name()
                if file_path.exists():
                    importer = importer_class()
                    importer.extract_data(file_path, dataset)
            except Exception as e:
                print(f"Error with {importer_class.__name__}: {str(e)}")

        #
        # # Generate report
        # report_path = destination_folder / "dataset_report.txt"
        # try:
        #     DatasetReporter.generate_report(dataset, report_path)
        #     print(f"Dataset report generated: {report_path}")
        # except Exception as e:
        #     print(f"Error generating dataset report: {str(e)}")
