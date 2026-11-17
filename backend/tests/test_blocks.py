import pytest


def create_patient(client, name="Ann Lee"):
    response = client.post("/patients", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def create_resource(client, name="Dr. Lee", type="doctor"):
    response = client.post("/resources", json={"name": name, "type": type})
    assert response.status_code == 201, response.text
    return response.json()


def create_block(client, start, end, patient_id=None, resource_id=None, reason=None):
    body = {
        "start_time": start,
        "end_time": end,
        "patient_id": patient_id,
        "resource_id": resource_id,
        "reason": reason,
    }
    response = client.post("/blocks", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def block_ids(response):
    assert response.status_code == 200, response.text
    return [block["id"] for block in response.json()]


# ---------- Create ----------


def test_create_patient_block_converts_times_to_utc(client):
    patient = create_patient(client)
    block = create_block(
        client,
        "2026-11-18T09:00:00-05:00",
        "2026-11-18T10:00:00-05:00",
        patient_id=patient["id"],
        reason="  Work  ",
    )
    assert block["start_time"] == "2026-11-18T14:00:00Z"
    assert block["end_time"] == "2026-11-18T15:00:00Z"
    assert block["patient_id"] == patient["id"]
    assert block["resource_id"] is None
    assert block["reason"] == "Work"
    assert isinstance(block["id"], int)


def test_create_resource_block(client):
    resource = create_resource(client)
    block = create_block(
        client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", resource_id=resource["id"]
    )
    assert block["resource_id"] == resource["id"]
    assert block["patient_id"] is None
    assert block["reason"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"start_time": "2026-11-18T09:00:00"}, id="naive-start"),
        pytest.param({"end_time": "2026-11-18T10:00:00"}, id="naive-end"),
        pytest.param({"end_time": "2026-11-18T09:00:00Z"}, id="end-equals-start"),
        pytest.param({"end_time": "2026-11-18T08:00:00Z"}, id="end-before-start"),
        pytest.param({"end_time": "2026-11-18T10:00:00+01:00"}, id="end-equals-start-other-offset"),
        pytest.param({"patient_id": None}, id="no-owner"),
        pytest.param({"resource_id": "RESOURCE"}, id="both-owners"),
        pytest.param({"reason": "x" * 201}, id="reason-too-long"),
        pytest.param({"start_time": "not a date"}, id="bad-start"),
    ],
)
def test_create_block_invalid_body_returns_422(client, overrides):
    patient = create_patient(client)
    resource = create_resource(client)
    body = {
        "start_time": "2026-11-18T09:00:00Z",
        "end_time": "2026-11-18T10:00:00Z",
        "patient_id": patient["id"],
    }
    body.update(overrides)
    if body.get("resource_id") == "RESOURCE":
        body["resource_id"] = resource["id"]
    assert client.post("/blocks", json=body).status_code == 422


