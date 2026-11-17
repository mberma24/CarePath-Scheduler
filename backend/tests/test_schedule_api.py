import pytest

# Far-future windows, so these tests never depend on the real clock.
START = "2099-01-05T14:00:00Z"
END = "2099-01-05T20:00:00Z"


def post(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_patient_and_kpass(client, *steps):
    """Create a patient and a K-pass. Each step is (duration_minutes, resource_id or None)."""
    patient = post(client, "/patients", {"name": "Ann"})
    kpass = post(client, "/kpasses", {"name": "Bone Scan"})
    for i, (minutes, resource_id) in enumerate(steps):
        body = {"name": f"Step {i}", "duration_minutes": minutes, "resource_id": resource_id}
        kpass = post(client, f"/kpasses/{kpass['id']}/steps", body)
    return patient, kpass


def find(client, patient, kpass, start=START, end=END):
    body = {"kpass_id": kpass["id"], "patient_id": patient["id"], "start": start, "end": end}
    return client.post("/schedule", json=body)


# ---------- Found / not found ----------


def test_finds_schedule_with_chained_steps(client):
    doctor = post(client, "/resources", {"name": "Dr. Lee", "type": "doctor"})
    patient, kpass = make_patient_and_kpass(client, (45, doctor["id"]), (30, None))

    response = find(client, patient, kpass)

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["start_time"] == "2099-01-05T14:00:00Z"
    assert body["end_time"] == "2099-01-05T15:15:00Z"
    assert [(s["start_time"], s["end_time"]) for s in body["steps"]] == [
        ("2099-01-05T14:00:00Z", "2099-01-05T14:45:00Z"),
        ("2099-01-05T14:45:00Z", "2099-01-05T15:15:00Z"),
    ]
    assert [s["step_id"] for s in body["steps"]] == [s["id"] for s in kpass["steps"]]
    assert [s["resource_id"] for s in body["steps"]] == [doctor["id"], None]


def test_patient_block_pushes_start_later(client):
    patient, kpass = make_patient_and_kpass(client, (30, None))
    block = {"patient_id": patient["id"], "start_time": START, "end_time": "2099-01-05T15:00:00Z"}
    post(client, "/blocks", block)
    assert find(client, patient, kpass).json()["start_time"] == "2099-01-05T15:00:00Z"


def test_resource_block_delays_only_its_step(client):
    # Rest 30, then doctor 30. Doctor busy until 15:00 -> start 14:30, doctor at 15:00.
    doctor = post(client, "/resources", {"name": "Dr. Lee", "type": "doctor"})
    patient, kpass = make_patient_and_kpass(client, (30, None), (30, doctor["id"]))
    block = {"resource_id": doctor["id"], "start_time": START, "end_time": "2099-01-05T15:00:00Z"}
    post(client, "/blocks", block)
    body = find(client, patient, kpass).json()
    assert body["start_time"] == "2099-01-05T14:30:00Z"
    assert body["steps"][1]["start_time"] == "2099-01-05T15:00:00Z"


def test_fully_blocked_returns_not_found(client):
    patient, kpass = make_patient_and_kpass(client, (30, None))
    post(client, "/blocks", {"patient_id": patient["id"], "start_time": START, "end_time": END})
    response = find(client, patient, kpass)
    assert response.status_code == 200
    assert response.json() == {"found": False, "start_time": None, "end_time": None, "steps": []}


def test_start_with_offset_matches_utc(client):
    patient, kpass = make_patient_and_kpass(client, (30, None))
    response = find(client, patient, kpass, start="2099-01-05T09:00:00-05:00")
    assert response.json()["start_time"] == "2099-01-05T14:00:00Z"


# ---------- Errors ----------


def test_missing_kpass_returns_404(client):
    patient, _ = make_patient_and_kpass(client)
    response = find(client, patient, {"id": 999})
    assert response.status_code == 404
    assert response.json()["detail"] == "K-pass not found"


def test_missing_patient_returns_404(client):
    _, kpass = make_patient_and_kpass(client, (30, None))
    response = find(client, {"id": 999}, kpass)
    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found"


def test_kpass_without_steps_returns_422(client):
    patient, kpass = make_patient_and_kpass(client)
    response = find(client, patient, kpass)
    assert response.status_code == 422
    assert response.json()["detail"] == "K-pass has no steps"


def test_kpass_longer_than_window_returns_422(client):
    patient, kpass = make_patient_and_kpass(client, (45, None))
    response = find(client, patient, kpass, end="2099-01-05T14:30:00Z")
    assert response.status_code == 422
    assert "longer than the search window" in response.json()["detail"]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param("2099-01-05T14:00:00", END, id="naive-start"),
        pytest.param(START, "2099-01-05T20:00:00", id="naive-end"),
        pytest.param(START, START, id="end-equals-start"),
        pytest.param(END, START, id="end-before-start"),
    ],
)
def test_invalid_window_returns_422(client, start, end):
    patient, kpass = make_patient_and_kpass(client, (30, None))
    assert find(client, patient, kpass, start=start, end=end).status_code == 422
