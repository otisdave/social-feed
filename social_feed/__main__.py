"""Fetch, merge, and publish the chronological JSON archive and RSS feed."""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from social_feed.adapters import ADAPTERS, VALIDATORS
from social_feed.models import Publication, https_url, parse_date

ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("atom", ATOM)


def read_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    https_url(config["site_url"])
    if not config.get("title") or not config.get("description"):
        raise ValueError("The feed requires a title and description.")
    subscriptions = config["subscriptions"]
    if not isinstance(subscriptions, dict) or not subscriptions:
        raise ValueError("Configure subscriptions grouped by platform.")
    sources = []
    for platform, entries in subscriptions.items():
        if platform not in ("youtube", "facebook", "reddit"):
            raise ValueError(f"Unknown subscription platform: {platform}")
        if not isinstance(entries, list):
            raise ValueError(f"Subscriptions for {platform} must be a list.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Every {platform} subscription must be an object.")
            if "platform" in entry:
                raise ValueError("The platform is defined by the subscription section, not the entry.")
            enabled = entry.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("The enabled field must be true or false.")
            sources.append({**entry, "platform": platform, "enabled": enabled})
    if not sources:
        raise ValueError("Configure at least one subscription.")
    config["sources"] = sources
    ids = set()
    for source in config["sources"]:
        source_id = source["id"]
        if not isinstance(source_id, str) or not source_id.strip() or source_id in ids:
            raise ValueError(f"Empty or duplicate source ID: {source_id}")
        ids.add(source_id)
        if not isinstance(source["name"], str) or not source["name"].strip():
            raise ValueError(f"Source {source_id} requires a name.")
        https_url(source["url"])
        if source["enabled"]:
            if source["platform"] not in ADAPTERS:
                raise ValueError(
                    f"No adapter registered for {source['platform']}; "
                    f"keep subscription {source_id} disabled until it is connected."
                )
            VALIDATORS[source["platform"]](source)
    return config


def merge_publications(existing: list[dict], incoming: list[Publication]) -> list[dict]:
    merged = {}
    for row in existing:
        publication = Publication(**row)
        merged[(publication.source_id, publication.id)] = publication.to_dict()
    for publication in incoming:
        key = (publication.source_id, publication.id)
        previous = merged.get(key)
        if previous is None or parse_date(publication.updated_at) >= parse_date(previous["updated_at"]):
            merged[key] = publication.to_dict()
    return sorted(
        merged.values(),
        key=lambda item: (parse_date(item["published_at"]), item["source_id"], item["id"]),
        reverse=True,
    )


def make_rss(config: dict, items: list[dict], generated_at: str) -> bytes:
    site_url = config["site_url"].rstrip("/") + "/"
    root = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(root, "channel")
    for tag, text in {
        "title": config["title"],
        "link": site_url,
        "description": config["description"],
        "language": "fr-ca",
        "lastBuildDate": format_datetime(parse_date(generated_at), usegmt=True),
    }.items():
        ET.SubElement(channel, tag).text = text
    ET.SubElement(channel, f"{{{ATOM}}}link", {
        "href": site_url + "feed.xml", "rel": "self", "type": "application/rss+xml"
    })
    for publication in items:
        item = ET.SubElement(channel, "item")
        for tag, text in {
            "title": publication["title"],
            "link": publication["url"],
            "description": publication["description"],
            "pubDate": format_datetime(parse_date(publication["published_at"]), usegmt=True),
            "category": publication["platform"],
        }.items():
            ET.SubElement(item, tag).text = "\n".join(line.rstrip() for line in text.split("\n"))
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = (
            publication["source_id"] + ":" + publication["id"]
        )
        ET.SubElement(item, "source", {"url": site_url + "feed.xml"}).text = publication["source_name"]
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def publish(config: dict, output: Path, adapters: dict | None = None) -> bool:
    adapters = ADAPTERS if adapters is None else adapters
    archive_path = output / "feed.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {
        "items": [], "sources": []
    }
    configured_ids = {source["id"] for source in config["sources"]}
    # Validate the archive before any network request or write.
    existing = merge_publications(archive["items"], [])
    existing = [item for item in existing if item["source_id"] in configured_ids]
    previous_sources = {source["id"]: source for source in archive["sources"]}
    now = datetime.now(timezone.utc).isoformat()
    incoming = []
    sources = []
    success = True
    for source in config["sources"]:
        status = {key: source[key] for key in ("id", "name", "platform", "url")}
        if not source.get("enabled", True):
            status.update(
                status="disabled",
                error=None,
                last_success_at=previous_sources.get(source["id"], {}).get("last_success_at"),
            )
            sources.append(status)
            continue
        try:
            publications = adapters[source["platform"]](source)
        except Exception as error:
            # One failing provider must not erase the archive or hide healthy providers.
            print(f"ERROR [{source['id']}]: {type(error).__name__}: {error}", file=sys.stderr)
            success = False
            status.update(
                status="error",
                error=f"{type(error).__name__}: {error}",
                last_success_at=previous_sources.get(source["id"], {}).get("last_success_at"),
            )
        else:
            incoming.extend(publications)
            status.update(status="ok", error=None, last_success_at=now)
        sources.append(status)
    items = merge_publications(existing, incoming)
    for source in sources:
        source["item_count"] = sum(item["source_id"] == source["id"] for item in items)
    document = {
        "version": 1,
        "title": config["title"],
        "description": config["description"],
        "generated_at": now,
        "sources": sources,
        "items": items,
    }
    rss = make_rss(config, items, now)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("feed.json", (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        ("feed.xml", rss),
    ):
        temporary = output / (name + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(output / name)
    print(f"Published {len(items)} publications from {len(sources)} sources.")
    return success


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path, default=Path("site"))
    arguments = parser.parse_args()
    return 0 if publish(read_config(arguments.config), arguments.output) else 1


if __name__ == "__main__":
    sys.exit(main())
