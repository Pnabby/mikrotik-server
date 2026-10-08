import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import app
from app.models.enums import AdminRole
from app.routes.admin_auth import get_authenticated_admin
from app.routes.auth import get_authenticated_customer


@pytest.fixture
def issue_client(support_db):
    session, customers, admin, *_ = support_db
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_authenticated_customer] = lambda: customers[0]
    app.dependency_overrides[get_authenticated_admin] = lambda: admin
    yield TestClient(app), session, customers, admin
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def submit(client, **overrides):
    result = client.post(
        "/api/account/issues",
        json={
            "subject": "WiFi connection drops",
            "message": "The network keeps dropping in the evening.",
            "room_number": "B12",
            **overrides,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_complaint_reply_attend_and_reopen_update_notification_count(issue_client):
    client, *_ = issue_client
    issue = submit(client)
    notices = client.get("/api/admin/notifications").json()
    assert notices["count"] == 1
    assert notices["items"][0]["hostel_name"] == "Flint Main"
    assert notices["items"][0]["room_number"] == "B12"
    update = client.put(
        f"/api/admin/issues/{issue['id']}",
        json={
            "reply": "We repaired the access point. Please reconnect.",
            "status": "attended",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["attended_at"]
    assert client.get("/api/admin/notifications").json()["count"] == 0
    history = client.get("/api/account/issues").json()["items"][0]
    assert history["replies"][0]["message"] == "We repaired the access point. Please reconnect."
    assert history["status"] == "attended"
    assert (
        client.put(f"/api/admin/issues/{issue['id']}", json={"status": "open"}).status_code == 200
    )
    assert client.get("/api/admin/notifications").json()["count"] == 1


def test_origin_survives_customer_move_and_customers_cannot_read_each_others_issues(issue_client):
    client, session, customers, _ = issue_client
    issue = submit(client, room_number=None)
    customers[0].router_id = "annex"
    session.commit()
    assert client.get("/api/account/issues").json()["items"][0]["hostel_name"] == "Flint Main"
    assert client.get("/api/admin/issues?router_id=main").json()["total"] == 1
    assert client.get("/api/admin/issues?router_id=annex").json()["total"] == 0
    app.dependency_overrides[get_authenticated_customer] = lambda: customers[1]
    assert client.get("/api/account/issues").json()["items"] == []
    assert issue["room_number"] is None


def test_viewer_cannot_reply_or_change_status(issue_client):
    client, _, _, admin = issue_client
    issue = submit(client)
    admin.role = AdminRole.VIEWER
    assert client.get("/api/admin/issues").status_code == 200
    result = client.put(f"/api/admin/issues/{issue['id']}", json={"reply": "A reply"})
    assert result.status_code == 403
    assert client.get("/api/admin/notifications").json()["count"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"subject": "   ", "message": "Complaint"},
        {"subject": "Complaint", "message": "   "},
        {"subject": "Complaint", "message": "Complaint", "router_id": "annex"},
        {"subject": "Complaint", "message": "x" * 5001},
    ],
)
def test_empty_oversized_and_forged_hostel_complaints_are_rejected(issue_client, payload):
    client, *_ = issue_client
    assert client.post("/api/account/issues", json=payload).status_code == 422


def test_missing_issue_and_blank_reply_are_rejected(issue_client):
    client, *_ = issue_client
    assert (
        client.put(f"/api/admin/issues/{uuid.uuid4()}", json={"status": "attended"}).status_code
        == 404
    )
    issue = submit(client)
    assert client.put(f"/api/admin/issues/{issue['id']}", json={"reply": "   "}).status_code == 422
    assert client.put(f"/api/admin/issues/{issue['id']}", json={}).status_code == 422


def test_notification_count_includes_more_than_the_five_previews(issue_client):
    client, *_ = issue_client
    for number in range(7):
        submit(client, subject=f"Complaint {number}")
    notices = client.get("/api/admin/notifications").json()
    assert notices["count"] == 7
    assert len(notices["items"]) == 5


def test_complaint_endpoints_require_a_session(issue_client):
    client, *_ = issue_client
    app.dependency_overrides.pop(get_authenticated_customer)
    app.dependency_overrides.pop(get_authenticated_admin)
    assert client.get("/api/account/issues").status_code == 401
    assert (
        client.post(
            "/api/account/issues", json={"subject": "Complaint", "message": "Complaint"}
        ).status_code
        == 401
    )
    assert client.get("/api/admin/notifications").status_code == 401
    assert client.get("/api/admin/issues").status_code == 401
