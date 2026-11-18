import pytest


def create_kpass(client, name="Bone Scan"):
    response = client.post("/kpasses", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def add_step(client, kpass_id, name="Step", duration_minutes=15, resource_id=None, position=None):
    body = {"name": name, "duration_minutes": duration_minutes, "resource_id": resource_id}
    if position is not None:
        body["position"] = position
    response = client.post(f"/kpasses/{kpass_id}/steps", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def create_kpass_with_steps(client, names):
    kpass = create_kpass(client)
    for name in names:
        kpass = add_step(client, kpass["id"], name)
    return kpass


def create_resource(client, name="Dr. Lee", type="doctor"):
    response = client.post("/resources", json={"name": name, "type": type})
    assert response.status_code == 201, response.text
    return response.json()


def names(kpass):
    return [step["name"] for step in kpass["steps"]]


def positions(kpass):
    return [step["position"] for step in kpass["steps"]]


def ids_by_name(kpass):
    return {step["name"]: step["id"] for step in kpass["steps"]}


# ---------- Create K-pass ----------


def test_create_kpass_returns_201_with_no_steps(client):
    kpass = create_kpass(client, "Bone Scan")
    assert kpass["name"] == "Bone Scan"
    assert kpass["steps"] == []
    assert isinstance(kpass["id"], int)


def test_create_kpass_strips_whitespace(client):
    assert create_kpass(client, "  Bone Scan  ")["name"] == "Bone Scan"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": ""}, id="empty-name"),
        pytest.param({"name": "   "}, id="whitespace-name"),
        pytest.param({"name": "x" * 201}, id="name-too-long"),
        pytest.param({}, id="missing-name"),
    ],
)
def test_create_kpass_invalid_body_returns_422(client, body):
    assert client.post("/kpasses", json=body).status_code == 422


# ---------- Read K-pass ----------


def test_list_kpasses_empty(client):
    assert client.get("/kpasses").json() == []


def test_list_kpasses_returns_all_with_steps_in_order(client):
    first = create_kpass_with_steps(client, ["A", "B"])
    second = create_kpass_with_steps(client, ["C"])
    assert client.get("/kpasses").json() == [first, second]


def test_get_kpass_returns_kpass_with_steps(client):
    kpass = create_kpass_with_steps(client, ["A", "B"])
    assert client.get(f"/kpasses/{kpass['id']}").json() == kpass


