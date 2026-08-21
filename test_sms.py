import os
from twilio.rest import Client

account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]

client = Client(account_sid, auth_token)

try:
    message = client.messages.create(
        body="sms_internal_alerts",
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        to=os.environ["MY_PHONE_NUMBER"]
    )

    print("Message request sent to Twilio.")
    print("Message SID:", message.sid)
    print("Status:", message.status)

except Exception as error:
    print("ERROR:")
    print(error)