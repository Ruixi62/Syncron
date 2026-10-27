"""API publique entre la plateforme (shell) et les outils.

Un outil = une sous-classe de `Tool`, enregistrée dans le `ToolRegistry`.
Il ne connaît la plateforme qu'à travers `ToolHost`.
"""

from syncron_client.platform.registry import ToolRegistry
from syncron_client.platform.tool import (
    NotifyLevel,
    SearchHit,
    StatusLevel,
    Tool,
    ToolHost,
    ToolInfo,
    ToolStage,
    ToolStatus,
)

__all__ = [
    "NotifyLevel",
    "SearchHit",
    "StatusLevel",
    "Tool",
    "ToolHost",
    "ToolInfo",
    "ToolRegistry",
    "ToolStage",
    "ToolStatus",
]
