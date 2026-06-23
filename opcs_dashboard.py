#!/usr/bin/env python3
"""
OP&CS Operations Dashboard — Streamlit App
4 Pages: Dashboard | Raw Data | Detail View | CS Print List

Usage:
    streamlit run opcs_dashboard.py

Requirements: pandas openpyxl streamlit
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="OP&CS 作業排程",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
CUTOFF_HOUR   = 11
CUTOFF_MINUTE = 30

# Dispatch rules: customer key (uppercase substring match) → {destination key (uppercase): rule}
# Destination matched against "Ship To Country" column in raw data
RULES_RAW = {
    "EDOM TECHNOLOGY":           {"HK": "W2/W5", "TW": "W4"},
    "BANG TAI":                  {"HK": "W2/W5"},
    "WT MICROELECTRONICS":       {"HK": "Everyday", "TW": "W2/W4"},
    "ARROW ASIA PAC":            {"HK": "W2/W4"},
    "HMD KOREA":                 {"KR": "W2"},
    "ARROW CENTRAL EUROPE":      {"NETHERLANDS": "W4", "NL": "W4"},
    "ARROW ELECTRONICS ASIA":    {"MALAYSIA": "W2/W4", "MY": "W2/W4"},
    "UNIVERSAL SCIENTIFIC":      {"TW": "W3", "CN": "W3"},
    "MOUSER":                    {"*": "Everyday"},
    "DIGIKEY":                   {"*": "Everyday"},
    "AVNET":                     {"*": "Everyday"},
    "ARROW COMPONENTS MX":       {"MX": "Everyday"},
    "FORTUNE TECH":              {"*": "W5"},   # Abroad / any destination → W5
    "SCHENKER":                  {"SG": "W2/W4"},
    "PANGAEA":                   {"HK": "W2/W4"},
    "FEDEX":                     {"*": "FEDEX"},
    "DHL":                       {"*": "DHL"},
}

WEEKDAY_MAP = {0: "W1", 1: "W2", 2: "W3", 3: "W4", 4: "W5"}

WORK_STATUS_COLORS = {
    "未撿貨":       "#3B6D11",
    "已撿待包":     "#854F0B",
    "已包待出_GO":  "#185FA5",
    "已包待出_X":   "#A32D2D",
}

PRIORITY_COLORS = {
    "P1": "#E24B4A",
    "P2": "#EF9F27",
    "P3": "#3B6D11",
    "P4": "#888888",
}

# ─────────────────────────────────────────────
# DATA LOADING & PROCESSING
# ─────────────────────────────────────────────
@st.cache_data(show_spinner="載入資料中…")
def load_data(file1_path: str, file2_path: str) -> pd.DataFrame:
    """Load and merge both Excel files."""
    dfs = []
    for path in [file1_path, file2_path]:
        df = pd.read_excel(path, sheet_name="Open Delivery Notes", header=1)
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def process_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all business logic: work status, KPI date, dispatch, priority."""
    today = date.today()
    today_w = WEEKDAY_MAP.get(today.weekday(), "")

    # ── KPI date (New CRSD base + 12:00 rule) ──
    df["New CRSD"] = pd.to_datetime(df["New CRSD"], errors="coerce").dt.date
    df["DN Created Date/Time"] = pd.to_datetime(df["DN Created Date/Time"], errors="coerce")
    df["dn_date"] = df["DN Created Date/Time"].dt.date

    latest_dn_date = df["dn_date"].dropna().max()

    def kpi_date(row):
        crsd = row["New CRSD"]
        dn = row["DN Created Date/Time"]
        if pd.isna(dn) or pd.isna(crsd):
            return crsd
        if dn.date() == latest_dn_date and (dn.hour, dn.minute) >= (CUTOFF_HOUR, CUTOFF_MINUTE):
            return crsd + timedelta(days=1)
        return crsd

    df["kpi_date"] = df.apply(kpi_date, axis=1)
    df["days_to_kpi"] = df["kpi_date"].apply(
        lambda d: (d - today).days if pd.notna(d) else 999
    )

    # ── Work Status ──
    def work_status(row):
        pick = str(row.get("Picking Status", ""))
        pack = str(row.get("Packing Status", ""))
        sp   = str(row.get("Special Processing", ""))
        if "A - Not yet" in pick:
            return "未撿貨"
        if "C - Completely" in pick and "Not Relevant" in pack:
            return "已撿待包"
        if "C - Completely" in pick and "C - Completely" in pack:
            return "已包待出_X" if sp.strip() == "X" else "已包待出_GO"
        return "其他"

    df["work_status"] = df.apply(work_status, axis=1)

    # ── Column detection ──
    def find_col(df, *keywords):
        """Find first column whose name contains any of the keywords (case-insensitive)."""
        for kw in keywords:
            for c in df.columns:
                if kw.lower() in c.lower():
                    return c
        return None

    customer_col   = find_col(df, "sold-to name", "sold to name", "customer name", "customer")
    if customer_col not in df.columns:
        customer_col = find_col(df, "sold") or df.columns[0]

    # Ship To Country — used for dispatch destination matching
    ship_country_col = find_col(df, "ship to country", "ship-to country", "shipto country", "country")
    incoterms_col    = find_col(df, "incoterms", "inco term", "payment code", "terms")

    # ── Dispatch rule lookup ──
    def get_dispatch_rule(customer: str, ship_country: str) -> str:
        cust_upper    = str(customer).upper()
        country_upper = str(ship_country).upper().strip()
        # FEDEX / DHL shortcut
        if "FEDEX" in cust_upper: return "FEDEX"
        if "DHL"   in cust_upper: return "DHL"
        for key, dest_rules in RULES_RAW.items():
            if key.upper() in cust_upper:
                for dest_key, rule in dest_rules.items():
                    if dest_key == "*":
                        return rule
                    if dest_key.upper() in country_upper or country_upper in dest_key.upper():
                        return rule
        return ""

    df["dispatch_rule"] = df.apply(
        lambda r: get_dispatch_rule(
            r.get(customer_col, ""),
            r.get(ship_country_col, "") if ship_country_col else ""
        ),
        axis=1
    )

    def dispatch_today_fn(rule: str) -> bool:
        if not rule:
            return False
        if rule in ("Everyday", "FEDEX", "DHL", "T3EX"):
            return True
        tokens = [x.strip() for x in rule.split("/")]
        return today_w in tokens

    df["dispatch_today"] = df["dispatch_rule"].apply(dispatch_today_fn)
    df["today_w"] = today_w

    # ── Priority ──
    def priority(row):
        days = row["days_to_kpi"]
        picked = "C - Completely" in str(row.get("Picking Status", ""))
        if days <= 0:
            return "P1"
        if days <= 2:
            return "P2"
        if row["dispatch_today"] and not picked:
            return "P2"
        if days <= 5:
            return "P3"
        return "P4"

    df["priority"] = df.apply(priority, axis=1)

    # ── KPI bucket ──
    def kpi_bucket(days):
        if days <= 0:   return "今日必出"
        if days == 1:   return "明天"
        if days <= 4:   return "本週"
        if days <= 11:  return "下週"
        return "中長期"

    df["kpi_bucket"] = df["days_to_kpi"].apply(kpi_bucket)

    # ── Customer display: INCOTERMS-CUSTOMER NAME ──
    if incoterms_col and incoterms_col in df.columns:
        df["customer_display"] = (
            df[incoterms_col].astype(str).str.strip().str.upper()
            + "-"
            + df[customer_col].astype(str).str.strip().str.upper()
        )
        # Clean up "NAN-..." cases
        df["customer_display"] = df["customer_display"].str.replace(r"^NAN-", "", regex=True)
    else:
        df["customer_display"] = df[customer_col].astype(str).str.strip()

    # ── dispatch_rule_display: hide "Everyday" ──
    df["dispatch_rule_display"] = df["dispatch_rule"].apply(
        lambda r: "" if r == "Everyday" else r
    )

    return df, customer_col


