"""tres_suite -- backend for HORIBA DeltaFlex / EzTime time-resolved emission analysis.

Importing this package performs no analysis, no prompting and no file writing.
GUI-facing entry points: ``config.load_config`` / ``config_from_dict``,
``pipeline.run_project``, ``plotting.render_plots``, ``export.write_run``.
"""
__version__ = "0.1.0"

from .workbook import WorkbookParseError, TresWorkbook, AnisotropyWorkbook, detect_workbook_type, load_workbook  # noqa: F401,E402
from .project import Project, Measurement, ConditionGroup, LabelValue  # noqa: F401,E402
from .validation import Diagnostic, Severity, ValidationThresholds  # noqa: F401,E402
