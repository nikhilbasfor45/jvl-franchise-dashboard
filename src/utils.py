import json
import re
import pandas as pd
import streamlit as st

COLUMN_MAPPING = {
    "startup_name": ["startup", "startup_name", "company", "company_name", "name"],
    "sector": ["sector", "industry", "category", "vertical"],
    "city": ["city", "hq_city", "location_city"],
    "address": ["address", "hq_address", "location_address"],
    "amount": ["amount", "amount_raised", "funding_amount", "raise_amount", "funding"],
    "year": ["year", "funding_year", "raised_year"],
    "website": ["website", "web", "url", "company_website"],
    "leadership": ["leadership", "founder", "founders", "leadership_team", "leadership_founders"],
    "source_link": ["sourcelink", "source_link", "source", "article", "citation_link", "reference_link"],
    "contact": ["contact", "contact_details", "email", "phone"],
}


def load_css(path):
    with open(path, "r", encoding="utf-8") as handle:
        css = handle.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def read_excel_file(uploaded_file):
    return pd.read_excel(uploaded_file, engine="openpyxl")


def normalize_column_name(name):
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def normalize_columns(df):
    if df is None or df.empty:
        raise ValueError("Excel file is empty.")

    normalized_columns = {}
    seen = {}
    for col in df.columns:
        normalized = normalize_column_name(col)
        count = seen.get(normalized, 0) + 1
        seen[normalized] = count
        if count > 1:
            normalized = "{}_{}".format(normalized, count)
        normalized_columns[col] = normalized

    return df.rename(columns=normalized_columns)


def normalize_startup_df(df):
    df = normalize_columns(df)

    for canonical, variants in COLUMN_MAPPING.items():
        if canonical in df.columns:
            continue
        for variant in variants:
            if variant in df.columns:
                df[canonical] = df[variant]
                break

    if "startup_name" not in df.columns:
        raise ValueError("Missing required column: Startup")

    return df


def _to_int(value):
    try:
        if pd.isna(value):
            return None
        if isinstance(value, str):
            match = re.search(r"(19|20)\\d{2}", value)
            if match:
                return int(match.group(0))
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_float(value):
    try:
        if pd.isna(value):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            return float(cleaned)
    except (ValueError, TypeError):
        return None


def _to_str(value):
    if pd.isna(value):
        return None
    return str(value).strip() or None


def _parse_amount(value):
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).lower().replace(",", " ").replace("$", "").replace("us$", "").replace("₹", " ")
    text = re.sub(r"\\s+", " ", text).strip()

    scale_map = {
        "crore": 1e7,
        "cr": 1e7,
        "lakh": 1e5,
        "lac": 1e5,
        "million": 1e6,
        "mn": 1e6,
        "mil": 1e6,
        "billion": 1e9,
        "bn": 1e9,
        "thousand": 1e3,
        "k": 1e3,
    }

    matches = re.findall(r"([0-9]+(?:\\.[0-9]+)?)\\s*(crore|cr|lakh|lac|million|mn|mil|billion|bn|thousand|k)\\b", text)
    if len(matches) == 1:
        number, scale = matches[0]
        return float(number) * scale_map[scale]
    if len(matches) > 1:
        return None

    suffix_matches = re.findall(r"([0-9]+(?:\\.[0-9]+)?)(k|m|b)\\b", text)
    if len(suffix_matches) == 1:
        number, suffix = suffix_matches[0]
        suffix_map = {"k": 1e3, "m": 1e6, "b": 1e9}
        return float(number) * suffix_map[suffix]
    if len(suffix_matches) > 1:
        return None

    number_match = re.search(r"([0-9]+(?:\\.[0-9]+)?)", text)
    if number_match:
        return float(number_match.group(1))
    return None


def extract_startup_records(df):
    records = []
    for _, row in df.iterrows():
        startup_name = _to_str(row.get("startup_name"))
        if not startup_name:
            continue
        raw_payload = {k: None if pd.isna(v) else v for k, v in row.items()}
        record = {
            "startup_name": startup_name,
            "sector": _to_str(row.get("sector")),
            "city": _to_str(row.get("city")),
            "year": _to_int(row.get("year")),
            "amount": _parse_amount(row.get("amount")),
            "website": _to_str(row.get("website")),
            "leadership": _to_str(row.get("leadership")),
            "source_link": _to_str(row.get("source_link")),
            "address": _to_str(row.get("address")),
            "contact": _to_str(row.get("contact")),
        }
        record["raw_json"] = json.dumps(raw_payload, ensure_ascii=True)
        records.append(record)

    if not records:
        raise ValueError("No valid startup records found.")

    return records


def sanitize_dataframe(df, year_col="year", amount_col="amount"):
    if df is None or df.empty:
        return df
    df = df.copy()
    if year_col in df.columns:
        df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    if amount_col in df.columns:
        df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce")
    return df
