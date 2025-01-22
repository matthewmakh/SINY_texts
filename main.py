from twilio.rest import Client
import master_file

account_sid = master_file.account_SID
auth_token = master_file.auth_token
client = Client(account_sid, auth_token)



message = client.messages.create(
  from_='+18445801151',
  body=f'Hello Matthew, this is a test. \nThis is message #{i}',
  to='+19175845634'
)

print(f'message {i}: {message.sid}')