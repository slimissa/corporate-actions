"""
Data models for the Corporate Actions Registry.

These dataclasses provide a typed representation of the JSON structure
defined in actions.json. Each model includes a `from_dict` classmethod
to parse raw dictionaries, and a `to_dict` method to serialize back,
ensuring round-trip fidelity.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Dates:
    """Container for corporate action dates."""
    announcement: Optional[str] = None
    ex_date: Optional[str] = None
    record_date: Optional[str] = None
    effective_date: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Dates":
        if not isinstance(data, dict):
            return cls()
        return cls(
            announcement=data.get("announcement"),
            ex_date=data.get("ex_date"),
            record_date=data.get("record_date"),
            effective_date=data.get("effective_date"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Provenance:
    """Source and verification information for an action."""
    source: Optional[str] = None
    source_url: Optional[str] = None
    verification_source: Optional[str] = None
    verification_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Provenance":
        if not isinstance(data, dict):
            return cls()
        return cls(
            source=data.get("source"),
            source_url=data.get("source_url"),
            verification_source=data.get("verification_source"),
            verification_url=data.get("verification_url"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Impact:
    """Financial impact multipliers for backtesting."""
    price_multiplier: Optional[float] = None
    share_multiplier: Optional[float] = None
    cash_adjustment: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Impact":
        if not isinstance(data, dict):
            return cls()
        return cls(
            price_multiplier=data.get("price_multiplier"),
            share_multiplier=data.get("share_multiplier"),
            cash_adjustment=data.get("cash_adjustment"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Action:
    """A single corporate action entry."""
    isin: Optional[str] = None
    action_id: Optional[str] = None
    action_type: Optional[str] = None
    ratio: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    dates: Dates = field(default_factory=Dates)
    status: Optional[str] = None
    provenance: Provenance = field(default_factory=Provenance)
    impact: Impact = field(default_factory=Impact)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Action":
        if not isinstance(data, dict):
            return cls()
        return cls(
            isin=data.get("isin"),
            action_id=data.get("action_id"),
            action_type=data.get("action_type"),
            ratio=data.get("ratio"),
            amount=data.get("amount"),
            currency=data.get("currency"),
            dates=Dates.from_dict(data.get("dates")),
            status=data.get("status"),
            provenance=Provenance.from_dict(data.get("provenance")),
            impact=Impact.from_dict(data.get("impact")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dict, including nested dataclasses."""
        result = asdict(self)
        # Remove None values from nested dicts to keep clean
        if result["dates"] is not None:
            result["dates"] = self.dates.to_dict()
        if result["provenance"] is not None:
            result["provenance"] = self.provenance.to_dict()
        if result["impact"] is not None:
            result["impact"] = self.impact.to_dict()
        # Drop top-level None fields
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class RegistryMeta:
    """Metadata about the registry file."""
    version: Optional[str] = None
    generated_at: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RegistryMeta":
        if not isinstance(data, dict):
            return cls()
        return cls(
            version=data.get("version"),
            generated_at=data.get("generated_at"),
            source=data.get("source"),
            notes=data.get("notes"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}