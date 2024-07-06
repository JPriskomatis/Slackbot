import os
import requests
from flask import Flask, jsonify, request
from slack_sdk import WebClient
from slackeventsapi import SlackEventAdapter
from dotenv import load_dotenv
from pathlib import Path
import json
import time

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack Event Adapter
slack_event_adapter = SlackEventAdapter(os.environ['SIGNING_SECRET'], '/slack/events', app)

# Initialize Slack Web Client with bot token
client = WebClient(token=os.environ['SLACK_TOKEN'])
bot_id = client.auth_test()['user_id']

# Global variable to store pending review
pending_review = None

# Event listener for incoming messages
@slack_event_adapter.on('message')
def message(payload):
    event = payload.get('event', {})
    channel_id = event.get('channel')
    text = event.get('text')

    if text.startswith("$Hi"):
        client.chat_postMessage(channel=channel_id, text="Hello!")

# Route to handle Slack events
@app.route('/slack/events', methods=['POST'])
def slack_events():
    try:
        print("Received /slack/events request")
        print("Headers:", request.headers)
        print("Data:", request.data)
        payload = request.get_json()
        if 'challenge' in payload:
            return jsonify({'challenge': payload['challenge']}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Invalid Slack event'}), 400
    except Exception as e:
        print("Error in /slack/events:", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/slack/actions', methods=['POST'])
def slack_actions():
    global pending_review
    try:
        print("Received a request on /slack/actions")  # Log that the route was accessed
        print("Headers received:", request.headers)  # Log headers received
        print("Raw Data received:", request.data)  # Log the raw data received
        
        # Extracting payload and parsing JSON
        payload = request.form.to_dict()  # Convert form data to a dictionary
        payload_json = json.loads(payload['payload'])  # Parse payload JSON string to dictionary
        
        # Extract action details
        actions = payload_json.get('actions', [])
        for action in actions:
            action_id = action.get('action_id')
            review_text = action.get('value')

            if action_id in ['approve_button', 'deny_button']:
                print(f"BUTTON PRESSED: {action_id.capitalize()}")  # Log when approve or deny button is pressed
                pending_review = review_text
                print("Review action pending:", pending_review)
                break  # Exit loop after capturing the first action
        
        # Wait for pending_review to be set by the display_reviews endpoint
        while pending_review is None:
            time.sleep(1)  # Wait for 1 second before checking again
        
        # Determine the action based on pending_review value
        action = 'approve' if pending_review.startswith('$') else 'deny'

        pending_review = None  # Reset pending review after logging

        return jsonify({'status': 'success', 'action': action}), 200
    
    except json.JSONDecodeError as e:
        print("JSONDecodeError handling /slack/actions:", e)  # Log JSON decode errors specifically
        return jsonify({'status': 'error', 'message': 'Invalid JSON received'}), 400
    
    except Exception as e:
        print("Error handling /slack/actions:", e)  # Log any other errors encountered
        return jsonify({'status': 'error', 'message': str(e)}), 500

# New route to send messages from an external program
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    channel_id = data.get('channel_id')
    message = data.get('message')

    if not channel_id or not message:
        return jsonify({'status': 'error', 'message': 'Missing channel_id or message'}), 400

    try:
        client.chat_postMessage(channel=channel_id, text=message)
        return jsonify({'status': 'success', 'message': 'Message sent'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Function to display reviews in Slack channel
def DisplayReviews(review):
    channel_id = os.environ['SLACK_CHANNEL_ID']  # Ensure you have set this environment variable

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": review
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Approve"
                    },
                    "value": review,  # Pass the review text as value
                    "action_id": "approve_button"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Deny"
                    },
                    "value": review,
                    "action_id": "deny_button"
                }
            ]
        }
    ]

    try:
        client.chat_postMessage(channel=channel_id, blocks=blocks, text="Here is a new review:")
        print("Review posted successfully")
    except Exception as e:
        print(f"Failed to post review: {str(e)}")

# Route to handle displaying reviews and actions
@app.route('/display_reviews', methods=['POST'])
def display_reviews():
    global pending_review
    data = request.get_json()
    review = data.get('review')

    if not review:
        return jsonify({'status': 'error', 'message': 'Missing review text'}), 400

    try:
        DisplayReviews(review)

        while pending_review is None:
            time.sleep(1)  # Wait for 1 second before checking again

        print("Review action completed:", pending_review)

        # Determine the action based on pending_review value
        action = 'approve' if pending_review.startswith('$') else 'deny'

        pending_review = None  # Reset pending review after logging

        # Add a custom header to the response
        response = jsonify({'status': 'success', 'message': 'Review displayed', 'action': action})
        response.headers.add('Access-Control-Allow-Origin', '*')  # Allow cross-origin requests
        return response, 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

