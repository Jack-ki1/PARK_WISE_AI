from app.services.public_sources import PUBLIC_SOURCES


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_dashboard_does_not_fabricate_metrics(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["total_videos"] == 0
    assert summary["has_data"] is False
    assert summary["latest_video_id"] is None
    assert summary["occupancy_percent"] is None
    assert summary["peak_vehicles_observed"] is None


def test_only_curated_public_sources_are_exposed(client):
    response = client.get("/api/public-sources")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert {item["id"] for item in items} == set(PUBLIC_SOURCES)
    assert all(item["landing_page"].startswith("https://www.pexels.com/video/") for item in items)
    assert all("creator" in item for item in items)


def test_arbitrary_public_source_id_is_rejected_without_network(client):
    response = client.post("/api/public-sources/http://127.0.0.1:80/admin/fetch")
    assert response.status_code in {404, 405}


def test_video_list_is_empty_on_fresh_database(client):
    response = client.get("/api/videos")
    assert response.status_code == 200
    assert response.json() == []


def test_public_configuration_exposes_real_nonsecret_runtime_settings(client):
    response = client.get("/api/config/public")
    assert response.status_code == 200
    config = response.json()
    assert config["model"]
    assert 0 < config["confidence"] <= 1
    assert config["image_size"] > 0
    assert config["frame_stride"] > 0
    assert "max_upload_mb" in config
