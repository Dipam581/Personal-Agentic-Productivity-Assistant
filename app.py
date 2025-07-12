from datetime import datetime
from email.utils import parsedate_to_datetime
import json
import pandas as pd
import streamlit as st
from DB_utils.db import query_from_database
from great_tables import GT
from streamlit_extras.great_tables import great_tables
from great_tables import style, loc, md


def main():    
    st.set_page_config(page_title="Personal Agentic Productivity Assistant", page_icon=":robot_face:")
    st.title("Personal Agentic Productivity Assistant")
    st.markdown("""
        This is a personal productivity assistant that helps you manage your tasks and emails efficiently.
        You can ask it to schedule meetings, set reminders, and track your progress.
    """)
    st.sidebar.header("User Input")

    with st.spinner("Fetching your gmail data...", show_time=True):
        queryData = query_from_database("detailstable", "details, type, date, subject")
        if not queryData:
            st.error("No data found in the database.")
            return

        fullData = []
        if queryData:
            queryData.sort(
                key=lambda x: (0 if x["type"] == "schedule_meeting" else 1,parsedate_to_datetime(x["date"]))
            )
            for item in queryData:
                details_raw = item.get("details", "")
                try:
                    details = json.loads(details_raw) if isinstance(details_raw, str) else {}
                except json.JSONDecodeError:
                    details = {}

                fullData.append({
                    "company": details.get("company", " - "),
                    "Headline": item.get("subject", " - "),
                    "content": details.get("extracted", " - ")
                })

            df = pd.DataFrame(fullData)

            gt_table = (
                GT(df)
                .opt_stylize(style=3, color="gray", add_row_striping=True)
                .opt_align_table_header(align="left")
                .opt_vertical_padding(scale=0.75)
                .opt_horizontal_padding(scale=1.5)
                .opt_table_outline()
                .tab_style(
                    style=style.text(weight="bold", align="center", color="white"),
                    locations=loc.column_labels()
                )
            )

            great_tables(gt_table, width=1000)

if __name__ == "__main__":
    main()


#docker build -t airflow6:latest .
#docker compose up