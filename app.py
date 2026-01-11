import os
import sys
import json
import streamlit as st
import pandas as pd

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from db import (
    init_db,
    get_connection,
    get_meta,
    set_meta,
    replace_startups,
    get_startups_df,
    get_startup_by_id,
    get_user_rating,
    upsert_rating,
    get_user_ratings_df,
    toggle_shortlist,
    get_user_shortlist_df,
    get_leaderboard_df,
    get_ratings_export_df,
    get_shortlists_export_df,
)
from auth import verify_user, seed_default_users
from utils import (
    load_css,
    read_excel_file,
    normalize_startup_df,
    extract_startup_records,
    COLUMN_MAPPING,
    sanitize_dataframe,
)
from scoring import get_user_stats

st.set_page_config(page_title="JVL Franchise Owner Dashboard", layout="wide")
load_css(os.path.join(BASE_DIR, "assets", "styles.css"))

init_db()
seed_default_users()

if "user" not in st.session_state:
    st.session_state.user = None


def require_login():
    if st.session_state.user is None:
        st.warning("Please log in to continue.")
        return False
    return True


def login_panel():
    st.title("JVL Franchise Owner Dashboard")
    st.subheader("Secure sign-in")
    with st.form("login_form"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submit = st.form_submit_button("Sign in", key="login_submit")

    if submit:
        user = verify_user(username, password)
        if user:
            st.session_state.user = user
            st.success("Welcome back, {}".format(user["username"]))
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        else:
            st.error("Invalid credentials")


if st.session_state.user is None:
    login_panel()
    st.stop()

user = st.session_state.user
role = user["role"]

st.sidebar.markdown("<div class='sidebar-title'>JVL Dashboard</div>", unsafe_allow_html=True)
st.sidebar.markdown("Logged in as <span class='badge'>{}</span>".format(role), unsafe_allow_html=True)

pages = [
    "Explore Startups",
    "My Shortlist",
    "My Ratings",
    "Leaderboard",
]
if role == "admin":
    pages.insert(0, "Upload Data")
    pages.append("Admin Panel")

selection = st.sidebar.selectbox("Navigation", pages, key="nav_select")

if st.sidebar.button("Log out", key="logout_btn"):
    st.session_state.user = None
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def upload_data_page():
    st.title("Upload Startup Master")
    st.markdown("Upload the Excel file that contains the startup master list. The file must include a `Startup` column.")
    locked = get_meta("startup_locked") == "1"

    replace = False
    if locked:
        st.info("Startup master is locked. Only admins can replace it.")
        replace = st.checkbox("Replace existing master", key="upload_replace_master")

    upload = st.file_uploader("Upload .xlsx", type=["xlsx"], key="upload_excel")

    if upload:
        try:
            df = read_excel_file(upload)
            normalized_df = normalize_startup_df(df)
            records = extract_startup_records(normalized_df)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception:
            st.error("Unable to read the Excel file. Please verify the format.")
            return

        if locked and not replace:
            st.warning("Upload blocked. Enable replace to overwrite the existing master.")
            return

        try:
            replace_startups(records)
        except Exception as exc:
            st.error("Failed to save startups: {}".format(exc))
            return

        set_meta("startup_locked", "1")
        set_meta("startup_count", str(len(records)))
        st.success("Uploaded {} startups successfully.".format(len(records)))


def explore_page():
    st.title("Startup Explorer")
    st.markdown("Filter startups and open a detailed profile to rate and shortlist.")

    df = sanitize_dataframe(get_startups_df())
    if df.empty:
        st.info("No startups uploaded yet.")
        return

    search = st.text_input("Search by name", key="explore_search")
    sectors = sorted([x for x in df["sector"].dropna().unique()])
    cities = sorted([x for x in df["city"].dropna().unique()])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sector_filter = st.multiselect("Sector", sectors, key="explore_sector")
    with col2:
        city_filter = st.multiselect("City", cities, key="explore_city")
    with col3:
        year_filter = st.multiselect("Year", sorted(df["year"].dropna().unique()), key="explore_year")
    with col4:
        amount_range = st.slider(
            "Amount Range",
            float(df["amount"].min()) if not df["amount"].isna().all() else 0.0,
            float(df["amount"].max()) if not df["amount"].isna().all() else 1.0,
            (float(df["amount"].min()) if not df["amount"].isna().all() else 0.0,
             float(df["amount"].max()) if not df["amount"].isna().all() else 1.0),
            key="explore_amount",
        )

    filtered = df.copy()
    if search:
        filtered = filtered[filtered["startup_name"].str.contains(search, case=False, na=False)]
    if sector_filter:
        filtered = filtered[filtered["sector"].isin(sector_filter)]
    if city_filter:
        filtered = filtered[filtered["city"].isin(city_filter)]
    if year_filter:
        filtered = filtered[filtered["year"].isin(year_filter)]
    if not filtered["amount"].isna().all():
        filtered = filtered[(filtered["amount"] >= amount_range[0]) & (filtered["amount"] <= amount_range[1])]

    st.markdown("<div class='section-header'>Results</div>", unsafe_allow_html=True)
    def _display_amount(raw_json_value, numeric_value):
        if raw_json_value:
            try:
                raw_data = json.loads(raw_json_value)
            except json.JSONDecodeError:
                raw_data = {}
            for key in COLUMN_MAPPING["amount"]:
                value = raw_data.get(key)
                if value is not None and not (isinstance(value, float) and pd.isna(value)) and str(value).strip() != "":
                    return str(value).strip()
        if numeric_value is None or (isinstance(numeric_value, float) and pd.isna(numeric_value)):
            return ""
        return str(numeric_value)

    display_df = filtered[["startup_name", "sector", "city", "year", "amount", "raw_json"]].copy()
    display_df["amount"] = display_df.apply(
        lambda row: _display_amount(row.get("raw_json"), row.get("amount")),
        axis=1,
    )
    display_df = display_df.rename(
        columns={
            "startup_name": "Startup",
            "sector": "Sector",
            "city": "City",
            "year": "Year",
            "amount": "Amount",
        }
    ).fillna("")
    display_df = display_df[["Startup", "Sector", "City", "Year", "Amount"]]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if filtered.empty:
        st.info("No startups match the filters.")
        return

    startup_choice = st.selectbox(
        "Select a startup for details",
        filtered["startup_name"].tolist(),
        key="explore_startup_choice",
    )
    selected = filtered[filtered["startup_name"] == startup_choice].iloc[0]

    startup = get_startup_by_id(int(selected["id"]))
    if startup is None:
        st.error("Unable to load the startup details.")
        return

    def _safe_value(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return str(value).strip()

    def _normalize_url(url):
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return "https://{}".format(url)

    def _link_button(label, url, key):
        if not url:
            st.button(label, disabled=True, key=key)
            return
        if hasattr(st, "link_button"):
            st.link_button(label, url, key=key)
        else:
            st.markdown(f'<a href="{url}" target="_blank">{label}</a>', unsafe_allow_html=True)

    def _card_container():
        try:
            return st.container(border=True)
        except TypeError:
            return st.container()

    def _raw_value(raw_data, keys):
        for key in keys:
            value = raw_data.get(key)
            if value is not None and not (isinstance(value, float) and pd.isna(value)) and str(value).strip() != "":
                return value, key
        return None, None

    raw_data = {}
    if startup.get("raw_json"):
        try:
            raw_data = json.loads(startup["raw_json"])
        except json.JSONDecodeError:
            raw_data = {}

    used_raw_keys = set()

    def _value_with_fallback(canonical, keys):
        value = startup.get(canonical)
        if value is not None and not (isinstance(value, float) and pd.isna(value)) and str(value).strip() != "":
            return value
        raw_value, raw_key = _raw_value(raw_data, keys)
        if raw_key:
            used_raw_keys.add(raw_key)
        return raw_value

    raw_amount_value, raw_amount_key = _raw_value(raw_data, COLUMN_MAPPING["amount"])
    if raw_amount_key:
        used_raw_keys.add(raw_amount_key)
    amount_raw = raw_amount_value if raw_amount_value is not None else startup.get("amount")
    notes_text = _value_with_fallback("notes", ["notes", "summary", "description"])
    sector_value = _value_with_fallback("sector", COLUMN_MAPPING["sector"])
    city_value = _value_with_fallback("city", COLUMN_MAPPING["city"])
    year_value = _value_with_fallback("year", COLUMN_MAPPING["year"])
    address_value = _value_with_fallback("address", COLUMN_MAPPING["address"])
    leadership_value = _value_with_fallback("leadership", COLUMN_MAPPING["leadership"])
    contact_value = _value_with_fallback("contact", COLUMN_MAPPING["contact"])
    website_value = _normalize_url(_safe_value(_value_with_fallback("website", COLUMN_MAPPING["website"])))
    source_value = _normalize_url(_safe_value(_value_with_fallback("source_link", COLUMN_MAPPING["source_link"])))

    st.markdown("<div class='section-header'>Startup Detail</div>", unsafe_allow_html=True)
    with _card_container():
        st.subheader(startup["startup_name"])
        st.caption("Startup profile and key information.")

        action_cols = st.columns(3)
        with action_cols[0]:
            _link_button("Open Website", website_value, key=f"open_website_{startup['id']}")
        with action_cols[1]:
            _link_button("Open Source", source_value, key=f"open_source_{startup['id']}")
        with action_cols[2]:
            st.text_input("Website URL", value=website_value, disabled=True, key=f"website_url_{startup['id']}")

        detail_cols = st.columns(2)
        with detail_cols[0]:
            st.markdown("**Sector**")
            st.write(_safe_value(sector_value))
            st.markdown("**City**")
            st.write(_safe_value(city_value))
            st.markdown("**Year**")
            st.write(_safe_value(year_value))
            st.markdown("**Amount**")
            st.write(_safe_value(amount_raw))
            st.markdown("**Address**")
            st.write(_safe_value(address_value))
        with detail_cols[1]:
            st.markdown("**Leadership**")
            st.write(_safe_value(leadership_value))
            st.markdown("**Contact**")
            st.write(_safe_value(contact_value))
            st.markdown("**Website**")
            _link_button("Visit Website", website_value, key=f"visit_website_{startup['id']}")
            st.markdown("**Source**")
            _link_button("Open Source", source_value, key=f"open_source_detail_{startup['id']}")

    if notes_text:
        st.markdown("<div class='section-header'>Notes / Summary</div>", unsafe_allow_html=True)
        st.write(notes_text)

    exclude_keys = set(COLUMN_MAPPING.keys())
    exclude_keys.update(["notes", "summary", "description"])
    exclude_keys.update(used_raw_keys)

    additional_items = {}
    for key, value in raw_data.items():
        if key in exclude_keys:
            continue
        if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
            continue
        additional_items[key] = value

    if additional_items:
        with st.expander("Additional Details"):
            for key in sorted(additional_items.keys()):
                value = additional_items[key]
                label = key.replace("_", " ").title()
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=True)
                st.markdown(f"**{label}**")
                st.write(value)

    st.markdown("<div class='section-header'>Your Feedback</div>", unsafe_allow_html=True)

    current_rating = get_user_rating(startup["id"], user["id"])
    rating_default = int(current_rating["rating"]) if current_rating else 3
    comment_default = current_rating["comment"] if current_rating else ""

    rating = st.slider("Rating (1-5)", 1, 5, rating_default, key=f"rating_{startup['id']}")
    comment = st.text_area("Comment", value=comment_default, key=f"comment_{startup['id']}")

    if st.button("Save rating", key=f"save_rating_{startup['id']}"):
        upsert_rating(startup["id"], user["id"], rating, comment)
        st.success("Rating saved.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Toggle shortlist", key=f"toggle_shortlist_{startup['id']}"):
            added = toggle_shortlist(startup["id"], user["id"])
            msg = "Added to shortlist" if added else "Removed from shortlist"
            st.success(msg)
    with col_b:
        st.caption("Latest rating overwrites previous entry.")


def shortlist_page():
    st.title("My Shortlist")
    df = sanitize_dataframe(get_user_shortlist_df(user["id"]))
    if df.empty:
        st.info("No startups in your shortlist yet.")
        return

    st.dataframe(
        df[["startup_name", "sector", "city", "year", "amount"]],
        use_container_width=True,
        hide_index=True,
    )

    csv = df.to_csv(index=False)
    st.download_button("Export CSV", csv, file_name="my_shortlist.csv", key="shortlist_export")


def ratings_page():
    st.title("My Ratings")
    df = sanitize_dataframe(get_user_ratings_df(user["id"]))
    if df.empty:
        st.info("You have not rated any startups yet.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)


def leaderboard_page():
    st.title("Leaderboard")
    df = sanitize_dataframe(get_leaderboard_df())
    if df.empty:
        st.info("No ratings yet.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("<div class='section-header'>Top Rated Startups</div>", unsafe_allow_html=True)
    chart_df = df.head(10).set_index("startup_name")
    st.bar_chart(chart_df[["avg_rating"]])

    stats = get_user_stats(user["id"])
    st.markdown("<div class='section-header'>Your Stats</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Rated", stats["ratings_count"])
    with col2:
        st.metric("Shortlisted", stats["shortlist_count"])


def admin_panel():
    st.title("Admin Panel")
    st.markdown("Download system exports for reporting.")

    ratings_df = sanitize_dataframe(get_ratings_export_df())
    shortlists_df = sanitize_dataframe(get_shortlists_export_df())
    startups_df = sanitize_dataframe(get_startups_df())

    st.download_button("Export Ratings", ratings_df.to_csv(index=False), file_name="ratings.csv", key="export_ratings")
    st.download_button("Export Shortlists", shortlists_df.to_csv(index=False), file_name="shortlists.csv", key="export_shortlists")
    st.download_button("Export Startups", startups_df.to_csv(index=False), file_name="startups_master.csv", key="export_startups")


if selection == "Upload Data":
    upload_data_page()
elif selection == "Explore Startups":
    explore_page()
elif selection == "My Shortlist":
    shortlist_page()
elif selection == "My Ratings":
    ratings_page()
elif selection == "Leaderboard":
    leaderboard_page()
elif selection == "Admin Panel":
    admin_panel()
