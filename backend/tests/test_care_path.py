import pytest

from app.schemas.care_path import MAX_STEP_MINUTES


def create_care_path(client, name="Bone Scan"):
    response = client.post("/care-paths", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def add_step(
    client, care_path_id, name="Step", duration_minutes=15, resource_id=None, position=None
):
    body = {"name": name, "duration_minutes": duration_minutes, "resource_id": resource_id}
    if position is not None:
        body["position"] = position
    response = client.post(f"/care-paths/{care_path_id}/steps", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def create_care_path_with_steps(client, names):
    care_path = create_care_path(client)
    for name in names:
        care_path = add_step(client, care_path["id"], name)
    return care_path


def create_resource(client, name="Dr. Lee", type="doctor"):
    response = client.post("/resources", json={"name": name, "type": type})
    assert response.status_code == 201, response.text
    return response.json()


def names(care_path):
    return [step["name"] for step in care_path["steps"]]


def positions(care_path):
    return [step["position"] for step in care_path["steps"]]


def ids_by_name(care_path):
    return {step["name"]: step["id"] for step in care_path["steps"]}


# ---------- Create care path ----------


def test_create_care_path_returns_201_with_no_steps(client):
    care_path = create_care_path(client, "Bone Scan")
    assert care_path["name"] == "Bone Scan"
    assert care_path["steps"] == []
    assert isinstance(care_path["id"], int)


def test_create_care_path_strips_whitespace(client):
    assert create_care_path(client, "  Bone Scan  ")["name"] == "Bone Scan"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": ""}, id="empty-name"),
        pytest.param({"name": "   "}, id="whitespace-name"),
        pytest.param({"name": "x" * 201}, id="name-too-long"),
        pytest.param({}, id="missing-name"),
    ],
)
def test_create_care_path_invalid_body_returns_422(client, body):
    assert client.post("/care-paths", json=body).status_code == 422


# ---------- Read care path ----------


def test_list_care_paths_empty(client):
    assert client.get("/care-paths").json() == []


def test_list_care_paths_returns_all_with_steps_in_order(client):
    first = create_care_path_with_steps(client, ["A", "B"])
    second = create_care_path_with_steps(client, ["C"])
    assert client.get("/care-paths").json() == [first, second]


def test_get_care_path_returns_care_path_with_steps(client):
    care_path = create_care_path_with_steps(client, ["A", "B"])
    assert client.get(f"/care-paths/{care_path['id']}").json() == care_path


