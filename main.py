import os.path
import requests
import asyncio
import base64

from agenticAi import process_email
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from DB_utils.db import add_data_to_db, query_from_database, add_to_detailsTable
from datetime import datetime, timedelta, timezone


def queryDB(msg_id: str):
  queryData = query_from_database("gmaildata", "*", msg_id)
  llmData = asyncio.run(process_email(queryData[0]["id"], queryData[0]["msg_id"], queryData[0]["msg_data"]))
  try:
    if(llmData):
      add_to_detailsTable(llmData, msg_id, queryData[0]["id"])
      print("Data saved successfully to details table.")
    else:
      print("No data returned from process_email.")
  except Exception as e:
    print(f"Error saving data to details table: {e}")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
user_id = "dipam.ghosh92@gmail.com"

def get_msg(user_id, msg_id, creds):
  res = requests.get(
      f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{msg_id}",
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Accept": "application/json",
        }
  )
  return res.json()


def extract_body(payload):
    if 'body' in payload and payload['body'].get('data'):
        data = payload['body']['data']
        return base64.urlsafe_b64decode(data.encode()).decode('utf-8')
    if 'parts' in payload:
        for part in payload['parts']:
            # Prefer plain text
            if part.get('mimeType') == 'text/plain' and part['body'].get('data'):
                data = part['body']['data']
                return base64.urlsafe_b64decode(data.encode()).decode('utf-8')
            # Fallback to HTML
            if part.get('mimeType') == 'text/html' and part['body'].get('data'):
                data = part['body']['data']
                return base64.urlsafe_b64decode(data.encode()).decode('utf-8')
            # Handle nested multipart
            if 'parts' in part:
                body = extract_body(part)
                if body:
                    return body
    return ""



def get_all_msg(user_id, creds):
  IST = timezone(timedelta(hours=5, minutes=30))

  now_ist = datetime.now(IST)
  today_midnight = datetime.combine(now_ist.date(), datetime.min.time(), IST)
  yesterday_midnight = today_midnight - timedelta(days= 20)
  start_ts = int(yesterday_midnight.timestamp())
  end_ts   = int(today_midnight.timestamp())   

  date_filter = f'after:{start_ts} before:{end_ts}'

  inclusive = '(Application OR application OR meeting OR LinkedIn OR Team OR Zoom OR video OR Data)'
  exclusive = '-Bank -discount -sale -sales -buy -buying ' \
                '-purchase -purchasing -free -offer -offers ' \
                '-coupon -coupons -deal -deals'

  query = f'{inclusive} {exclusive} {date_filter}'
  # print(f"Query: {query}")

  res = requests.get(
      f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages",
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Accept": "application/json",
        },
        params={
            # "maxResults": "50",
            "labelIds": ["INBOX", "CATEGORY_PERSONAL"],
            "q": query,
        }
  )

  for msg_ref in res.json().get("messages", []):
        msg_data = get_msg(user_id, msg_ref["id"], creds)
        payload = msg_data.get('payload', {})
        body = extract_body(payload)
        # print(f"Message ID: {msg_ref['id']}")
        # print("Body:", body)
        add_data_to_db(body, msg_ref["id"])
        queryDB(msg_ref["id"])

        # print("=" * 200)
  
  return res.json()


def main():
  """Shows basic usage of the Gmail API.
  Lists the user's Gmail labels.
  """
  creds = None
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    with open("token.json", "w") as token:
      token.write(creds.to_json())

  try:
    service = build("gmail", "v1", credentials=creds)
    results = service.users().labels().list(userId="me").execute()
    get_all_msg(user_id, creds)

  except HttpError as error:
    print(f"An error occurred: {error}")


if __name__ == "__main__":
  main()
  # Example usage: uncomment the next line to call get_all_msg after main() and pass creds
  # get_all_msg(user_id, creds)