@pytest.mark.parametrize(
    ("owner_field", "detail"),
    [("patient_id", "Patient not found"), ("resource_id", "Resource not found")],
)
def test_create_block_missing_owner_returns_422(client, owner_field, detail):
    body = {
        "start_time": "2026-11-18T09:00:00Z",
        "end_time": "2026-11-18T10:00:00Z",
        owner_field: 999,
    }
    response = client.post("/blocks", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == detail


# ---------- List and filter ----------


def test_list_blocks_empty(client):
    assert client.get("/blocks").json() == []


def test_list_blocks_sorted_by_start_time(client):
    patient = create_patient(client)
    later = create_block(client, "2026-11-18T12:00:00Z", "2026-11-18T13:00:00Z", patient["id"])
    earlier = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", patient["id"])
    assert block_ids(client.get("/blocks")) == [earlier["id"], later["id"]]


def test_list_blocks_filters_by_owner(client):
    ann = create_patient(client, "Ann")
    bob = create_patient(client, "Bob")
    doctor = create_resource(client)
    ann_block = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", ann["id"])
    create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", bob["id"])
    doctor_block = create_block(
        client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", resource_id=doctor["id"]
    )
    by_patient = client.get("/blocks", params={"patient_id": ann["id"]})
    by_resource = client.get("/blocks", params={"resource_id": doctor["id"]})
    assert block_ids(by_patient) == [ann_block["id"]]
    assert block_ids(by_resource) == [doctor_block["id"]]


def test_list_blocks_window_returns_overlapping_blocks(client):
    patient = create_patient(client)
    pid = patient["id"]
    # Window: 10:00-12:00 UTC
    before = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", pid)
    touches_start = create_block(client, "2026-11-18T09:00:00Z", "2026-11-18T10:00:00Z", pid)
    crosses_start = create_block(client, "2026-11-18T09:30:00Z", "2026-11-18T10:30:00Z", pid)
    inside = create_block(client, "2026-11-18T10:30:00Z", "2026-11-18T11:00:00Z", pid)
    crosses_end = create_block(client, "2026-11-18T11:30:00Z", "2026-11-18T12:30:00Z", pid)
    touches_end = create_block(client, "2026-11-18T12:00:00Z", "2026-11-18T13:00:00Z", pid)
    covers = create_block(client, "2026-11-18T07:00:00Z", "2026-11-18T14:00:00Z", pid)

    params = {"start": "2026-11-18T10:00:00Z", "end": "2026-11-18T12:00:00Z"}
    ids = block_ids(client.get("/blocks", params=params))

    assert ids == [covers["id"], crosses_start["id"], inside["id"], crosses_end["id"]]
    for excluded in (before, touches_start, touches_end):
        assert excluded["id"] not in ids


def test_list_blocks_window_with_offset_matches_utc(client):
    patient = create_patient(client)
    create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", patient["id"])
    create_block(client, "2026-11-18T15:00:00Z", "2026-11-18T16:00:00Z", patient["id"])
    utc = {"start": "2026-11-18T14:00:00Z", "end": "2026-11-18T17:00:00Z"}
    offset = {"start": "2026-11-18T09:00:00-05:00", "end": "2026-11-18T12:00:00-05:00"}
    assert block_ids(client.get("/blocks", params=offset)) == block_ids(
        client.get("/blocks", params=utc)
    )
    assert len(block_ids(client.get("/blocks", params=utc))) == 1


@pytest.mark.parametrize("param", ["start", "end"])
def test_list_blocks_naive_window_returns_422(client, param):
    response = client.get("/blocks", params={param: "2026-11-18T09:00:00"})
    assert response.status_code == 422


# ---------- Get, update, delete ----------


def test_get_block(client):
    patient = create_patient(client)
    block = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", patient["id"])
    assert client.get(f"/blocks/{block['id']}").json() == block


def test_get_missing_block_returns_404(client):
    response = client.get("/blocks/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Block not found"


def test_update_block_changes_times_and_reason_keeps_owner(client):
    patient = create_patient(client)
    block = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", patient["id"])
    body = {
        "start_time": "2026-11-19T10:00:00+01:00",
        "end_time": "2026-11-19T11:30:00+01:00",
        "reason": "Moved",
    }
    response = client.put(f"/blocks/{block['id']}", json=body)
    assert response.status_code == 200
    updated = response.json()
    assert updated["start_time"] == "2026-11-19T09:00:00Z"
    assert updated["end_time"] == "2026-11-19T10:30:00Z"
    assert updated["reason"] == "Moved"
    assert updated["patient_id"] == patient["id"]
    assert client.get(f"/blocks/{block['id']}").json() == updated


def test_update_block_end_before_start_returns_422(client):
    patient = create_patient(client)
    block = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", patient["id"])
    body = {"start_time": "2026-11-18T10:00:00Z", "end_time": "2026-11-18T09:00:00Z"}
    assert client.put(f"/blocks/{block['id']}", json=body).status_code == 422


def test_update_missing_block_returns_404(client):
    body = {"start_time": "2026-11-18T08:00:00Z", "end_time": "2026-11-18T09:00:00Z"}
    assert client.put("/blocks/999", json=body).status_code == 404


def test_delete_block_returns_204_then_404(client):
    patient = create_patient(client)
    block = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", patient["id"])
    assert client.delete(f"/blocks/{block['id']}").status_code == 204
    assert client.get(f"/blocks/{block['id']}").status_code == 404


def test_delete_missing_block_returns_404(client):
    assert client.delete("/blocks/999").status_code == 404


# ---------- Cascade ----------


def test_deleting_patient_deletes_only_their_blocks(client):
    ann = create_patient(client, "Ann")
    bob = create_patient(client, "Bob")
    create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", ann["id"])
    bob_block = create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", bob["id"])
    assert client.delete(f"/patients/{ann['id']}").status_code == 204
    assert block_ids(client.get("/blocks")) == [bob_block["id"]]


def test_deleting_resource_deletes_only_its_blocks(client):
    doctor = create_resource(client, "Dr. Lee")
    scanner = create_resource(client, "Scanner 1", "scanner")
    create_block(client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", resource_id=doctor["id"])
    scanner_block = create_block(
        client, "2026-11-18T08:00:00Z", "2026-11-18T09:00:00Z", resource_id=scanner["id"]
    )
    assert client.delete(f"/resources/{doctor['id']}").status_code == 204
    assert block_ids(client.get("/blocks")) == [scanner_block["id"]]
