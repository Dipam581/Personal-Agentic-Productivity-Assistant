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

from DB_utils.db import add_data_to_db, query_from_database, add_to_detailsTable,delete_old_records
from datetime import datetime, timedelta, timezone


def queryDB(msg_id: str, date: str, subject: str):
#   queryData = query_from_database("gmaildata", "*", msg_id)
  llmData = "" #asyncio.run(process_email(queryData[0]["id"], queryData[0]["msg_id"], queryData[0]["msg_data"]))
  try:
    if(llmData):
      #add_to_detailsTable(llmData, msg_id, queryData[0]["id"], llmData["intent"], date, subject)
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
    print(f"Extracting body from payload: {payload}")  # Debugging the payload
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

def get_msg_Date_Subject(payload):
    headers = payload.get('headers', [])
    subject = ""
    date = ""
    for header in headers:
        if header['name'] == 'Subject':
            subject = header['value']
        if header['name'] == 'Date':
            date = header['value']
    return date, subject


def get_all_msg(user_id, creds):
    IST = timezone(timedelta(hours=5, minutes=30)) # Indian Standard Time

    now_ist = datetime.now(IST)

    time_window_minutes = 1440  # 24 hours * 60 minutes
    start_time_ist = now_ist - timedelta(minutes=time_window_minutes)
    start_ts = int(start_time_ist.timestamp())
    # No 'before' filter needed if you want everything up to now
    date_filter = f'after:{start_ts}'

    # --- END MODIFIED PART ---

    inclusive = '(Application OR application OR meeting OR LinkedIn OR Team OR Zoom OR video OR Data)'
    exclusive = '-Bank -discount -sale -sales -buy -buying ' \
                '-purchase -purchasing -free -offer -offers ' \
                '-coupon -coupons -deal -deals'

    query = f'{inclusive} {exclusive} {date_filter}'

    messages_to_process = []
    next_page_token = None
    max_results_per_call = 1 # Or 100, depending on how many you want to fetch per page

    while True:
        params = {
            "labelIds": ["INBOX", "CATEGORY_PERSONAL"],
            "q": query,
            "maxResults": max_results_per_call,
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        try:
            res = requests.get(
                f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Accept": "application/json",
                    },
                    params=params
            )
            res.raise_for_status()
            response_json = res.json()

            messages_batch = response_json.get("messages", [])
            messages_to_process.extend(messages_batch)

            next_page_token = response_json.get("nextPageToken")
            print(f"nextPageToken={next_page_token}")
            if not next_page_token:
                break

        except requests.exceptions.RequestException as e:
            print(f"Error fetching messages from Gmail API: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during message list fetching: {e}")
            break


    if not messages_to_process:
        print("No messages found matching the criteria.")
        return {"messages": []}

    # delete_old_records("gmaildata")

    for msg_ref in messages_to_process:
        try:
            msg_data = get_msg(user_id, msg_ref["id"], creds)
            payload = msg_data.get('payload', {})
            body = extract_body(payload)
            date, subject = get_msg_Date_Subject(payload)

            if body:
                print(f"Processing Message ID: {msg_ref['id']}")
                #add_data_to_db(body, msg_ref["id"])
                queryDB(msg_ref["id"], date, subject)
            else:
                print(f"Skipping Message ID {msg_ref['id']}: No extractable body found.")

        except requests.exceptions.RequestException as e:
            print(f"Error getting details for message {msg_ref['id']}: {e}")
            continue
        except Exception as e:
            print(f"An error occurred while processing message {msg_ref['id']}: {e}")
            continue

    return {"messages": [{"id": msg["id"]} for msg in messages_to_process]}


def main():
  """Shows basic usage of the Gmail API.
  Lists the user's Gmail labels.
  """
#   delete_old_records("gmaildata")
  CUR_DIR = os.path.dirname(os.path.realpath(__file__))
    # secret_path = os.path.join(CUR_DIR, "credentials.json") # Not directly used for Airflow authentication flow

  creds = None
    # Attempt to load credentials from a pre-existing token.json
  if os.path.exists("token.json"):
      creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If credentials are not valid (e.g., expired or token.json missing initially)
  if not creds or not creds.valid:
      if creds and creds.expired and creds.refresh_token:
            # If credentials exist but are expired and a refresh token is available, refresh them
          try:
              creds.refresh(Request())
                # Save the refreshed token back to token.json
              with open("token.json", "w") as token:
                  token.write(creds.to_json())
              print("Gmail API token refreshed successfully.")
          except Exception as e:
              print(f"Error refreshing Gmail API token: {e}")
              raise Exception("Failed to refresh Gmail API token. Manual re-authentication may be required.")
      else:
            # This block is executed if:
            # 1. token.json does not exist at all.
            # 2. token.json exists but is invalid and has no refresh token (e.g., manually deleted refresh_token).
            # In Airflow, we cannot perform interactive authentication (run_console or run_local_server).
            # Therefore, we raise an error, indicating that token.json must be pre-generated.
          print("Gmail API token.json not found or invalid and cannot be refreshed automatically.")
          print("Please ensure 'token.json' is present in the Airflow environment and is valid.")
          print("You need to run the authentication flow manually once (e.g., on your local machine) to generate 'token.json',")
          print("and then copy it to the location accessible by your Airflow DAGs.")
          raise Exception("Gmail API token missing or invalid. Manual pre-authentication required.")

    # If we reach here, 'creds' should be valid or an exception would have been raised.
  if creds:
      try:
          service = build("gmail", "v1", credentials=creds)
          # Verify credentials by listing labels (optional, but good for early failure)
          results = service.users().labels().list(userId="me").execute()
          print(f"Successfully connected to Gmail API. Found {len(results.get('labels', []))} labels.")
          get_all_msg(user_id, creds)

      except HttpError as error:
          print(f"An HTTP error occurred with Gmail API: {error}")
          raise # Re-raise the exception to fail the Airflow task
      except Exception as e:
          print(f"An unexpected error occurred: {e}")
          raise # Re-raise any other unexpected exceptions
  else:
        # This case should ideally be caught by the 'raise Exception' above,
        # but as a safeguard.
      print("Credentials object is None after authentication attempts. Cannot proceed.")
      raise Exception("Gmail API credentials not established.")


if __name__ == "__main__":
  main()
  # Example usage: uncomment the next line to call get_all_msg after main() and pass creds
  # get_all_msg(user_id, creds)