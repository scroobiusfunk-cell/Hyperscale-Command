"""ORM models.

Every model is imported here so Alembic's autogenerate sees the full metadata.
"""

from app.models.asset import Asset, AssetAlias, AssetSubmittal
from app.models.capture_recipe import CaptureRecipe
from app.models.checklist_item import ChecklistItem
from app.models.document import SourceDocument
from app.models.document_page import DocumentPage
from app.models.evidence import Evidence
from app.models.grader_result import GraderResult
from app.models.identity import AppUser, Project
from app.models.labeled_example import LabeledExample
from app.models.reconciliation import (
    ReconciliationQueueItem,
    ReconciliationQueueReason,
    ReconciliationQueueStatus,
)
from app.models.requirement import Requirement
from app.models.rule_set import RuleSet, RuleSetStatus
from app.models.ruling import Ruling

__all__ = [
    "AppUser",
    "Asset",
    "AssetAlias",
    "AssetSubmittal",
    "CaptureRecipe",
    "ChecklistItem",
    "DocumentPage",
    "Evidence",
    "GraderResult",
    "LabeledExample",
    "Project",
    "ReconciliationQueueItem",
    "ReconciliationQueueReason",
    "ReconciliationQueueStatus",
    "Requirement",
    "RuleSet",
    "RuleSetStatus",
    "Ruling",
    "SourceDocument",
]
