from twilio.rest import Client
import master_file  # Your Twilio credentials

# Twilio credentials from master_file
account_sid = master_file.account_SID
auth_token = master_file.auth_token
client = Client(account_sid, auth_token)

# Public URL of the CSV file
file_url = "http://<raspberry_pi_ip>/Sent_numbers.csv"

# Recipient's phone number
recipient = ""

# Send the SMS with the link
message = client.messages.create(
    from_="+18445801151",  # Your Twilio phone number
    body=f"Here's the updated CSV file: {file_url}",
    to=recipient
)

print(f"Message sent! SID: {message.sid}")
