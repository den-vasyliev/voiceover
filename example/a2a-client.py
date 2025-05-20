import requests
import uuid
 
# 1. Discover the agent by fetching its Agent Card
AGENT_BASE_URL = "http://127.0.0.1:5001"
agent_card_url = f"{AGENT_BASE_URL}/.well-known/agent.json"
response = requests.get(agent_card_url)
if response.status_code != 200:
    raise RuntimeError(f"Failed to get agent card: {response.status_code}")
agent_card = response.json()
print("Discovered Agent:", agent_card["name"], "-", agent_card.get("description", ""))
 
# 2. Prepare a task request for the agent
task_id = str(uuid.uuid4())  # generate a random unique task ID
session_id = str(uuid.uuid4())  # generate a random unique session ID
user_text = "What is the status of my cluster?"
task_payload = {
    "id": task_id,
    "sessionId": session_id,  # include sessionId
    "acceptedOutputModes": ["text"],  # specify accepted output modes
    "message": {
        "role": "user",
        "parts": [
            {"type": "text", "text": user_text}  # include type in parts
        ]
    }
}
jsonrpc_payload = {
    "jsonrpc": "2.0",
    "id": task_id,
    "method": "tasks/send",
    "params": task_payload
}
print(f"Sending task {task_id} to agent with message: '{user_text}'")
 
# 3. Send the task to the agent's tasks/send endpoint
tasks_send_url = f"{AGENT_BASE_URL}/tasks/send"
result = requests.post(tasks_send_url, json=jsonrpc_payload)
if result.status_code != 200:
    raise RuntimeError(f"Task request failed: {result.status_code}, {result.text}")
task_response = result.json()
result_obj = task_response.get("result", {})
# 4. Process the agent's response
# The response should contain the task ID, status, and the messages (including the agent's reply).
if result_obj.get("status", {}).get("state") == "completed":
    messages = result_obj.get("messages", [])

    # If messages is empty, try to get the message from status
    if not messages and "status" in result_obj and "message" in result_obj["status"]:
        agent_message = result_obj["status"]["message"]
        messages = [agent_message]

    if messages:
        agent_message = messages[-1]  # last message (from agent)
        agent_reply_text = ""
        for part in agent_message.get("parts", []):
            if "text" in part:
                agent_reply_text += part["text"]
        print("Agent's reply:", agent_reply_text)
    else:
        print("No messages in response!")
else:
    print("Task did not complete. Status:", result_obj.get("status"))