from enum import Enum
import os

class ReportLevel(Enum):
    DEBUG = 1
    INFO = 2
    WARN = 3
    ERROR = 4

class ReportLogger:
    def __init__(self, level=ReportLevel.DEBUG, log_file="log_output.txt"):
        self.level = level
        self.log_file = log_file

        # Reset the log file at the start of each application run
        with open(self.log_file, 'w') as file:
            file.write("")

    def log(self, level: ReportLevel, message: str):
        if level.value >= self.level.value:
            indent = "\t"
            print(f"{level.name}:{indent}{message}")

    def debug(self, message: str):
        self.log(ReportLevel.DEBUG, message)

    def info(self, message: str):
        self.log(ReportLevel.INFO, message)

    def warning(self, message: str):
        self.log(ReportLevel.WARN, message)

    def error(self, message: str):
        self.log(ReportLevel.ERROR, message)

    def clean(self, message: str):
        """Appends only the message string without additional formatting to the log file."""
        print(f"{message}")
        with open(self.log_file, 'a') as file:
            file.write(f"{message}\n")

# Example usage of the logger, set at INFO level by default
report_logger = ReportLogger(ReportLevel.INFO)
