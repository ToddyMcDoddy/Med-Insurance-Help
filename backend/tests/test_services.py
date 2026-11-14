import json
from pathlib import Path


SERVICES_FILE = (
    Path(__file__).parents[1]
    / "app"
    / "mock_data"
    / "services.json"
)


def test_services_file_is_valid_and_labeled_illustrative():
    data = json.loads(SERVICES_FILE.read_text())

    assert data["currency"] == "USD"
    assert "illustrative" in data["label"].lower()
    assert "synthetic" in data["disclaimer"].lower()
    assert data["services"]


def test_service_entries_have_valid_cost_sharing():
    data = json.loads(SERVICES_FILE.read_text())

    for service in data["services"]:
        assert service["service_id"]
        assert service["service_name"]
        assert service["illustrative_allowed_amount"] >= 0

        if service["kind"] == "copay":
            assert service["copay_type"] in {
                "primary_care", "specialist", "er"
            }
        else:
            assert service["kind"] == "coinsurance"
            assert service["copay_type"] is None


def test_service_ids_are_unique():
    data = json.loads(SERVICES_FILE.read_text())
    ids = [service["service_id"] for service in data["services"]]

    assert len(ids) == len(set(ids))
