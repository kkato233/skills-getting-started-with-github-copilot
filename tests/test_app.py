from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from src import app as app_module


class RacingParticipants(list):
    def __init__(self, participants, barrier):
        super().__init__(participants)
        self.barrier = barrier

    def remove(self, email):
        self.barrier.wait()
        return super().remove(email)


def test_root_redirects_to_static_index(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/static/index.html"


def test_get_activities_returns_activity_details_and_participants(client):
    response = client.get("/activities")

    assert response.status_code == 200
    activities = response.json()
    assert activities["Chess Club"]["description"]
    assert activities["Chess Club"]["schedule"]
    assert activities["Chess Club"]["max_participants"] == 12
    assert activities["Chess Club"]["participants"] == [
        "michael@mergington.edu",
        "daniel@mergington.edu",
    ]


def test_signup_adds_participant(client):
    email = "new.student@mergington.edu"

    response = client.post("/activities/Chess Club/signup", params={"email": email})

    assert response.status_code == 200
    assert response.json() == {"message": f"Signed up {email} for Chess Club"}
    assert email in client.get("/activities").json()["Chess Club"]["participants"]


def test_signup_rejects_duplicate_participant(client):
    response = client.post(
        "/activities/Chess Club/signup",
        params={"email": "michael@mergington.edu"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Student already signed up for this activity"


def test_signup_rejects_unknown_activity(client):
    response = client.post(
        "/activities/Unknown Club/signup",
        params={"email": "new.student@mergington.edu"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"


def test_unregister_removes_participant(client):
    email = "michael@mergington.edu"

    response = client.delete(f"/activities/Chess Club/participants/{email}")

    assert response.status_code == 200
    assert response.json() == {"message": f"Unregistered {email} from Chess Club"}
    assert email not in client.get("/activities").json()["Chess Club"]["participants"]


def test_unregister_rejects_unknown_participant(client):
    response = client.delete(
        "/activities/Chess Club/participants/not-signed-up@mergington.edu"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Participant not found"


def test_unregister_handles_concurrent_requests_without_server_error():
    email = "race.student@mergington.edu"
    app_module.activities["Chess Club"]["participants"] = RacingParticipants(
        [email],
        Barrier(2),
    )

    def unregister():
        with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
            return test_client.delete(f"/activities/Chess Club/participants/{email}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [future.result() for future in [executor.submit(unregister) for _ in range(2)]]

    assert sorted(response.status_code for response in responses) == [200, 404]
    assert app_module.activities["Chess Club"]["participants"] == []


def test_unregister_rejects_unknown_activity(client):
    response = client.delete(
        "/activities/Unknown Club/participants/student@mergington.edu"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"