def test_get_missing_care_path_returns_404(client):
    response = client.get("/care-paths/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Care path not found"


# ---------- Update care path ----------


def test_update_care_path_renames_and_keeps_steps(client):
    care_path = create_care_path_with_steps(client, ["A", "B"])
    response = client.put(f"/care-paths/{care_path['id']}", json={"name": "PET Scan"})
    assert response.status_code == 200
    assert response.json()["name"] == "PET Scan"
    assert response.json()["steps"] == care_path["steps"]


def test_update_missing_care_path_returns_404(client):
    assert client.put("/care-paths/999", json={"name": "PET Scan"}).status_code == 404


def test_update_care_path_invalid_body_returns_422(client):
    care_path = create_care_path(client)
    assert client.put(f"/care-paths/{care_path['id']}", json={"name": ""}).status_code == 422


# ---------- Delete care path ----------


def test_delete_care_path_returns_204_then_404(client):
    care_path = create_care_path_with_steps(client, ["A", "B"])
    assert client.delete(f"/care-paths/{care_path['id']}").status_code == 204
    assert client.get(f"/care-paths/{care_path['id']}").status_code == 404


def test_delete_care_path_deletes_its_steps(client):
    # If the step survived, it would still reference the resource and block its deletion (409).
    resource = create_resource(client)
    care_path = create_care_path(client)
    add_step(client, care_path["id"], "Doctor", resource_id=resource["id"])
    assert client.delete(f"/care-paths/{care_path['id']}").status_code == 204
    assert client.delete(f"/resources/{resource['id']}").status_code == 204


def test_delete_missing_care_path_returns_404(client):
    assert client.delete("/care-paths/999").status_code == 404


# ---------- Add step ----------


def test_add_step_returns_care_path_with_new_step(client):
    resource = create_resource(client)
    care_path = create_care_path(client)
    care_path = add_step(client, care_path["id"], "  Doctor  ", 45, resource["id"])
    [step] = care_path["steps"]
    assert step["name"] == "Doctor"
    assert step["duration_minutes"] == 45
    assert step["resource_id"] == resource["id"]
    assert step["position"] == 0
    assert isinstance(step["id"], int)


def test_add_step_without_resource_is_rest_step(client):
    care_path = add_step(client, create_care_path(client)["id"], "Rest", 30)
    assert care_path["steps"][0]["resource_id"] is None


def test_add_steps_appends_in_order(client):
    care_path = create_care_path_with_steps(client, ["A", "B", "C"])
    assert names(care_path) == ["A", "B", "C"]
    assert positions(care_path) == [0, 1, 2]


def test_add_step_at_position_shifts_later_steps(client):
    care_path = create_care_path_with_steps(client, ["A", "C"])
    care_path = add_step(client, care_path["id"], "B", position=1)
    care_path = add_step(client, care_path["id"], "Z", position=0)
    assert names(care_path) == ["Z", "A", "B", "C"]
    assert positions(care_path) == [0, 1, 2, 3]


def test_add_step_position_past_end_appends(client):
    care_path = create_care_path_with_steps(client, ["A", "B"])
    care_path = add_step(client, care_path["id"], "C", position=99)
    assert names(care_path) == ["A", "B", "C"]
    assert positions(care_path) == [0, 1, 2]


def test_add_step_accepts_max_duration(client):
    care_path = add_step(client, create_care_path(client)["id"], duration_minutes=MAX_STEP_MINUTES)
    assert care_path["steps"][0]["duration_minutes"] == MAX_STEP_MINUTES


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": "A", "duration_minutes": 0}, id="zero-duration"),
        pytest.param({"name": "A", "duration_minutes": -15}, id="negative-duration"),
        pytest.param({"name": "A", "duration_minutes": 20}, id="not-slot-multiple"),
        pytest.param({"name": "A", "duration_minutes": MAX_STEP_MINUTES + 15}, id="over-max"),
        pytest.param({"name": "", "duration_minutes": 15}, id="empty-name"),
        pytest.param({"name": "A"}, id="missing-duration"),
        pytest.param({"duration_minutes": 15}, id="missing-name"),
        pytest.param({"name": "A", "duration_minutes": 15, "position": -1}, id="negative-position"),
    ],
)
def test_add_step_invalid_body_returns_422(client, body):
    care_path = create_care_path(client)
    assert client.post(f"/care-paths/{care_path['id']}/steps", json=body).status_code == 422


def test_add_step_unknown_resource_returns_422(client):
    care_path = create_care_path(client)
    body = {"name": "Doctor", "duration_minutes": 15, "resource_id": 999}
    response = client.post(f"/care-paths/{care_path['id']}/steps", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "Resource not found"


def test_add_step_to_missing_care_path_returns_404(client):
    body = {"name": "A", "duration_minutes": 15}
    assert client.post("/care-paths/999/steps", json=body).status_code == 404


# ---------- Update step ----------


def test_update_step_changes_fields_and_keeps_position(client):
    resource = create_resource(client)
    care_path = create_care_path_with_steps(client, ["A", "B", "C"])
    step_id = ids_by_name(care_path)["B"]
    body = {"name": "Doctor", "duration_minutes": 60, "resource_id": resource["id"]}
    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)
    assert response.status_code == 200
    updated = response.json()
    assert names(updated) == ["A", "Doctor", "C"]
    assert positions(updated) == [0, 1, 2]
    step = updated["steps"][1]
    assert step["id"] == step_id
    assert step["duration_minutes"] == 60
    assert step["resource_id"] == resource["id"]


def test_update_step_from_other_care_path_returns_404(client):
    care_path = create_care_path_with_steps(client, ["A"])
    other = create_care_path_with_steps(client, ["Z"])
    step_id = ids_by_name(other)["Z"]
    body = {"name": "A", "duration_minutes": 15}
    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)
    assert response.status_code == 404
    assert response.json()["detail"] == "Step not found"


