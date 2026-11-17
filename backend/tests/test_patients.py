import pytest


def create_patient(client, name="Ana"):
    response = client.post("/patients", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


# ---------- Create ----------


def test_create_patient_returns_201_with_id(client):
    patient = create_patient(client, "Ana")
    assert patient["name"] == "Ana"
    assert isinstance(patient["id"], int)


def test_create_patient_strips_whitespace(client):
    assert create_patient(client, "  Ana  ")["name"] == "Ana"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": ""}, id="empty"),
        pytest.param({"name": "   "}, id="whitespace-only"),
        pytest.param({"name": "x" * 201}, id="too-long"),
        pytest.param({}, id="missing-name"),
    ],
)
def test_create_patient_invalid_body_returns_422(client, body):
    assert client.post("/patients", json=body).status_code == 422


# ---------- Read ----------


def test_list_patients_empty(client):
    assert client.get("/patients").json() == []


def test_list_patients_returns_all_in_creation_order(client):
    ana = create_patient(client, "Ana")
    bo = create_patient(client, "Bo")
    assert client.get("/patients").json() == [ana, bo]


def test_get_patient_by_id(client):
    ana = create_patient(client)
    assert client.get(f"/patients/{ana['id']}").json() == ana


def test_get_missing_patient_returns_404(client):
    response = client.get("/patients/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


# ---------- Update ----------


def test_update_patient(client):
    ana = create_patient(client)
    response = client.put(f"/patients/{ana['id']}", json={"name": "Ana B"})
    assert response.status_code == 200
    assert response.json() == {"id": ana["id"], "name": "Ana B"}
    assert client.get(f"/patients/{ana['id']}").json()["name"] == "Ana B"


def test_update_missing_patient_returns_404(client):
    assert client.put("/patients/999", json={"name": "X"}).status_code == 404


def test_update_patient_invalid_body_returns_422(client):
    ana = create_patient(client)
    assert client.put(f"/patients/{ana['id']}", json={"name": ""}).status_code == 422


# ---------- Delete ----------


def test_delete_patient(client):
    ana = create_patient(client)
    response = client.delete(f"/patients/{ana['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/patients/{ana['id']}").status_code == 404


def test_delete_missing_patient_returns_404(client):
    assert client.delete("/patients/999").status_code == 404