# ─────────────────────────────────────────────
# SIDEBAR — file upload & navigation
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📦 OP&CS 作業排程")
    st.markdown("---")

    page = st.radio(
        "頁面導航",
        ["📊 Dashboard", "📋 Raw Data", "🔍 Detail View", "🖨 CS Print List"],
        index=st.session_state.get("page_index", 0),
        key="nav_radio",
    )

    st.markdown("---")
    st.markdown("### 📂 上傳資料")

    f1 = st.file_uploader("Open DN — CHBT, AK3T", type=["xlsx"], key="f1")
    f2 = st.file_uploader("Open DN — ASEM, A3TA, ASEA", type=["xlsx"], key="f2")

    st.markdown("---")
    today_disp = date.today()
    wd_label = WEEKDAY_MAP.get(today_disp.weekday(), "")
    wd_cn = {"W1": "一", "W2": "二", "W3": "三", "W4": "四", "W5": "五"}.get(wd_label, "")
    st.markdown(f"**今天：** {today_disp}  \n**{wd_label} (星期{wd_cn})**")
    st.caption("KPI 截止點：11:30 (New CRSD 基準)")


# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
if not f1 or not f2:
    st.info("👈 請在左側上傳兩份 Open Delivery Notes Excel 檔案")
    st.stop()