def test_get_missing_kpass_returns_404(client):
    response = client.get("/kpasses/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "K-pass not found"


# ---------- Update K-pass ----------


def test_update_kpass_renames_and_keeps_steps(client):
    kpass = create_kpass_with_steps(client, ["A", "B"])
    response = client.put(f"/kpasses/{kpass['id']}", json={"name": "PET Scan"})
    assert response.status_code == 200
    assert response.json()["name"] == "PET Scan"
    assert response.json()["steps"] == kpass["steps"]


def test_update_missing_kpass_returns_404(client):
    assert client.put("/kpasses/999", json={"name": "PET Scan"}).status_code == 404


def test_update_kpass_invalid_body_returns_422(client):
    kpass = create_kpass(client)
    assert client.put(f"/kpasses/{kpass['id']}", json={"name": ""}).status_code == 422


# ---------- Delete K-pass ----------


def test_delete_kpass_returns_204_then_404(client):
    kpass = create_kpass_with_steps(client, ["A", "B"])
    assert client.delete(f"/kpasses/{kpass['id']}").status_code == 204
    assert client.get(f"/kpasses/{kpass['id']}").status_code == 404


def test_delete_kpass_deletes_its_steps(client):
    # If the step survived, it would still reference the resource and block its deletion (409).
    resource = create_resource(client)
    kpass = create_kpass(client)
    add_step(client, kpass["id"], "Doctor", resource_id=resource["id"])
    assert client.delete(f"/kpasses/{kpass['id']}").status_code == 204
    assert client.delete(f"/resources/{resource['id']}").status_code == 204


def test_delete_missing_kpass_returns_404(client):
    assert client.delete("/kpasses/999").status_code == 404


# ---------- Add step ----------


def test_add_step_returns_kpass_with_new_step(client):
    resource = create_resource(client)
    kpass = create_kpass(client)
    kpass = add_step(client, kpass["id"], "  Doctor  ", 45, resource["id"])
    [step] = kpass["steps"]
    assert step["name"] == "Doctor"
    assert step["duration_minutes"] == 45
    assert step["resource_id"] == resource["id"]
    assert step["position"] == 0
    assert isinstance(step["id"], int)


def test_add_step_without_resource_is_rest_step(client):
    kpass = add_step(client, create_kpass(client)["id"], "Rest", 30)
    assert kpass["steps"][0]["resource_id"] is None


def test_add_steps_appends_in_order(client):
    kpass = create_kpass_with_steps(client, ["A", "B", "C"])
    assert names(kpass) == ["A", "B", "C"]
    assert positions(kpass) == [0, 1, 2]


def test_add_step_at_position_shifts_later_steps(client):
    kpass = create_kpass_with_steps(client, ["A", "C"])
    kpass = add_step(client, kpass["id"], "B", position=1)
    kpass = add_step(client, kpass["id"], "Z", position=0)
    assert names(kpass) == ["Z", "A", "B", "C"]
    assert positions(kpass) == [0, 1, 2, 3]


def test_add_step_position_past_end_appends(client):
    kpass = create_kpass_with_steps(client, ["A", "B"])
    kpass = add_step(client, kpass["id"], "C", position=99)
    assert names(kpass) == ["A", "B", "C"]
    assert positions(kpass) == [0, 1, 2]


def test_add_step_accepts_max_duration(client):
    kpass = add_step(client, create_kpass(client)["id"], duration_minutes=24 * 60)
    assert kpass["steps"][0]["duration_minutes"] == 24 * 60


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": "A", "duration_minutes": 0}, id="zero-duration"),
        pytest.param({"name": "A", "duration_minutes": -15}, id="negative-duration"),
        pytest.param({"name": "A", "duration_minutes": 20}, id="not-slot-multiple"),
        pytest.param({"name": "A", "duration_minutes": 24 * 60 + 15}, id="over-24-hours"),
        pytest.param({"name": "", "duration_minutes": 15}, id="empty-name"),
        pytest.param({"name": "A"}, id="missing-duration"),
        pytest.param({"duration_minutes": 15}, id="missing-name"),
        pytest.param({"name": "A", "duration_minutes": 15, "position": -1}, id="negative-position"),
    ],
)
def test_add_step_invalid_body_returns_422(client, body):
    kpass = create_kpass(client)
    assert client.post(f"/kpasses/{kpass['id']}/steps", json=body).status_code == 422


