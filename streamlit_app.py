"""Temporary Streamlit page for diagnosing FastF1 endpoint access."""

import requests
import streamlit as st

st.set_page_config(page_title="FastF1 connection test")
st.title("FastF1 connection test")
st.caption(
    "This temporary page checks whether the deployed runtime can reach the "
    "primary Formula 1 live-timing service and FastF1's fallback mirror."
)

SESSION_PATH = (
    "/static/2026/"
    "2026-06-14_Barcelona_Grand_Prix/"
    "2026-06-14_Race/"
)
REQUEST_HEADERS = {
    "User-Agent": "BestHTTP",
    "Connection": "close",
    "TE": "identity",
    "Accept-Encoding": "gzip, identity",
}
HOSTS = (
    "https://livetiming.formula1.com",
    "https://livetiming-mirror.fastf1.dev",
)
PAGES = (
    "SessionInfo.jsonStream",
    "TimingData.jsonStream",
)

for host in HOSTS:
    st.subheader(host)
    for page in PAGES:
        url = f"{host}{SESSION_PATH}{page}"
        try:
            with requests.get(
                url,
                headers=REQUEST_HEADERS,
                timeout=20,
                stream=True,
            ) as response:
                result = {
                    "page": page,
                    "status": response.status_code,
                    "content_length": response.headers.get("Content-Length"),
                    "url": response.url,
                }
                st.write(result)
                print(result, flush=True)
        except requests.RequestException as error:
            message = f"{page}: {type(error).__name__}: {error}"
            st.error(message)
            print(message, flush=True)