# Save to temp files for caching
import tempfile, os

@st.cache_data(show_spinner=False)
def load_from_bytes(b1: bytes, b2: bytes) -> pd.DataFrame:
    import io
    dfs = []
    for b in [b1, b2]:
        df = pd.read_excel(io.BytesIO(b), sheet_name="Open Delivery Notes", header=1)
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

raw_df = load_from_bytes(f1.read(), f2.read())
df, customer_col = process_data(raw_df.copy())

# Reset file pointers
f1.seek(0); f2.seek(0)


# ─────────────────────────────────────────────
# HELPER: navigate to detail view
# ─────────────────────────────────────────────
def go_to_detail(filter_key: str, filter_val):
    st.session_state["detail_filter_key"]  = filter_key
    st.session_state["detail_filter_val"]  = filter_val
    st.session_state["page_index"]         = 2
    st.rerun()


# ══════════════════════════════════════════════
# PAGE 1 — DASHBOARD
# ══════════════════════════════════════════════
if page == "📊 Dashboard":

    today = date.today()

    # ── Totals by work_status ──
    counts = df["work_status"].value_counts()
    ws_pick  = counts.get("未撿貨", 0)
    ws_pack  = counts.get("已撿待包", 0)
    ws_go    = counts.get("已包待出_GO", 0)
    ws_x     = counts.get("已包待出_X", 0)

    # Boxes
    box_col = next((c for c in df.columns if "box" in c.lower() or "carton" in c.lower()), None)
    boxes_go = int(df[df["work_status"] == "已包待出_GO"][box_col].sum()) if box_col else 0
    boxes_x  = int(df[df["work_status"] == "已包待出_X"][box_col].sum()) if box_col else 0

    # Today must-ship
    today_pick = len(df[(df["work_status"] == "未撿貨")    & (df["days_to_kpi"] <= 0)])
    today_pack = len(df[(df["work_status"] == "已撿待包")   & (df["days_to_kpi"] <= 0)])
    today_x    = len(df[(df["work_status"] == "已包待出_X") & (df["days_to_kpi"] <= 0)])
    today_go   = len(df[(df["work_status"] == "已包待出_GO")& (df["days_to_kpi"] <= 0)])
    today_total = today_pick + today_pack + today_x + today_go

    wd_label = WEEKDAY_MAP.get(today.weekday(), "")
    wd_cn    = {"W1": "一", "W2": "二", "W3": "三", "W4": "四", "W5": "五"}.get(wd_label, "")

    # ── Header ──
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"## OP&CS 作業排程")
    with c2:
        st.markdown(f"**{wd_label} 星期{wd_cn}** · {today}")

    st.caption(f"🕛 KPI 截止點 11:30 ｜ New CRSD 基準 ｜ 今天 = {wd_label}")
    st.divider()

    # ── Three status cards ──
    col1, col2, col3 = st.columns(3, gap="medium")

    with col1:
        st.markdown(
            f"""
            <div style="background:#EAF3DE;border-radius:10px;padding:16px;">
                <div style="font-size:12px;color:#3B6D11;font-weight:600;">① 未撿貨</div>
                <div style="font-size:11px;color:#5a7a3a;margin-bottom:8px;">Picking = A · Not yet processed</div>
                <div style="font-size:38px;font-weight:600;color:#3B6D11;line-height:1;">{ws_pick}</div>
                <div style="font-size:11px;color:#5a7a3a;margin-top:4px;">DNs 待備貨</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("")
        pick_df = df[df["work_status"] == "未撿貨"]
        for bucket, color in [("今日必出", "#E24B4A"), ("明天", "#EF9F27"), ("本週", "#3B6D11"), ("下週", "#888"), ("中長期", "#aaa")]:
            n = len(pick_df[pick_df["kpi_bucket"] == bucket])
            st.markdown(
                f'<span style="color:{color};font-weight:500;">{bucket}</span>'
                f'<span style="float:right;font-weight:600;">{n}</span>',
                unsafe_allow_html=True,
            )
        if st.button("詳細查看 未撿貨", key="db_pick"):
            go_to_detail("work_status", "未撿貨")

    with col2:
        st.markdown(
            f"""
            <div style="background:#FAEEDA;border-radius:10px;padding:16px;">
                <div style="font-size:12px;color:#854F0B;font-weight:600;">② 已撿待包</div>
                <div style="font-size:11px;color:#a06020;margin-bottom:8px;">Picking=C · Packing=Not Relevant</div>
                <div style="font-size:38px;font-weight:600;color:#854F0B;line-height:1;">{ws_pack}</div>
                <div style="font-size:11px;color:#a06020;margin-top:4px;">DNs 待包裝</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("")
        pack_df = df[df["work_status"] == "已撿待包"]
        for bucket, color in [("今日必出", "#E24B4A"), ("明天", "#EF9F27"), ("本週", "#3B6D11"), ("下週", "#888"), ("中長期", "#aaa")]:
            n = len(pack_df[pack_df["kpi_bucket"] == bucket])
            st.markdown(
                f'<span style="color:{color};font-weight:500;">{bucket}</span>'
                f'<span style="float:right;font-weight:600;">{n}</span>',
                unsafe_allow_html=True,
            )
        if st.button("詳細查看 已撿待包", key="db_pack"):
            go_to_detail("work_status", "已撿待包")

    with col3:
        boxes_total = boxes_go + boxes_x
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#E6F1FB 50%,#FCEBEB 50%);
                        border-radius:10px;padding:16px;">
                <div style="font-size:12px;font-weight:600;">③ 已包待出</div>
                <div style="font-size:11px;color:#555;margin-bottom:8px;">Picking=C · Packing=C · {boxes_total} boxes</div>
                <div style="font-size:38px;font-weight:600;line-height:1;">{ws_go + ws_x}</div>
                <div style="font-size:11px;color:#555;margin-top:4px;">DNs 待出貨</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("")
        c3a, c3b = st.columns(2)
        with c3a:
            st.markdown(
                f'<div style="background:#E6F1FB;border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="color:#042C53;font-size:11px;font-weight:600;">✅ GO 可出</div>'
                f'<div style="color:#185FA5;font-size:26px;font-weight:600;">{ws_go}</div>'
                f'<div style="color:#185FA5;font-size:10px;">{boxes_go} boxes</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("查看 GO", key="db_go"):
                go_to_detail("work_status", "已包待出_GO")
        with c3b:
            st.markdown(
                f'<div style="background:#FCEBEB;border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="color:#791F1F;font-size:11px;font-weight:600;">⚠ X 待授權</div>'
                f'<div style="color:#A32D2D;font-size:26px;font-weight:600;">{ws_x}</div>'
                f'<div style="color:#A32D2D;font-size:10px;">{boxes_x} boxes</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("查看 X", key="db_x"):
                go_to_detail("work_status", "已包待出_X")

    st.divider()

    # ── Today must-ship band ──
    st.markdown(
        f"""
        <div style="background:#FCEBEB;border:1px solid #F7C1C1;border-radius:10px;
                    padding:14px 20px;margin-bottom:16px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <span style="font-size:16px;">🔴</span>
                <span style="font-size:15px;font-weight:600;color:#A32D2D;">今天必出 — New CRSD ≤ 今日</span>
                <span style="font-size:26px;font-weight:600;color:#A32D2D;margin-left:auto;">{today_total}</span>
                <span style="font-size:12px;color:#A32D2D;">DNs</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tc1, tc2, tc3, tc4 = st.columns(4)
    for col, label, val, sub, action, bg, fg in [
        (tc1, "① 未撿貨",       today_pick, "逾期未備",   "立即備貨",   "#C0DD97", "#27500A"),
        (tc2, "② 已撿待包",     today_pack, "待包裝",      "立即包裝",   "#FAC775", "#633806"),
        (tc3, "③ 已包待出 X",   today_x,    "等授權",      "催授權",     "#F7C1C1", "#791F1F"),
        (tc4, "③ 已包待出 GO",  today_go,   "可立即出貨",  "立即出貨 ⚡", "#378ADD", "#fff"),
    ]:
        with col:
            st.markdown(
                f'<div style="background:#FFF5F5;border:0.5px solid #F7C1C1;border-radius:8px;'
                f'padding:12px;text-align:center;">'
                f'<div style="font-size:11px;color:#A32D2D;font-weight:500;margin-bottom:4px;">{label}</div>'
                f'<div style="font-size:30px;font-weight:600;line-height:1;">{val}</div>'
                f'<div style="font-size:10px;color:#888;margin:4px 0;">{sub}</div>'
                f'<div style="background:{bg};color:{fg};font-size:10px;padding:3px 8px;'
                f'border-radius:6px;display:inline-block;font-weight:500;">{action}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Future KPI planning ──
    st.markdown("#### 📅 未來 KPI 規劃")
    fc1, fc2, fc3, fc4 = st.columns(4)

    for col, label, days_range, color in [
        (fc1, "明天",    (1, 1),  "#854F0B"),
        (fc2, "本週",    (2, 4),  "#3B6D11"),
        (fc3, "下週",    (5, 11), "#185FA5"),
        (fc4, "中長期",  (12, 999), "#888"),
    ]:
        with col:
            mask = (df["days_to_kpi"] >= days_range[0]) & (df["days_to_kpi"] <= days_range[1])
            sub  = df[mask]
            n    = len(sub)
            breakdown = sub["work_status"].value_counts().to_dict()
            detail_str = "  ".join(
                f'<span style="color:{WORK_STATUS_COLORS.get(k,"#888")};font-size:10px;">{k} {v}</span>'
                for k, v in breakdown.items()
            )
            st.markdown(
                f'<div style="border:0.5px solid #ddd;border-radius:8px;padding:12px;">'
                f'<div style="font-size:12px;font-weight:500;color:{color};">{label}</div>'
                f'<div style="font-size:26px;font-weight:600;color:{color};line-height:1.1;">{n}</div>'
                f'<div style="margin-top:4px;">{detail_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Shipping Point breakdown ──
    st.markdown("#### 🏭 Shipping Point 分佈")
    sp_col = next((c for c in df.columns if "shipping point" in c.lower() or "ship. pt" in c.lower() or "Shipping Point" in c), None)

    if sp_col:
        sp_pivot = df.groupby([sp_col, "work_status"]).size().unstack(fill_value=0)
        st.dataframe(sp_pivot, use_container_width=True)


# ══════════════════════════════════════════════
# PAGE 2 — RAW DATA LIST
# ══════════════════════════════════════════════
elif page == "📋 Raw Data":

    st.markdown("## 📋 Raw Data — 完整訂單列表")

    sp_col  = next((c for c in df.columns if "shipping point" in c.lower() or "Shipping Point" in c), None)
    dn_col  = next((c for c in df.columns if "delivery" in c.lower() and "note" not in c.lower() and len(c) < 15), None)
    if dn_col is None:
        dn_col = next((c for c in df.columns if c.strip().upper() in ["DN", "DELIVERY NOTE", "DELIVERY"]), None)

    # ── Filters ──
    with st.expander("🔍 篩選條件", expanded=True):
        fc1, fc2, fc3 = st.columns(3)

        with fc1:
            ws_options = ["全部"] + sorted(df["work_status"].dropna().unique().tolist())
            sel_ws = st.multiselect("作業狀態", options=ws_options[1:], default=[])

            p_options = ["P1", "P2", "P3", "P4"]
            sel_p = st.multiselect("優先級", options=p_options, default=[])

        with fc2:
            if sp_col:
                sp_options = sorted(df[sp_col].dropna().unique().tolist())
                sel_sp = st.multiselect("Shipping Point", options=sp_options, default=[])
            else:
                sel_sp = []

            bucket_opts = ["今日必出", "明天", "本週", "下週", "中長期"]
            sel_bucket = st.multiselect("KPI 區間", options=bucket_opts, default=[])

        with fc3:
            cust_options = sorted(df["customer_display"].dropna().unique().tolist())
            sel_cust = st.multiselect("客戶", options=cust_options, default=[])

            sel_dispatch = st.checkbox("僅顯示今日 dispatch", value=False)
            sel_x_only   = st.checkbox("僅顯示 Special Processing = X", value=False)

        cr1, cr2 = st.columns(2)
        with cr1:
            min_crsd = df["kpi_date"].dropna().min()
            max_crsd = df["kpi_date"].dropna().max()
            date_from = st.date_input("KPI 日期 From", value=min_crsd)
        with cr2:
            date_to = st.date_input("KPI 日期 To", value=max_crsd)

    # ── Apply filters ──
    mask = pd.Series([True] * len(df), index=df.index)

    if sel_ws:
        mask &= df["work_status"].isin(sel_ws)
    if sel_p:
        mask &= df["priority"].isin(sel_p)
    if sel_sp and sp_col:
        mask &= df[sp_col].isin(sel_sp)
    if sel_bucket:
        mask &= df["kpi_bucket"].isin(sel_bucket)
    if sel_cust:
        mask &= df["customer_display"].isin(sel_cust)
    if sel_dispatch:
        mask &= df["dispatch_today"]
    if sel_x_only:
        mask &= df.get("Special Processing", pd.Series([""] * len(df), index=df.index)).str.strip() == "X"
    mask &= df["kpi_date"].apply(lambda d: date_from <= d <= date_to if pd.notna(d) else False)

    filtered = df[mask].copy()
    st.caption(f"顯示 {len(filtered)} / {len(df)} 筆")

    # ── Display columns ──
    display_cols = [c for c in [
        sp_col, dn_col, customer_col,
        "New CRSD", "kpi_date", "days_to_kpi",
        "work_status", "priority", "kpi_bucket",
        "dispatch_rule_display", "dispatch_today",
        "Picking Status", "Packing Status", "Special Processing",
    ] if c and c in filtered.columns]

    def color_ws(val):
        color = WORK_STATUS_COLORS.get(val, "")
        if color:
            return f"color: {color}; font-weight: bold"
        return ""

    def color_p(val):
        color = PRIORITY_COLORS.get(val, "")
        if color:
            return f"color: {color}; font-weight: bold"
        return ""

    styled = (
        filtered[display_cols]
        .style
        .map(color_ws, subset=["work_status"])
        .map(color_p,  subset=["priority"])
    )

    st.dataframe(styled, use_container_width=True, height=500)

    # ── Export ──
    csv = filtered[display_cols].to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "⬇ 下載篩選結果 CSV",
        data=csv.encode("utf-8-sig"),
        file_name=f"opcs_raw_{date.today()}.csv",
        mime="text/csv",
    )


# ══════════════════════════════════════════════
# PAGE 3 — DETAIL VIEW (click-through)
# ══════════════════════════════════════════════
elif page == "🔍 Detail View":

    st.markdown("## 🔍 Detail View")

    # Pre-fill from dashboard click-through
    detail_filter_key = st.session_state.get("detail_filter_key", None)
    detail_filter_val = st.session_state.get("detail_filter_val", None)

    sp_col = next((c for c in df.columns if "Shipping Point" in c), None)

    # ── Filter controls ──
    c1, c2, c3 = st.columns(3)
    with c1:
        ws_opts = sorted(df["work_status"].dropna().unique().tolist())
        default_ws = [detail_filter_val] if detail_filter_key == "work_status" and detail_filter_val in ws_opts else []
        sel_ws_d = st.multiselect("作業狀態", options=ws_opts, default=default_ws, key="d_ws")
    with c2:
        cust_opts = sorted(df["customer_display"].dropna().unique().tolist())
        default_cust = [detail_filter_val] if detail_filter_key == "customer" and detail_filter_val in cust_opts else []
        sel_cust_d = st.multiselect("客戶", options=cust_opts, default=default_cust, key="d_cust")
    with c3:
        if sp_col:
            sp_opts = sorted(df[sp_col].dropna().unique().tolist())
            default_sp = [detail_filter_val] if detail_filter_key == "sp" and detail_filter_val in sp_opts else []
            sel_sp_d = st.multiselect("Shipping Point", options=sp_opts, default=default_sp, key="d_sp")
        else:
            sel_sp_d = []

    # ── Apply ──
    mask_d = pd.Series([True] * len(df), index=df.index)
    if sel_ws_d:
        mask_d &= df["work_status"].isin(sel_ws_d)
    if sel_cust_d:
        mask_d &= df["customer_display"].isin(sel_cust_d)
    if sel_sp_d and sp_col:
        mask_d &= df[sp_col].isin(sel_sp_d)

    sub_d = df[mask_d].copy()

    if detail_filter_val:
        st.info(f"Dashboard 來源：**{detail_filter_val}** → {len(sub_d)} 筆")

    # ── Summary cards ──
    d1, d2, d3, d4 = st.columns(4)
    for col, ws, lbl in [
        (d1, "未撿貨",      "未撿貨"),
        (d2, "已撿待包",    "已撿待包"),
        (d3, "已包待出_GO", "已包待出 GO"),
        (d4, "已包待出_X",  "已包待出 X"),
    ]:
        with col:
            n = len(sub_d[sub_d["work_status"] == ws])
            color = WORK_STATUS_COLORS.get(ws, "#888")
            st.markdown(
                f'<div style="border-left:4px solid {color};padding:8px 12px;background:#fafafa;'
                f'border-radius:4px;">'
                f'<div style="font-size:11px;color:{color};font-weight:600;">{lbl}</div>'
                f'<div style="font-size:24px;font-weight:600;">{n}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    # ── Full detail table ──
    detail_cols = [c for c in [
        sp_col,
        next((c for c in df.columns if "delivery" in c.lower() and len(c) < 15), None),
        customer_col,
        "New CRSD", "kpi_date", "days_to_kpi", "kpi_bucket",
        "work_status", "priority",
        "dispatch_rule_display", "dispatch_today",
        "Picking Status", "Packing Status", "Special Processing",
        next((c for c in df.columns if "box" in c.lower() or "件數" in c), None),
        next((c for c in df.columns if "weight" in c.lower() or "wt" in c.lower()), None),
    ] if c and c in sub_d.columns]

    # deduplicate while preserving order
    seen = set()
    detail_cols = [c for c in detail_cols if not (c in seen or seen.add(c))]

    def highlight_rows(row):
        ws = row.get("work_status", "")
        color_map = {
            "未撿貨":       "#EAF3DE",
            "已撿待包":     "#FAEEDA",
            "已包待出_GO":  "#E6F1FB",
            "已包待出_X":   "#FCEBEB",
        }
        bg = color_map.get(ws, "")
        return [f"background-color: {bg}" if bg else "" for _ in row]

    st.dataframe(
        sub_d[detail_cols].style.apply(highlight_rows, axis=1),
        use_container_width=True,
        height=520,
    )

    # Export
    csv_d = sub_d[detail_cols].to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "⬇ 下載此列表 CSV",
        data=csv_d.encode("utf-8-sig"),
        file_name=f"detail_{detail_filter_val or 'all'}_{date.today()}.csv",
        mime="text/csv",
    )

    # Clear session nav
    if st.button("← 返回 Dashboard"):
        st.session_state.pop("detail_filter_key", None)
        st.session_state.pop("detail_filter_val", None)
        st.session_state["page_index"] = 0
        st.rerun()


# ══════════════════════════════════════════════
# PAGE 4 — CS PRINT LIST
# ══════════════════════════════════════════════
elif page == "🖨 CS Print List":

    st.markdown("## 🖨 CS 出貨清單 — 依 Dispatch 規則")

    today     = date.today()
    today_w   = WEEKDAY_MAP.get(today.weekday(), "")
    wd_cn     = {"W1": "一", "W2": "二", "W3": "三", "W4": "四", "W5": "五"}.get(today_w, "")

    def _fc(df, *kws):
        for kw in kws:
            for c in df.columns:
                if kw.lower() in c.lower():
                    return c
        return None

    sp_col       = _fc(df, "shipping point", "ship. pt")
    dn_col       = _fc(df, "delivery")
    etd_col      = _fc(df, "etd")
    ship_to_col  = _fc(df, "ship to customer", "ship-to customer", "ship to name")
    box_col      = _fc(df, "件數", "box", "carton", "qty")
    route_col    = _fc(df, "route")
    dst_col      = _fc(df, "dst", "destination", "ship to country", "ship-to country")
    pay_col      = _fc(df, "payment code", "incoterms", "inco term")
    acct_col     = _fc(df, "delivery account", "account")

    # ── Controls ──
    ct1, ct2 = st.columns([2, 1])
    with ct1:
        show_mode = st.radio(
            "顯示模式",
            ["今日 Dispatch 可出", "全部 GO 訂單", "今日 KPI 全部"],
            horizontal=True,
        )
    with ct2:
        show_x_warning = st.checkbox("包含 X 待授權（標注警示）", value=True)

    # ── Filter based on mode ──
    if show_mode == "今日 Dispatch 可出":
        mask_p = df["dispatch_today"] & (df["work_status"] == "已包待出_GO")
        title  = f"今日 ({today_w} 星期{wd_cn}) Dispatch — GO 可出"
    elif show_mode == "全部 GO 訂單":
        mask_p = df["work_status"] == "已包待出_GO"
        title  = "全部 GO 待出訂單"
    else:  # 今日 KPI 全部
        mask_p = df["days_to_kpi"] <= 0
        title  = f"今日 KPI 到期全部（{today}）"

    if show_x_warning:
        # also include X orders that are today
        mask_x = (df["work_status"] == "已包待出_X") & (df["days_to_kpi"] <= 0)
        print_df = df[mask_p | mask_x].copy()
    else:
        print_df = df[mask_p].copy()

    # ── Sort: priority > days_to_kpi > customer ──
    p_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    print_df["_p_order"] = print_df["priority"].map(p_order).fillna(9)
    print_df = print_df.sort_values(["_p_order", "days_to_kpi", "customer_display"])

    st.markdown(f"### {title}")
    st.caption(f"共 {len(print_df)} 筆 ｜ 產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── CS Print columns — match header: Delivery / SP / ETD / DN Created / New CRSD /
    #    Ship to Customer / 件數 / ROUTE / DST / Payment Code / Delivery Account ──
    # Also inject dispatch_rule_display (hides "Everyday") and work_status / priority
    candidate_cols = [
        dn_col, sp_col, etd_col, "DN Created Date/Time", "New CRSD",
        ship_to_col, "customer_display",
        box_col, route_col, dst_col, pay_col, acct_col,
        "work_status", "priority", "dispatch_rule_display", "Special Processing",
    ]
    seen = set()
    print_cols = [
        c for c in candidate_cols
        if c and c in print_df.columns and not (c in seen or seen.add(c))
    ]

    # ── Styled table ──
    def style_print(row):
        ws = row.get("work_status", "")
        sp = str(row.get("Special Processing", "")).strip()
        if ws == "已包待出_X":
            return ["background-color: #FCEBEB; color: #A32D2D"] * len(row)
        if ws == "已包待出_GO":
            return ["background-color: #E6F1FB"] * len(row)
        days = row.get("days_to_kpi", 999)
        if days <= 0:
            return ["background-color: #FFF5F5"] * len(row)
        return [""] * len(row)

    styled_p = print_df[print_cols].style.apply(style_print, axis=1)
    st.dataframe(styled_p, use_container_width=True, height=480)

    # ── Summary by customer ──
    st.markdown("#### 客戶彙總")
    if box_col:
        summary = (
            print_df.groupby("customer_display")
            .agg(
                DNs=("customer_display", "count"),
                Boxes=(box_col, "sum"),
                Dispatch=("dispatch_rule", lambda x: x.mode()[0] if not x.empty else ""),
                Status=("work_status", lambda x: ", ".join(x.unique()[:2])),
                Min_CRSD=("New CRSD", "min"),
            )
            .sort_values("DNs", ascending=False)
            .reset_index()
        )
    else:
        summary = (
            print_df.groupby("customer_display")
            .agg(
                DNs=("customer_display", "count"),
                Dispatch=("dispatch_rule", lambda x: x.mode()[0] if not x.empty else ""),
                Status=("work_status", lambda x: ", ".join(x.unique()[:2])),
                Min_CRSD=("New CRSD", "min"),
            )
            .sort_values("DNs", ascending=False)
            .reset_index()
        )
    st.dataframe(summary, use_container_width=True)

    # ── Download ──
    st.markdown("---")
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv_p = print_df[print_cols].to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇ 下載出貨清單 CSV",
            data=csv_p.encode("utf-8-sig"),
            file_name=f"cs_print_{today}.csv",
            mime="text/csv",
        )
    with col_dl2:
        st.info("💡 按 Ctrl+P (Windows) / ⌘+P (Mac) 可列印目前畫面")
