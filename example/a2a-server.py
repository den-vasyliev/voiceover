from flask import Flask, request, jsonify
 
app = Flask(__name__)
 
# Define the Agent Card data (metadata about this agent)
AGENT_CARD = {
    "name": "EchoAgent",
    "description": "A simple agent that echoes back user messages.",
    "url": "http://localhost:5001",  # The base URL where this agent is hosted
    "version": "1.0",
    "capabilities": {
        "streaming": False,           # This agent doesn't support streaming responses
        "pushNotifications": False    # No push notifications in this simple example
    }
    # (In a full Agent Card, there could be more fields like authentication info, etc.)
}
 
# Serve the Agent Card at the well-known URL.
@app.get("/.well-known/agent.json")
def get_agent_card():
    """Endpoint to provide this agent's metadata (Agent Card)."""
    return jsonify(AGENT_CARD)
 
# Handle incoming task requests at the A2A endpoint.
@app.post("/tasks/send")
def handle_task():
    """Endpoint for A2A clients to send a new task (with an initial user message)."""
    req = request.get_json()  # parse incoming JSON request
    # Check for JSON-RPC 2.0 envelope
    if isinstance(req, dict) and req.get("jsonrpc") == "2.0" and "params" in req:
        jsonrpc_id = req.get("id")
        task_request = req["params"]
    else:
        jsonrpc_id = None
        task_request = req
    # Extract the task ID and the user's message text from the request.
    task_id = task_request.get("id")
    user_message = ""
    try:
        # According to A2A spec, the user message is in task_request["message"]["parts"][0]["text"]
        user_message = task_request["message"]["parts"][0]["text"]
    except Exception as e:
        error_resp = {"error": "Invalid request format"}
        if jsonrpc_id is not None:
            return jsonify({"jsonrpc": "2.0", "id": jsonrpc_id, "error": error_resp}), 400
        return jsonify(error_resp), 400

    # For this simple agent, the "processing" is just echoing the message back.
    agent_reply_text = f"Hello! You said: '{user_message}'"

    # Formulate the response in A2A Task format.
    # We'll return a Task object with the final state = 'completed' and the agent's message.
    response_task = {
        "id": task_id,
        "status": {"state": "completed"},
        "messages": [
            task_request.get("message", {}),             # include the original user message in history
            {
                "role": "agent",                        # the agent's reply
                "parts": [{"text": agent_reply_text}]   # agent's message content as a TextPart
            }
        ]
        # We could also include an "artifacts" field if the agent returned files or other data.
    }
    # If JSON-RPC, wrap the response
    if jsonrpc_id is not None:
        return jsonify({"jsonrpc": "2.0", "id": jsonrpc_id, "result": response_task})
    return jsonify(response_task)
 
# Run the Flask app (A2A server) if this script is executed directly.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
    