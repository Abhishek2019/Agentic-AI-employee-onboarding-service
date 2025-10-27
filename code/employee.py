# employee.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal, Dict, Any
import re

SeatType = Literal["cabin", "cubicle"]
OSType   = Literal["linux", "windows", "macos"]
EquipType = Literal["laptop", "headphone", "mic", "webcam", "phone"]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

@dataclass
class Employee:
    # ---- DB columns (employees table) ----
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    employee_ID: Optional[int] = None  # filled after insert (RETURNING)

    # ---- Extra details captured via chat (not necessarily in employees table) ----
    address: Optional[str] = None
    seat_pref: Optional[SeatType] = None          # desired seat type
    os_requirement: Optional[OSType] = None       # for laptop
    primary_equipment: Optional[EquipType] = None # typically "laptop"
    notes: str = ""

    # ---- Runtime flags ----
    confirmed: bool = False                       # set true after user approves plan

    # ---------- business logic ----------
    REQUIRED_FIELDS = ("name", "email")  # add "phone" if you want it mandatory

    def is_ready_for_insert(self) -> bool:
        """Minimal readiness for creating the employees row."""
        return all(getattr(self, f) for f in self.REQUIRED_FIELDS) and self._email_ok()

    def _email_ok(self) -> bool:
        return bool(self.email and EMAIL_RE.match(self.email))

    def missing_fields(self) -> list[str]:
        return [f for f in self.REQUIRED_FIELDS if not getattr(self, f)]

    def to_db_params(self) -> Dict[str, Any]:
        """Map to the DB insert parameter dict for employees table."""
        if not self.is_ready_for_insert():
            raise ValueError(f"Missing required fields: {self.missing_fields()}")
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
        }

    def to_summary(self) -> str:
        """Human summary for final confirmation in chat."""
        lines = [
            f"Name: {self.name or '—'}",
            f"Email: {self.email or '—'}",
            f"Phone: {self.phone or '—'}",
            f"Address: {self.address or '—'}",
            f"Seat preference: {self.seat_pref or '—'}",
            f"OS requirement: {self.os_requirement or '—'}",
            f"Primary equipment: {self.primary_equipment or '—'}",
        ]
        return "\n".join(lines)

    def update_field(self, key: str, value: Any) -> None:
        """Safe setter used by the chat flow."""
        if not hasattr(self, key):
            raise AttributeError(f"Unknown field: {key}")
        # light normalizations
        if key == "email" and isinstance(value, str):
            value = value.strip().lower()
        if key == "seat_pref" and isinstance(value, str):
            value = value.strip().lower()
            if value not in ("cabin", "cubicle"):
                raise ValueError("seat_pref must be 'cabin' or 'cubicle'")
        if key == "os_requirement" and isinstance(value, str):
            v = value.strip().lower().replace("mac", "macos")
            if v not in ("linux", "windows", "macos"):
                raise ValueError("os_requirement must be linux/windows/macos")
            value = v
        if key == "primary_equipment" and isinstance(value, str):
            v = value.strip().lower()
            if v not in ("laptop","headphone","mic","webcam","phone"):
                raise ValueError("primary_equipment invalid")
            value = v
        setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
