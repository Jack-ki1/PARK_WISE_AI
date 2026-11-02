"""Approved, finite catalogue of publicly listed Pexels source clips.

Only these source IDs may be fetched; callers cannot supply arbitrary URLs.
Direct MP4 locations were obtained through each Pexels page's Free download link.
Always review the current Pexels terms before commercial redistribution.

Each entry pins ``sha256`` + ``bytes`` of the exact file the link served when the
entry was written. Direct CDN links rot (and providers re-encode in place), so
the fetch path verifies the digest and fails with an explicit "source changed"
error instead of importing whatever the URL now serves.
"""

PUBLIC_SOURCES: dict[str, dict] = {
    "pexels-tom-fisk-3848792": {
        "title": "Aerial Footage Of Cars On A Parking Lot",
        "creator": "Tom Fisk",
        "landing_page": "https://www.pexels.com/video/aerial-footage-of-cars-on-a-parking-lot-3848792/",
        "download_url": "https://videos.pexels.com/video-files/3848792/3848792-uhd_3840_2160_30fps.mp4",
        "description": "High-angle view of parked cars arranged in a parking lot.",
        "duration_seconds": 38,
        "resolution": "3840×2160",
        "license_label": "Pexels Free license — verify current terms",
        "filename": "pexels-tom-fisk-parking-3848792.mp4",
        "sha256": "86043be8630ff71344746cd69362dd25ff77e62f667246e7ca738428c673c0c0",
        "bytes": 116666185,
    },
    "pexels-yasin-koc-tepe-27832493": {
        "title": "An Aerial View of a Parking Lot with Cars",
        "creator": "Yasin Koçtepe",
        "landing_page": "https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-27832493/",
        "download_url": "https://videos.pexels.com/video-files/27832493/12237869_3840_2160_50fps.mp4",
        "description": "Aerial drone footage of a busy parking lot and road intersection.",
        "duration_seconds": 18,
        "resolution": "3840×2160",
        "license_label": "Pexels Free license — verify current terms",
        "filename": "pexels-yasin-parking-27832493.mp4",
        "sha256": "24c477c2b1a24ac251fb6bc8fe638e22ad448adfaef55c49f6fec21fbdc20db1",
        "bytes": 155376366,
    },
    "pexels-david-pickup-28125313": {
        "title": "Crowded Parking Lot from Above",
        "creator": "David Pickup",
        "landing_page": "https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-28125313/",
        "download_url": "https://videos.pexels.com/video-files/28125313/12306189_3840_2160_30fps.mp4",
        "description": "High-angle aerial view of a crowded parking lot with vehicles.",
        "duration_seconds": 31,
        "resolution": "3840×2160",
        "license_label": "Pexels Free license — verify current terms",
        "filename": "pexels-david-pickup-parking-28125313.mp4",
        "sha256": "2669831f8dc675ccae53e84121eb0fc95b4ec4a9bc753ca814e2a916d15f5824",
        "bytes": 269275222,
    },
}


def list_public_sources() -> list[dict]:
    return [
        {
            "id": source_id,
            "title": item["title"],
            "creator": item["creator"],
            "landing_page": item["landing_page"],
            "description": item["description"],
            "duration_seconds": item["duration_seconds"],
            "resolution": item["resolution"],
            "license_label": item["license_label"],
        }
        for source_id, item in PUBLIC_SOURCES.items()
    ]
