import json


def test_create_chat(test_client):
    # Arrange
    data = {"message": "Hello, AI!", "user_id": "test_user"}

    # Act
    response = test_client.post(
        "/api/chats", data=json.dumps(data), content_type="application/json"
    )

    # Assert
    assert response.status_code == 201
    response_data = json.loads(response.data)
    assert "chat_id" in response_data


def test_get_chat_history(test_client):
    # First create a chat
    data = {"message": "Hello, AI!", "user_id": "test_user"}
    response = test_client.post(
        "/api/chats", data=json.dumps(data), content_type="application/json"
    )
    chat_id = json.loads(response.data)["chat_id"]

    # Act
    response = test_client.get(f"/api/chats/{chat_id}")

    # Assert
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert "messages" in response_data
