"""Save/load Project objects as JSON (.vbproj.json)."""
from __future__ import annotations

import json

from .models import Project

PROJECT_EXTENSION = ".vbproj.json"


def save_project(project: Project, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, indent=2)


def load_project(path: str) -> Project:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Project.from_dict(data)