def test_update_missing_step_returns_404(client):
    care_path = create_care_path(client)
    body = {"name": "A", "duration_minutes": 15}
    assert client.put(f"/care-paths/{care_path['id']}/steps/999", json=body).status_code == 404


def test_update_step_unknown_resource_returns_422(client):
    care_path = create_care_path_with_steps(client, ["A"])
    step_id = ids_by_name(care_path)["A"]
    body = {"name": "A", "duration_minutes": 15, "resource_id": 999}
    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)
    assert response.status_code == 422


def test_update_step_invalid_body_returns_422(client):
    care_path = create_care_path_with_steps(client, ["A"])
    step_id = ids_by_name(care_path)["A"]
    body = {"name": "A", "duration_minutes": 20}
    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)
    assert response.status_code == 422


# ---------- Delete step ----------


def test_delete_step_closes_the_gap(client):
    care_path = create_care_path_with_steps(client, ["A", "B", "C", "D"])
    step_id = ids_by_name(care_path)["B"]
    response = client.delete(f"/care-paths/{care_path['id']}/steps/{step_id}")
    assert response.status_code == 200
    assert names(response.json()) == ["A", "C", "D"]
    assert positions(response.json()) == [0, 1, 2]
    assert client.get(f"/care-paths/{care_path['id']}").json() == response.json()


def test_add_step_after_delete_appends_at_end(client):
    care_path = create_care_path_with_steps(client, ["A", "B", "C"])
    client.delete(f"/care-paths/{care_path['id']}/steps/{ids_by_name(care_path)['A']}")
    care_path = add_step(client, care_path["id"], "D")
    assert names(care_path) == ["B", "C", "D"]
    assert positions(care_path) == [0, 1, 2]


def test_delete_step_from_other_care_path_returns_404(client):
    care_path = create_care_path_with_steps(client, ["A"])
    other = create_care_path_with_steps(client, ["Z"])
    step_id = ids_by_name(other)["Z"]
    assert client.delete(f"/care-paths/{care_path['id']}/steps/{step_id}").status_code == 404
    assert names(client.get(f"/care-paths/{other['id']}").json()) == ["Z"]


def test_delete_missing_step_returns_404(client):
    care_path = create_care_path(client)
    assert client.delete(f"/care-paths/{care_path['id']}/steps/999").status_code == 404


# ---------- Reorder steps ----------


def test_reorder_steps_saves_new_order(client):
    care_path = create_care_path_with_steps(client, ["A", "B", "C", "D"])
    ids = ids_by_name(care_path)
    body = {"step_ids": [ids["D"], ids["B"], ids["A"], ids["C"]]}
    response = client.put(f"/care-paths/{care_path['id']}/steps", json=body)
    assert response.status_code == 200
    assert names(response.json()) == ["D", "B", "A", "C"]
    assert positions(response.json()) == [0, 1, 2, 3]
    assert client.get(f"/care-paths/{care_path['id']}").json() == response.json()


def test_reorder_empty_care_path_with_empty_list(client):
    care_path = create_care_path(client)
    response = client.put(f"/care-paths/{care_path['id']}/steps", json={"step_ids": []})
    assert response.status_code == 200
    assert response.json()["steps"] == []


@pytest.mark.parametrize(
    "case",
    ["missing-id", "duplicate-id", "duplicate-same-length", "unknown-id", "other-care-path-id"],
)
def test_reorder_steps_invalid_ids_returns_422(client, case):
    care_path = create_care_path_with_steps(client, ["A", "B", "C"])
    other = create_care_path_with_steps(client, ["Z"])
    a, b, c = (step["id"] for step in care_path["steps"])
    z = other["steps"][0]["id"]
    step_ids = {
        "missing-id": [a, b],
        "duplicate-id": [a, b, c, c],
        "duplicate-same-length": [a, b, b],
        "unknown-id": [a, b, c, 999],
        "other-care-path-id": [a, b, z],
    }[case]
    response = client.put(f"/care-paths/{care_path['id']}/steps", json={"step_ids": step_ids})
    assert response.status_code == 422
    assert names(client.get(f"/care-paths/{care_path['id']}").json()) == ["A", "B", "C"]


