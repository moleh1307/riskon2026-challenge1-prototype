"""Versioned, data-driven support-function selection for M3."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import RoutingRequest


class SupportModelRule(BaseModel):
    """One support-function rule loaded from JSON."""

    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1)
    selector_type: str
    selector_value: str
    support_function: str


class SupportModel(BaseModel):
    """Closed, versioned support-function mapping."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    support_model_version: str
    rules: list[SupportModelRule]

    @classmethod
    def from_file(cls, path: Path) -> "SupportModel":
        """Load one local support-model JSON file."""

        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def resolve(self, request: RoutingRequest) -> str | None:
        """Return the first matching support function in priority order."""

        reasons = {reason.value for reason in request.reason_codes}
        for rule in sorted(self.rules, key=lambda item: item.priority):
            if rule.selector_type == "NEED_TYPE" and rule.selector_value == request.need_type.value:
                return rule.support_function
            if rule.selector_type == "REASON_CODE" and rule.selector_value in reasons:
                return rule.support_function
        return None
