from __future__ import annotations

import re

from .base import Adapter


class Greenhouse(Adapter):
    """Single page. The hosted board (job-boards.greenhouse.io) renders the
    form inline with react-select dropdowns; the older boards.greenhouse.io
    layout uses native selects under #application_form."""
    name = "greenhouse"
    hosts = ("greenhouse.io",)
    root = "#application-form, #application_form, form[action*='applications']"
    confirm_url = re.compile(r"/confirmation\b")
