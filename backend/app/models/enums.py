import enum


class Role(str, enum.Enum):
    admin = "admin"
    officer = "officer"
    public = "public"


class RiskLevel(str, enum.Enum):
    green = "green"
    yellow = "yellow"
    orange = "orange"
    red = "red"


class AlertStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"
    acknowledged = "acknowledged"


class AlertKind(str, enum.Enum):
    landslide = "landslide"
    flash_flood = "flash-flood"
    monsoon = "monsoon"
    advisory = "advisory"


class ReportStatus(str, enum.Enum):
    submitted = "submitted"
    verified = "verified"
    resolved = "resolved"