def test_reorder_missing_care_path_returns_404(client):
    assert client.put("/care-paths/999/steps", json={"step_ids": []}).status_code == 404


# ---------- Resources used by steps ----------


def test_delete_resource_used_by_step_returns_409(client):
    resource = create_resource(client)
    add_step(client, create_care_path(client)["id"], "Doctor", resource_id=resource["id"])
    response = client.delete(f"/resources/{resource['id']}")
    assert response.status_code == 409
    assert response.json()["detail"] == "Resource is used by a care path step and cannot be deleted"
    assert client.get(f"/resources/{resource['id']}").status_code == 200


def test_delete_resource_after_its_step_is_deleted_returns_204(client):
    resource = create_resource(client)
    care_path = add_step(
        client, create_care_path(client)["id"], "Doctor", resource_id=resource["id"]
    )
    client.delete(f"/care-paths/{care_path['id']}/steps/{care_path['steps'][0]['id']}")
    assert client.delete(f"/resources/{resource['id']}").status_code == 204


# ---------- Any resource of a type ----------


def test_add_step_with_resource_type(client):
    create_resource(client, "Dr. Lee", "doctor")
    care_path = create_care_path(client)
    body = {"name": "Consult", "duration_minutes": 30, "resource_type": "doctor"}

    response = client.post(f"/care-paths/{care_path['id']}/steps", json=body)

    assert response.status_code == 201, response.text
    step = response.json()["steps"][0]
    assert step["resource_type"] == "doctor"
    assert step["resource_id"] is None


def test_add_step_with_resource_id_and_type_returns_422(client):
    resource = create_resource(client, "Dr. Lee", "doctor")
    care_path = create_care_path(client)
    body = {
        "name": "Consult",
        "duration_minutes": 30,
        "resource_id": resource["id"],
        "resource_type": "doctor",
    }

    response = client.post(f"/care-paths/{care_path['id']}/steps", json=body)

    assert response.status_code == 422


def test_add_step_with_unknown_resource_type_returns_422(client):
    care_path = create_care_path(client)
    body = {"name": "Scan", "duration_minutes": 30, "resource_type": "scanner"}

    response = client.post(f"/care-paths/{care_path['id']}/steps", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "No resources of type 'scanner'"


def test_update_step_switches_from_resource_to_type(client):
    resource = create_resource(client, "Dr. Lee", "doctor")
    care_path = add_step(client, create_care_path(client)["id"], "Consult", 30, resource["id"])
    step_id = care_path["steps"][0]["id"]
    body = {"name": "Consult", "duration_minutes": 30, "resource_type": "doctor"}

    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)

    assert response.status_code == 200, response.text
    step = response.json()["steps"][0]
    assert (step["resource_id"], step["resource_type"]) == (None, "doctor")


# ---------- A care path must fit in one clinic day ----------


def test_add_step_that_makes_care_path_longer_than_a_clinic_day_returns_422(client):
    care_path = add_step(client, create_care_path(client)["id"], duration_minutes=MAX_STEP_MINUTES)
    body = {"name": "Extra", "duration_minutes": 15}

    response = client.post(f"/care-paths/{care_path['id']}/steps", json=body)

    assert response.status_code == 422
    assert "longer than a clinic day" in response.json()["detail"]


def test_update_step_that_makes_care_path_too_long_returns_422(client):
    care_path = add_step(client, create_care_path(client)["id"], duration_minutes=60)
    care_path = add_step(client, care_path["id"], duration_minutes=60)
    step_id = care_path["steps"][0]["id"]
    body = {"name": "Step", "duration_minutes": MAX_STEP_MINUTES}

    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)

    assert response.status_code == 422


def test_update_step_within_a_clinic_day_is_allowed(client):
    care_path = add_step(client, create_care_path(client)["id"], duration_minutes=MAX_STEP_MINUTES)
    step_id = care_path["steps"][0]["id"]
    body = {"name": "Step", "duration_minutes": MAX_STEP_MINUTES - 15}

    response = client.put(f"/care-paths/{care_path['id']}/steps/{step_id}", json=body)

    assert response.status_code == 200, response.text