def test_add_step_unknown_resource_returns_422(client):
    kpass = create_kpass(client)
    body = {"name": "Doctor", "duration_minutes": 15, "resource_id": 999}
    response = client.post(f"/kpasses/{kpass['id']}/steps", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "Resource not found"


def test_add_step_to_missing_kpass_returns_404(client):
    body = {"name": "A", "duration_minutes": 15}
    assert client.post("/kpasses/999/steps", json=body).status_code == 404


# ---------- Update step ----------


def test_update_step_changes_fields_and_keeps_position(client):
    resource = create_resource(client)
    kpass = create_kpass_with_steps(client, ["A", "B", "C"])
    step_id = ids_by_name(kpass)["B"]
    body = {"name": "Doctor", "duration_minutes": 60, "resource_id": resource["id"]}
    response = client.put(f"/kpasses/{kpass['id']}/steps/{step_id}", json=body)
    assert response.status_code == 200
    updated = response.json()
    assert names(updated) == ["A", "Doctor", "C"]
    assert positions(updated) == [0, 1, 2]
    step = updated["steps"][1]
    assert step["id"] == step_id
    assert step["duration_minutes"] == 60
    assert step["resource_id"] == resource["id"]


def test_update_step_from_other_kpass_returns_404(client):
    kpass = create_kpass_with_steps(client, ["A"])
    other = create_kpass_with_steps(client, ["Z"])
    step_id = ids_by_name(other)["Z"]
    body = {"name": "A", "duration_minutes": 15}
    response = client.put(f"/kpasses/{kpass['id']}/steps/{step_id}", json=body)
    assert response.status_code == 404
    assert response.json()["detail"] == "Step not found"


def test_update_missing_step_returns_404(client):
    kpass = create_kpass(client)
    body = {"name": "A", "duration_minutes": 15}
    assert client.put(f"/kpasses/{kpass['id']}/steps/999", json=body).status_code == 404


def test_update_step_unknown_resource_returns_422(client):
    kpass = create_kpass_with_steps(client, ["A"])
    step_id = ids_by_name(kpass)["A"]
    body = {"name": "A", "duration_minutes": 15, "resource_id": 999}
    response = client.put(f"/kpasses/{kpass['id']}/steps/{step_id}", json=body)
    assert response.status_code == 422


def test_update_step_invalid_body_returns_422(client):
    kpass = create_kpass_with_steps(client, ["A"])
    step_id = ids_by_name(kpass)["A"]
    body = {"name": "A", "duration_minutes": 20}
    response = client.put(f"/kpasses/{kpass['id']}/steps/{step_id}", json=body)
    assert response.status_code == 422


# ---------- Delete step ----------


def test_delete_step_closes_the_gap(client):
    kpass = create_kpass_with_steps(client, ["A", "B", "C", "D"])
    step_id = ids_by_name(kpass)["B"]
    response = client.delete(f"/kpasses/{kpass['id']}/steps/{step_id}")
    assert response.status_code == 200
    assert names(response.json()) == ["A", "C", "D"]
    assert positions(response.json()) == [0, 1, 2]
    assert client.get(f"/kpasses/{kpass['id']}").json() == response.json()


def test_add_step_after_delete_appends_at_end(client):
    kpass = create_kpass_with_steps(client, ["A", "B", "C"])
    client.delete(f"/kpasses/{kpass['id']}/steps/{ids_by_name(kpass)['A']}")
    kpass = add_step(client, kpass["id"], "D")
    assert names(kpass) == ["B", "C", "D"]
    assert positions(kpass) == [0, 1, 2]


def test_delete_step_from_other_kpass_returns_404(client):
    kpass = create_kpass_with_steps(client, ["A"])
    other = create_kpass_with_steps(client, ["Z"])
    step_id = ids_by_name(other)["Z"]
    assert client.delete(f"/kpasses/{kpass['id']}/steps/{step_id}").status_code == 404
    assert names(client.get(f"/kpasses/{other['id']}").json()) == ["Z"]


def test_delete_missing_step_returns_404(client):
    kpass = create_kpass(client)
    assert client.delete(f"/kpasses/{kpass['id']}/steps/999").status_code == 404


# ---------- Reorder steps ----------


def test_reorder_steps_saves_new_order(client):
    kpass = create_kpass_with_steps(client, ["A", "B", "C", "D"])
    ids = ids_by_name(kpass)
    body = {"step_ids": [ids["D"], ids["B"], ids["A"], ids["C"]]}
    response = client.put(f"/kpasses/{kpass['id']}/steps", json=body)
    assert response.status_code == 200
    assert names(response.json()) == ["D", "B", "A", "C"]
    assert positions(response.json()) == [0, 1, 2, 3]
    assert client.get(f"/kpasses/{kpass['id']}").json() == response.json()


def test_reorder_empty_kpass_with_empty_list(client):
    kpass = create_kpass(client)
    response = client.put(f"/kpasses/{kpass['id']}/steps", json={"step_ids": []})
    assert response.status_code == 200
    assert response.json()["steps"] == []


@pytest.mark.parametrize(
    "case",
    ["missing-id", "duplicate-id", "duplicate-same-length", "unknown-id", "other-kpass-id"],
)
def test_reorder_steps_invalid_ids_returns_422(client, case):
    kpass = create_kpass_with_steps(client, ["A", "B", "C"])
    other = create_kpass_with_steps(client, ["Z"])
    a, b, c = (step["id"] for step in kpass["steps"])
    z = other["steps"][0]["id"]
    step_ids = {
        "missing-id": [a, b],
        "duplicate-id": [a, b, c, c],
        "duplicate-same-length": [a, b, b],
        "unknown-id": [a, b, c, 999],
        "other-kpass-id": [a, b, z],
    }[case]
    response = client.put(f"/kpasses/{kpass['id']}/steps", json={"step_ids": step_ids})
    assert response.status_code == 422
    assert names(client.get(f"/kpasses/{kpass['id']}").json()) == ["A", "B", "C"]


def test_reorder_missing_kpass_returns_404(client):
    assert client.put("/kpasses/999/steps", json={"step_ids": []}).status_code == 404


# ---------- Resources used by steps ----------


def test_delete_resource_used_by_step_returns_409(client):
    resource = create_resource(client)
    add_step(client, create_kpass(client)["id"], "Doctor", resource_id=resource["id"])
    response = client.delete(f"/resources/{resource['id']}")
    assert response.status_code == 409
    assert response.json()["detail"] == "Resource is used by a K-pass step and cannot be deleted"
    assert client.get(f"/resources/{resource['id']}").status_code == 200


def test_delete_resource_after_its_step_is_deleted_returns_204(client):
    resource = create_resource(client)
    kpass = add_step(client, create_kpass(client)["id"], "Doctor", resource_id=resource["id"])
    client.delete(f"/kpasses/{kpass['id']}/steps/{kpass['steps'][0]['id']}")
    assert client.delete(f"/resources/{resource['id']}").status_code == 204


# ---------- Any resource of a type ----------


def test_add_step_with_resource_type(client):
    create_resource(client, "Dr. Lee", "doctor")
    kpass = create_kpass(client)
    body = {"name": "Consult", "duration_minutes": 30, "resource_type": "doctor"}

    response = client.post(f"/kpasses/{kpass['id']}/steps", json=body)

    assert response.status_code == 201, response.text
    step = response.json()["steps"][0]
    assert step["resource_type"] == "doctor"
    assert step["resource_id"] is None


def test_add_step_with_resource_id_and_type_returns_422(client):
    resource = create_resource(client, "Dr. Lee", "doctor")
    kpass = create_kpass(client)
    body = {
        "name": "Consult",
        "duration_minutes": 30,
        "resource_id": resource["id"],
        "resource_type": "doctor",
    }

    response = client.post(f"/kpasses/{kpass['id']}/steps", json=body)

    assert response.status_code == 422


def test_add_step_with_unknown_resource_type_returns_422(client):
    kpass = create_kpass(client)
    body = {"name": "Scan", "duration_minutes": 30, "resource_type": "scanner"}

    response = client.post(f"/kpasses/{kpass['id']}/steps", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "No resources of type 'scanner'"


def test_update_step_switches_from_resource_to_type(client):
    resource = create_resource(client, "Dr. Lee", "doctor")
    kpass = add_step(client, create_kpass(client)["id"], "Consult", 30, resource["id"])
    step_id = kpass["steps"][0]["id"]
    body = {"name": "Consult", "duration_minutes": 30, "resource_type": "doctor"}

    response = client.put(f"/kpasses/{kpass['id']}/steps/{step_id}", json=body)

    assert response.status_code == 200, response.text
    step = response.json()["steps"][0]
    assert (step["resource_id"], step["resource_type"]) == (None, "doctor")
