"""Matrix Traffic Data — Reporting Engine.

Excel report generation with Matrix branding for ATC, TMC, and O-D reports.
"""

from src.reports.matrix_branding import (
    HEADER_BG,
    HEADER_TEXT,
    SUBHEADER_BG,
    ACCENT_BLUE,
    TOTAL_ROW_BG,
    BORDER_COLOR,
    ALT_ROW_BG,
    get_header_font,
    get_header_fill,
    get_border,
    get_total_fill,
    write_matrix_header,
    apply_header_style,
    apply_data_borders,
    auto_size_columns,
)
from src.reports.report_engine import BaseReport
from src.reports.atc_report import ATCReport
from src.reports.tmc_report import TMCReport
from src.reports.od_report import ODReport

__all__ = [
    # Branding constants
    "HEADER_BG",
    "HEADER_TEXT",
    "SUBHEADER_BG",
    "ACCENT_BLUE",
    "TOTAL_ROW_BG",
    "BORDER_COLOR",
    "ALT_ROW_BG",
    # Branding helpers
    "get_header_font",
    "get_header_fill",
    "get_border",
    "get_total_fill",
    "write_matrix_header",
    "apply_header_style",
    "apply_data_borders",
    "auto_size_columns",
    # Report classes
    "BaseReport",
    "ATCReport",
    "TMCReport",
    "ODReport",
]
