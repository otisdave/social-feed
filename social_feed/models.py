"""The publication contract shared by every source adapter."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse


def parse_date(value: str) -> datetime:
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError(f"A publication date must include a timezone: {value}")
    return date.astimezone(timezone.utc)


def https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"Expected an absolute HTTPS URL: {value}")
    return value


@dataclass(frozen=True)
class Publication:
    id: str
    title: str
    url: str
    published_at: str
    updated_at: str
    description: str
    image_url: str | None
    source_id: str
    source_name: str
    platform: str

    def __post_init__(self) -> None:
        if not all((self.id, self.title.strip(), self.source_id, self.source_name, self.platform)):
            raise ValueError("A publication must have an ID, title and source.")
        https_url(self.url)
        if self.image_url:
            https_url(self.image_url)
        parse_date(self.published_at)
        parse_date(self.updated_at)

    def to_dict(self) -> dict:
        return asdict(self)
