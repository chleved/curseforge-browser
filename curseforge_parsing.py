from datetime import datetime


def find_resource_pack_class(classes):
    preferred_slugs = (
        "texture-packs",
        "texture_packs",
        "resource-packs",
        "resource_packs",
        "texturepacks",
    )

    for item in classes:
        slug = (item.get("slug") or "").lower()
        if slug in preferred_slugs:
            return item

    for item in classes:
        slug = (item.get("slug") or "").lower()
        name = (item.get("name") or "").lower()
        if "texture" in slug or "texture" in name or "resource" in slug or "resource" in name:
            return item

    return None


def normalize_mod_loader_type(value):
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def parse_file_date(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def build_mod_dict(mod, target_version, target_mod_loader=None):
    indexes = [file_index for file_index in mod.get("latestFilesIndexes", []) if file_index]
    normalized_loader = normalize_mod_loader_type(target_mod_loader)

    def _matches(file_index, require_version=False, require_loader=False):
        if require_version and file_index.get("gameVersion") != target_version:
            return False
        if require_loader:
            if normalize_mod_loader_type(file_index.get("modLoader")) != normalized_loader:
                return False
        return True

    file_id = next(
        (
            file_index.get("fileId")
            for file_index in indexes
            if _matches(
                file_index,
                require_version=bool(target_version),
                require_loader=normalized_loader is not None,
            )
        ),
        None,
    )

    if file_id is None and target_version:
        file_id = next(
            (file_index.get("fileId") for file_index in indexes if _matches(file_index, require_version=True)),
            None,
        )

    if file_id is None and normalized_loader is not None:
        file_id = next(
            (file_index.get("fileId") for file_index in indexes if _matches(file_index, require_loader=True)),
            None,
        )

    if file_id is None:
        file_id = next((file_index.get("fileId") for file_index in indexes), None)

    return {
        "id": mod.get("id"),
        "name": mod.get("name"),
        "summary": mod.get("summary", ""),
        "authors": ", ".join(author.get("name", "") for author in mod.get("authors", [])),
        "downloads": mod.get("downloadCount", 0),
        "url": (mod.get("links") or {}).get("websiteUrl"),
        "logo_url": (mod.get("logo") or {}).get("thumbnailUrl"),
        "fileId": file_id,
    }
