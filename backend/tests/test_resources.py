import pytest


def create_resource(client, name="Dr. Lee", type="doctor"):
    response = client.post("/resources", json={"name": name, "type": type})
    assert response.status_code == 201, response.text
    return response.json()


# ---------- Create ----------


def test_create_resource_returns_201_with_id(client):
    resource = create_resource(client, "Dr. Lee", "doctor")
    assert resource["name"] == "Dr. Lee"
    assert resource["type"] == "doctor"
    assert isinstance(resource["id"], int)


def test_create_resource_strips_whitespace(client):
    resource = create_resource(client, "  Scanner 1  ", "  scanner  ")
    assert resource["name"] == "Scanner 1"
    assert resource["type"] == "scanner"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": "", "type": "doctor"}, id="empty-name"),
        pytest.param({"name": "Dr. Lee", "type": ""}, id="empty-type"),
        pytest.param({"name": "Dr. Lee", "type": "   "}, id="whitespace-type"),
        pytest.param({"name": "x" * 201, "type": "doctor"}, id="name-too-long"),
        pytest.param({"name": "Dr. Lee", "type": "x" * 51}, id="type-too-long"),
        pytest.param({"type": "doctor"}, id="missing-name"),
        pytest.param({"name": "Dr. Lee"}, id="missing-type"),
    ],
)
def test_create_resource_invalid_body_returns_422(client, body):
    assert client.post("/resources", json=body).status_code == 422


# ---------- Read ----------


def test_list_resources_empty(client):
    assert client.get("/resources").json() == []


def test_list_resources_returns_all_in_creation_order(client):
    doctor = create_resource(client, "Dr. Lee", "doctor")
    scanner = create_resource(client, "Scanner 1", "scanner")
    assert client.get("/resources").json() == [doctor, scanner]


def test_list_resources_filters_by_type(client):
    doctor = create_resource(client, "Dr. Lee", "doctor")
    create_resource(client, "Scanner 1", "scanner")
    other_doctor = create_resource(client, "Dr. Kim", "doctor")
    response = client.get("/resources", params={"type": "doctor"})
    assert response.json() == [doctor, other_doctor]


def test_list_resources_filter_with_no_match_returns_empty(client):
    create_resource(client, "Dr. Lee", "doctor")
    assert client.get("/resources", params={"type": "nmt"}).json() == []


def test_get_resource_by_id(client):
    doctor = create_resource(client)
    assert client.get(f"/resources/{doctor['id']}").json() == doctor


def test_get_missing_resource_returns_404(client):
    response = client.get("/resources/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


# ---------- Update ----------


def test_update_resource(client):
    doctor = create_resource(client)
    response = client.put(
        f"/resources/{doctor['id']}", json={"name": "Dr. Lee-Park", "type": "physician"}
    )
    assert response.status_code == 200
    assert response.json() == {"id": doctor["id"], "name": "Dr. Lee-Park", "type": "physician"}
    assert client.get(f"/resources/{doctor['id']}").json()["type"] == "physician"


def test_update_missing_resource_returns_404(client):
    body = {"name": "X", "type": "doctor"}
    assert client.put("/resources/999", json=body).status_code == 404


def test_update_resource_invalid_body_returns_422(client):
    doctor = create_resource(client)
    body = {"name": "Dr. Lee", "type": ""}
    assert client.put(f"/resources/{doctor['id']}", json=body).status_code == 422


# ---------- Delete ----------


def test_delete_resource(client):
    doctor = create_resource(client)
    response = client.delete(f"/resources/{doctor['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/resources/{doctor['id']}").status_code == 404


def test_delete_missing_resource_returns_404(client):
    assert client.delete("/resources/999").status_code == 404
