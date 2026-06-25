#!/usr/bin/env python3
"""SKYWORKS Operations Dashboard - 3 Pages: Dashboard | Detail View | CS Print List"""

import io, base64
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime

# ── Logo ───────────────────────────────────────────────────────────────────────
DIMERCO_LOGO_HTML = (
    '<img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDQwIiBoZWlnaHQ9IjU4IiB2aWV3Qm94PSIwIDAgNDQwIDU4IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxkZWZzPjxzdHlsZT4ubHR7Zm9udC1mYW1pbHk6IkFyaWFsIEJsYWNrIixJbXBhY3Qsc2Fucy1zZXJpZjtmb250LXN0eWxlOml0YWxpYztmb250LXdlaWdodDo5MDA7Zm9udC1zaXplOjI2cHg7ZmlsbDojMDA5RUUzO2xldHRlci1zcGFjaW5nOi0wLjVweDt9PC9zdHlsZT48L2RlZnM+PHRleHQgY2xhc3M9Imx0IiB4PSIyIiB5PSIzMCI+RElNRVJDTzwvdGV4dD48cGF0aCBkPSJNIDc2IDM0IEMgMTAwIDMxLDEyMCAyOSwxNDAgMjYiIHN0cm9rZT0iIzAwOUVFMyIgc3Ryb2tlLXdpZHRoPSIzLjIiIGZpbGw9Im5vbmUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPjxwYXRoIGQ9Ik0gNzYgNDAgQyAxMDAgMzcsMTIwIDM1LDE0MCAzMiIgc3Ryb2tlPSIjRjdBMTFBIiBzdHJva2Utd2lkdGg9IjQuMiIgZmlsbD0ibm9uZSIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIi8+PGxpbmUgeDE9IjE1MiIgeTE9IjYiIHgyPSIxNTIiIHkyPSI1MiIgc3Ryb2tlPSIjQkJCQkJCIiBzdHJva2Utd2lkdGg9IjEiLz48dGV4dCB4PSIxNjMiIHk9IjMwIiBmb250LWZhbWlseT0iTWljcm9zb2Z0IEpoZW5nSGVpLFBpbmdGYW5nIFRDLHNhbnMtc2VyaWYiIGZvbnQtd2VpZ2h0PSI3MDAiIGZvbnQtc2l6ZT0iMjAiIGZpbGw9IiMwMDMwODciPuWkmuWFg+Wci+mam+eJqea1geiCoeS7veaciemZkOWFrOWPuDwvdGV4dD48dGV4dCB4PSIxNjMiIHk9IjQ4IiBmb250LWZhbWlseT0iQXJpYWwsc2Fucy1zZXJpZiIgZm9udC13ZWlnaHQ9IjQwMCIgZm9udC1zaXplPSIxMC41IiBmaWxsPSIjNTU1NTU1IiBsZXR0ZXItc3BhY2luZz0iMC4zIj5ESVZFUlNJRklFRCBJTlRFUk5BVElPTkFMIExPR0lTVElDUyBDTy4sIExURC48L3RleHQ+PC9zdmc+"'
    ' style="width:260px;margin-bottom:4px;">'
)

st.set_page_config(
    page_title="SKYWORKS 作業排程",
    page_icon="\U0001f4e6",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────────────────────
CUTOFF_HOUR, CUTOFF_MINUTE = 11, 30

RULES_RAW = {
    "EDOM TECHNOLOGY":        {"HK": "W2/W5", "TW": "W4"},
    "BANG TAI":               {"HK": "W2/W5"},
    "WT MICROELECTRONICS":    {"HK": "Everyday", "TW": "W2/W4"},
    "ARROW ASIA PAC":         {"HK": "W2/W4"},
    "HMD KOREA":              {"KR": "W2"},
    "ARROW CENTRAL EUROPE":   {"NETHERLANDS": "W4", "NL": "W4"},
    "ARROW ELECTRONICS ASIA": {"MALAYSIA": "W2/W4", "MY": "W2/W4"},
    "UNIVERSAL SCIENTIFIC":   {"TW": "W3", "CN": "W3"},
    "MOUSER":                 {"*": "Everyday"},
    "DIGIKEY":                {"*": "Everyday"},
    "AVNET":                  {"*": "Everyday"},
    "ARROW COMPONENTS MX":    {"MX": "Everyday"},
    "FORTUNE TECH":           {"*": "W5"},
    "SCHENKER":               {"SG": "W2/W4"},
    "PANGAEA":                {"HK": "W2/W4"},
    "FEDEX":                  {"*": "FEDEX"},
    "DHL":                    {"*": "DHL"},
}

WEEKDAY_MAP = {0: "W1", 1: "W2", 2: "W3", 3: "W4", 4: "W5"}

WS_COLORS = {
    "未揀貨":      "#3B6D11",
    "已揀待包":    "#854F0B",
    "已包待出_GO": "#185FA5",
    "已包待出_X":  "#A32D2D",
}

P_COLORS = {
    "P1": "#A32D2D", "P2": "#E24B4A",
    "P3": "#C7500A", "P4": "#EF9F27",
    "P5": "#185FA5", "P6": "#5588BB",
    "P7": "#AAAAAA",
}

BKT_ORDER = ["今日必出", "明天", "本週",
             "下週", "中長期"]

_CACHE_VER = "v4"  # increment this to bust st.cache_data when columns change

# ── Display column rename map ──────────────────────────────────────────────
RENAME_MAP = {
    "customer_display":              "Shipping Incoterms and Customer",
    "kpi_date":                      "KPI Date",
    "effective_ship_date":           "Shipping Date",
    "days_to_kpi":                   "Days To KPI",
    "days_to_effective":             "Days To Ship",
    "work_status":                   "Work Status",
    "kpi_bucket":                    "KPI Type",
    "dispatch_rule_display":         "Consult Rule",
    "cip_direct":                    "CIP Direct",
    "dispatch_today":                "Dispatch Today",
    "sp_display":                    "SP Display",
    "exc_flag":                      "Exception",
    "DN Created Date/Time(TW time)": "DN Created (TW Time)",
}

def display_rename(col):
    """Rename for display: RENAME_MAP overrides, else title-case + strip underscores."""
    if col in RENAME_MAP:
        return RENAME_MAP[col]
    if "_" in col:
        return col.replace("_", " ").title()
    return col

# ── Helpers ────────────────────────────────────────────────────────────────────
def find_col(df, *kws):
    for kw in kws:
        for c in df.columns:
            if kw.lower() in c.lower():
                return c
    return None

def next_workday(d):
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt

def rule_weekdays(rule):
    r = str(rule).strip()
    if not r or r in ("", "Everyday", "FEDEX", "DHL", "T3EX"):
        return None
    days = []
    for t in r.split("/"):
        t = t.strip()
        if t.startswith("W") and t[1:].isdigit():
            days.append(int(t[1:]) - 1)
    return days or None

def next_dispatch_day(base, rule):
    allowed = rule_weekdays(rule)
    if allowed is None:
        return base
    for offset in range(7):
        c = base + timedelta(days=offset)
        if c.weekday() in allowed:
            return c
    return base

# ── Data processing ────────────────────────────────────────────────────────────
def process_data(raw_df):
    df = raw_df.copy()
    today   = date.today()
    today_w = WEEKDAY_MAP.get(today.weekday(), "")

    customer_col     = find_col(df, "sold-to name", "sold to name", "customer name", "customer")
    if not customer_col or customer_col not in df.columns:
        customer_col = find_col(df, "sold") or df.columns[0]
    ship_country_col = find_col(df, "ship to country", "ship-to country", "shipto country")
    incoterms_col    = find_col(df, "incoterms", "inco term", "payment code", "terms")

    # step 1 – dates
    df["New CRSD"] = pd.to_datetime(df["New CRSD"], errors="coerce").dt.date
    df["DN Created Date/Time"] = pd.to_datetime(df["DN Created Date/Time"], errors="coerce")
    # Convert source timezone UTC-7 → Taiwan UTC+8 (+15 hours)
    TW_COL = "DN Created Date/Time(TW time)"
    df[TW_COL] = df["DN Created Date/Time"] + pd.Timedelta(hours=15)

    # step 2 – work status
    def _ws(row):
        pick = str(row.get("Picking Status", ""))
        pack = str(row.get("Packing Status", ""))
        sp   = str(row.get("Special Processing", "")).strip()
        if "A - Not yet" in pick:
            return "未揀貨"
        if "C - Completely" in pick and "Not Relevant" in pack:
            return "已揀待包"
        if "C - Completely" in pick and "C - Completely" in pack:
            return "已包待出_X" if sp == "X" else "已包待出_GO"
        return "其他"
    df["work_status"] = df.apply(_ws, axis=1)

    # step 2b – CIP override: non-TW CIP orders skip dispatch rule, ship direct on CRSD
    df["cip_override"] = False
    if incoterms_col and incoterms_col in df.columns and ship_country_col and ship_country_col in df.columns:
        df["cip_override"] = (
            df[incoterms_col].astype(str).str.strip().str.upper() == "CIP"
        ) & (
            df[ship_country_col].astype(str).str.strip().str.upper() != "TW"
        )

    # step 3 – dispatch rule
    def _rule(customer, ship_country):
        cu = str(customer).upper()
        cy = str(ship_country).upper().strip()
        if "FEDEX" in cu: return "FEDEX"
        if "DHL"   in cu: return "DHL"
        for key, dest_rules in RULES_RAW.items():
            if key.upper() in cu:
                for dk, rule in dest_rules.items():
                    if dk == "*": return rule
                    if dk.upper() in cy or cy in dk.upper(): return rule
        return ""
    df["dispatch_rule"] = df.apply(
        lambda r: _rule(r.get(customer_col, ""),
                        r.get(ship_country_col, "") if ship_country_col else ""), axis=1)

    def _dispatch_today(row):
        if row["cip_override"]: return True   # CIP non-TW always dispatchable
        rule = row["dispatch_rule"]
        if not rule: return False
        if rule in ("Everyday", "FEDEX", "DHL", "T3EX"): return True
        return today_w in [x.strip() for x in rule.split("/")]
    df["dispatch_today"] = df.apply(_dispatch_today, axis=1)
    df["today_w"] = today_w

    # step 4 – kpi_date (11:30 cutoff, using TW time for comparison)
    def _kpi_date(row):
        crsd  = row["New CRSD"]
        dn_tw = row[TW_COL]   # Taiwan UTC+8 time
        if pd.isna(crsd): return crsd
        if (row["work_status"] == "已包待出_GO"
                and crsd == today
                and row["dispatch_today"]
                and pd.notna(dn_tw)
                and (dn_tw.hour, dn_tw.minute) >= (CUTOFF_HOUR, CUTOFF_MINUTE)):
            return next_workday(today)
        return crsd
    df["kpi_date"] = df.apply(_kpi_date, axis=1)
    df["days_to_kpi"] = df["kpi_date"].apply(
        lambda d: (d - today).days if pd.notna(d) else 999)

    # step 5 – effective ship date
    def _eff(row):
        kd = row["kpi_date"]
        if pd.isna(kd): return kd
        base = max(kd, today)
        if row["cip_override"]:
            return base  # CIP non-TW: ship direct on CRSD, no dispatch-day constraint
        return next_dispatch_day(base, row["dispatch_rule"])
    df["effective_ship_date"] = df.apply(_eff, axis=1)
    df["days_to_effective"] = df["effective_ship_date"].apply(
        lambda d: (d - today).days if pd.notna(d) else 999)

    # step 6 – priority
    def _priority(row):
        days = row["days_to_effective"]
        ws   = row["work_status"]
        if ws in ("已包待出_GO", "已包待出_X"):
            return "P1" if days<=2 else ("P3" if days<=5 else ("P5" if days<=10 else "P7"))
        not_picked = (ws == "未揀貨")
        if days <= 2:  return "P1" if not_picked else "P2"
        if days <= 5:  return "P3" if not_picked else "P4"
        if days <= 10: return "P5" if not_picked else "P6"
        return "P7"
    df["priority"] = df.apply(_priority, axis=1)

    # step 7 – kpi_bucket (date-based only, no SP=X override)
    def _bucket(row):
        days = row["days_to_effective"]
        if days <= 0:  return "今日必出"
        if days == 1:  return "明天"
        if days <= 4:  return "本週"
        if days <= 11: return "下週"
        return "中長期"
    df["kpi_bucket"] = df.apply(_bucket, axis=1)

    # step 8 – sp_display  (X -> "待核准出貨")
    df["sp_display"] = df["Special Processing"].apply(
        lambda v: "待核准出貨" if str(v).strip() == "X" else str(v).strip()
    )

    # step 9 – customer_display / dispatch_rule_display
    if incoterms_col and incoterms_col in df.columns:
        df["customer_display"] = (
            df[incoterms_col].astype(str).str.strip().str.upper()
            + "-"
            + df[customer_col].astype(str).str.strip().str.upper()
        ).str.replace(r"^NAN-", "", regex=True)
    else:
        df["customer_display"] = df[customer_col].astype(str).str.strip()

    df["dispatch_rule_display"] = df["dispatch_rule"].apply(
        lambda r: "" if r == "Everyday" else r)

    # CIP direct-ship display tag
    df["cip_direct"] = df["cip_override"].map({True: "CIP直出", False: ""})

    return df, customer_col

# ── Navigation helpers ─────────────────────────────────────────────────────────
def go_to_detail(filter_key=None, filter_val=None):
    st.session_state["detail_filter_key"] = filter_key
    st.session_state["detail_filter_val"] = filter_val
    st.session_state["_nav_idx"] = 1  # Detail View
    st.rerun()

def go_to_dashboard():
    st.session_state["detail_filter_key"] = None
    st.session_state["detail_filter_val"] = None
    st.session_state["_nav_idx"] = 0  # Dashboard
    st.rerun()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(DIMERCO_LOGO_HTML, unsafe_allow_html=True)
    st.markdown("### SKYWORKS 作業排程")
    st.markdown("---")

    _PAGE_NAMES = ["\U0001f4ca Dashboard", "\U0001f50d Detail View", "\U0001f5a8 CS Print List"]
    _nav_idx = st.session_state.get("_nav_idx", 0)
    page = st.radio(
        "頁面導航",
        _PAGE_NAMES,
        index=_nav_idx,
    )
    # keep _nav_idx in sync when user clicks manually
    st.session_state["_nav_idx"] = _PAGE_NAMES.index(page)

    st.markdown("---")
    st.markdown("### 上傳資料")
    f1 = st.file_uploader("Open DN — CHBT, AK3T",       type=["xlsx"], key="f1")
    f2 = st.file_uploader("Open DN — ASEM, A3TA, ASEA", type=["xlsx"], key="f2")

    st.markdown("---")
    _td = date.today()
    _wl = WEEKDAY_MAP.get(_td.weekday(), "")
    _wc = {"W1":"一","W2":"二","W3":"三","W4":"四","W5":"五"}.get(_wl,"")
    st.markdown(f"**今天：** {_td}  \n**{_wl} (星期{_wc})**")
    st.caption("KPI 截止點：11:30 (New CRSD 基準)")

# ── Load data ──────────────────────────────────────────────────────────────────
if not f1 or not f2:
    st.info("請在左側上傳兩份 Open Delivery Notes Excel 檔案")
    st.stop()

@st.cache_data(show_spinner="載入資料中…")
def _load(b1, b2, cache_ver=_CACHE_VER):
    dfs = []
    for b in [b1, b2]:
        dfs.append(pd.read_excel(io.BytesIO(b), sheet_name="Open Delivery Notes", header=1))
    raw = pd.concat(dfs, ignore_index=True)
    return process_data(raw)  # process inside cache — only runs when files or version change

df, customer_col = _load(f1.getvalue(), f2.getvalue())

# ── Shared column refs ─────────────────────────────────────────────────────────
sp_col    = find_col(df, "shipping point", "ship. pt")
dn_col    = find_col(df, "delivery")
etd_col   = find_col(df, "etd", "sched. gi", "sched gi", "gi date", "planned gi", "goods issue")
# Debug: show resolved column names in sidebar (remove after confirming)
with st.sidebar.expander("欄位對應（Debug）", expanded=False):
    st.caption(f"ETD col: `{etd_col}`")
    st.caption(f"TW time col in df: {'DN Created Date/Time(TW time)' in df.columns}")
    st.caption(f"All columns: {list(df.columns[:8])}")
box_col   = find_col(df, "件數", "box", "carton", "qty")
route_col = find_col(df, "route")
dst_col   = find_col(df, "ship to country", "ship-to country", "dst")
acct_col  = find_col(df, "delivery account", "account")

# =============================================================================
# PAGE: DASHBOARD
# =============================================================================
if page == "\U0001f4ca Dashboard":
    today = date.today()
    wl = WEEKDAY_MAP.get(today.weekday(), "")
    wc = {"W1":"一","W2":"二","W3":"三","W4":"四","W5":"五"}.get(wl,"")

    counts  = df["work_status"].value_counts()
    ws_pick = counts.get("未揀貨", 0)
    ws_pack = counts.get("已揀待包", 0)
    ws_go   = counts.get("已包待出_GO", 0)
    ws_x    = counts.get("已包待出_X", 0)
    boxes_go = int(df[df["work_status"]=="已包待出_GO"][box_col].sum()) if box_col else 0
    boxes_x  = int(df[df["work_status"]=="已包待出_X"][box_col].sum()) if box_col else 0

    hc1, hc2 = st.columns([3,1])
    with hc1: st.markdown("## SKYWORKS 作業排程")
    with hc2: st.markdown(f"**{wl} 星期{wc}** · {today}")
    st.caption(f"KPI 截止點 11:30 | New CRSD 基準 | 今天 = {wl}")
    st.divider()

    # ── Status cards ──
    col1, col2, col3 = st.columns(3, gap="medium")

    BKT_LIST = [
        ("今日必出","#E24B4A"),
        ("明天","#EF9F27"),
        ("本週","#3B6D11"),
        ("下週","#888"),
        ("中長期","#aaa"),
    ]

    with col1:
        st.markdown(
            f'<div style="background:#EAF3DE;border-radius:10px;padding:16px;">'
            f'<div style="font-size:12px;color:#3B6D11;font-weight:600;">① 未揀貨</div>'
            f'<div style="font-size:11px;color:#5a7a3a;margin-bottom:8px;">Picking=A Not yet processed</div>'
            f'<div style="font-size:38px;font-weight:600;color:#3B6D11;line-height:1;">{ws_pick}</div>'
            f'<div style="font-size:11px;color:#5a7a3a;margin-top:4px;">DNs 待備貨</div></div>',
            unsafe_allow_html=True)
        st.markdown("")
        pick_df = df[df["work_status"]=="未揀貨"]
        for bkt, clr in BKT_LIST:
            n = len(pick_df[pick_df["kpi_bucket"]==bkt])
            st.markdown(
                f'<span style="color:{clr};font-weight:500;">{bkt}</span>'
                f'<span style="float:right;font-weight:600;">{n}</span>',
                unsafe_allow_html=True)
        if st.button("詳細查看 未揀貨", key="db_pick"):
            go_to_detail("work_status", "未揀貨")

    with col2:
        st.markdown(
            f'<div style="background:#FAEEDA;border-radius:10px;padding:16px;">'
            f'<div style="font-size:12px;color:#854F0B;font-weight:600;">② 已揀待包</div>'
            f'<div style="font-size:11px;color:#a06020;margin-bottom:8px;">Picking=C Packing=Not Relevant</div>'
            f'<div style="font-size:38px;font-weight:600;color:#854F0B;line-height:1;">{ws_pack}</div>'
            f'<div style="font-size:11px;color:#a06020;margin-top:4px;">DNs 待包裝</div></div>',
            unsafe_allow_html=True)
        st.markdown("")
        pack_df = df[df["work_status"]=="已揀待包"]
        for bkt, clr in BKT_LIST:
            n = len(pack_df[pack_df["kpi_bucket"]==bkt])
            st.markdown(
                f'<span style="color:{clr};font-weight:500;">{bkt}</span>'
                f'<span style="float:right;font-weight:600;">{n}</span>',
                unsafe_allow_html=True)
        if st.button("詳細查看 已揀待包", key="db_pack"):
            go_to_detail("work_status", "已揀待包")

    with col3:
        boxes_total = boxes_go + boxes_x
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#E6F1FB 50%,#FCEBEB 50%);'
            f'border-radius:10px;padding:16px;">'
            f'<div style="font-size:12px;font-weight:600;">③ 已包待出</div>'
            f'<div style="font-size:11px;color:#555;margin-bottom:8px;">Picking=C Packing=C {boxes_total} boxes</div>'
            f'<div style="font-size:38px;font-weight:600;line-height:1;">{ws_go+ws_x}</div>'
            f'<div style="font-size:11px;color:#555;margin-top:4px;">DNs 待出貨</div></div>',
            unsafe_allow_html=True)
        st.markdown("")
        c3a, c3b = st.columns(2)
        with c3a:
            st.markdown(
                f'<div style="background:#E6F1FB;border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="color:#042C53;font-size:11px;font-weight:600;">GO 可出</div>'
                f'<div style="color:#185FA5;font-size:26px;font-weight:600;">{ws_go}</div>'
                f'<div style="color:#185FA5;font-size:10px;">{boxes_go} boxes</div></div>',
                unsafe_allow_html=True)
            if st.button("查看 GO", key="db_go"):
                go_to_detail("work_status", "已包待出_GO")
        with c3b:
            st.markdown(
                f'<div style="background:#FCEBEB;border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="color:#791F1F;font-size:11px;font-weight:600;">X 待授權</div>'
                f'<div style="color:#A32D2D;font-size:26px;font-weight:600;">{ws_x}</div>'
                f'<div style="color:#A32D2D;font-size:10px;">{boxes_x} boxes</div></div>',
                unsafe_allow_html=True)
            if st.button("查看 X", key="db_x"):
                go_to_detail("work_status", "已包待出_X")

    st.divider()

    # ── Today must-ship ──
    t_pick = len(df[(df["work_status"]=="未揀貨")     & (df["days_to_effective"]<=0)])
    t_pack = len(df[(df["work_status"]=="已揀待包")  & (df["days_to_effective"]<=0)])
    t_x    = len(df[(df["work_status"]=="已包待出_X") & (df["days_to_effective"]<=0)])
    t_go   = len(df[(df["work_status"]=="已包待出_GO")& (df["days_to_effective"]<=0)])
    t_tot  = t_pick + t_pack + t_x + t_go

    st.markdown(
        f'<div style="background:#FCEBEB;border:1px solid #F7C1C1;border-radius:10px;'
        f'padding:14px 20px;margin-bottom:16px;">'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<span style="font-size:16px;">\U0001f534</span>'
        f'<span style="font-size:15px;font-weight:600;color:#A32D2D;">🔴 今天必出 — 按出貨排程統計</span>'
        f'<span style="font-size:26px;font-weight:600;color:#A32D2D;margin-left:auto;">{t_tot}</span>'
        f'<span style="font-size:12px;color:#A32D2D;">DNs</span>'
        f'</div></div>',
        unsafe_allow_html=True)

    tc1, tc2, tc3, tc4 = st.columns(4)
    for col, lbl, val, ws_key, sub, act, bg, fg in [
        (tc1, "未揀貨",      t_pick, "未揀貨",      "逾期未備",   "立即備貨",   "#C0DD97","#27500A"),
        (tc2, "已揀待包",    t_pack, "已揀待包",    "待包裝",     "立即包裝",   "#FAC775","#633806"),
        (tc3, "已包待出 X",  t_x,    "已包待出_X",  "等授權",     "催授權",         "#F7C1C1","#791F1F"),
        (tc4, "已包待出 GO", t_go,   "已包待出_GO", "可立即出貨","立即出貨","#378ADD","#fff"),
    ]:
        with col:
            st.markdown(
                f'<div style="background:#FFF5F5;border:0.5px solid #F7C1C1;border-radius:8px;'
                f'padding:12px;text-align:center;">'
                f'<div style="font-size:11px;color:#A32D2D;font-weight:500;margin-bottom:4px;">{lbl}</div>'
                f'<div style="font-size:30px;font-weight:600;line-height:1;">{val}</div>'
                f'<div style="font-size:10px;color:#888;margin:4px 0;">{sub}</div>'
                f'<div style="background:{bg};color:{fg};font-size:10px;padding:3px 8px;'
                f'border-radius:6px;display:inline-block;font-weight:500;">{act}</div></div>',
                unsafe_allow_html=True)
            if st.button(f"查看細項", key=f"td_{ws_key}"):
                go_to_detail("today_ws", ws_key)

    st.divider()

    # ── Future planning ──
    st.markdown("#### 未來 KPI 規劃")
    fc1, fc2, fc3, fc4 = st.columns(4)
    for col, lbl, dr, clr in [
        (fc1, "明天",   (1,1),    "#854F0B"),
        (fc2, "本週",   (2,4),    "#3B6D11"),
        (fc3, "下週",   (5,11),   "#185FA5"),
        (fc4, "中長期",(12,999),"#888"),
    ]:
        with col:
            m   = (df["days_to_effective"]>=dr[0])&(df["days_to_effective"]<=dr[1])
            sub = df[m]
            n   = len(sub)
            bd  = sub["work_status"].value_counts().to_dict()
            ds  = "  ".join(
                f'<span style="color:{WS_COLORS.get(k,"#888")};font-size:10px;">{k} {v}</span>'
                for k,v in bd.items())
            st.markdown(
                f'<div style="border:0.5px solid #ddd;border-radius:8px;padding:12px;">'
                f'<div style="font-size:12px;font-weight:500;color:{clr};">{lbl}</div>'
                f'<div style="font-size:26px;font-weight:600;color:{clr};line-height:1.1;">{n}</div>'
                f'<div style="margin-top:4px;">{ds}</div></div>',
                unsafe_allow_html=True)

    st.divider()

    # ── SP breakdown ──
    if sp_col:
        st.markdown("#### Shipping Point 分佈")
        sp_pivot = df.groupby([sp_col,"work_status"]).size().unstack(fill_value=0)
        st.dataframe(sp_pivot, use_container_width=True)

# =============================================================================
# PAGE: DETAIL VIEW  (merged Raw Data + Detail View)
# =============================================================================
elif page == "\U0001f50d Detail View":
    st.markdown("## \U0001f50d Detail View")

    dfk = st.session_state.get("detail_filter_key")
    dfv = st.session_state.get("detail_filter_val")

    # Back button
    if st.button("← 返回 Dashboard"):
        go_to_dashboard()

    st.markdown("---")


    # ── Filters ──
    with st.expander("\U0001f50e 篩選條件", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            ws_opts = sorted(df["work_status"].dropna().unique())
            d_ws = []
            if dfk in ("work_status","today_ws") and dfv in ws_opts:
                d_ws = [dfv]
            sel_ws = st.multiselect("作業狀態", ws_opts, default=d_ws, key="dv_ws")

            p_opts = ["P1","P2","P3","P4","P5","P6","P7"]
            d_p = [dfv] if dfk=="priority" and dfv in p_opts else []
            sel_p = st.multiselect("Priority", p_opts, default=d_p, key="dv_p")

            dn_search = st.text_input("搜尋 DN", value="", key="dv_dn", placeholder="輸入 DN 號碼…")

        with fc2:
            bkt_opts = ["今日必出","明天","本週","下週","中長期"]
            d_bkt = [dfv] if dfk=="kpi_bucket" and dfv in bkt_opts else []
            sel_bkt = st.multiselect("KPI 區間", bkt_opts, default=d_bkt, key="dv_bkt")

            sp_opts = sorted(df[sp_col].dropna().unique()) if sp_col else []
            d_sp = [dfv] if dfk=="sp" and dfv in sp_opts else []
            sel_sp = st.multiselect("Shipping Point", sp_opts, default=d_sp, key="dv_sp")

        with fc3:
            cu_opts = sorted(df["customer_display"].dropna().unique())
            d_cu = [dfv] if dfk=="customer" and dfv in cu_opts else []
            sel_cu = st.multiselect("客戶", cu_opts, default=d_cu, key="dv_cu")

            sel_dt     = st.checkbox("僅今日 dispatch", value=False, key="dv_dt")
            sel_xonly  = st.checkbox("僅 SP=X",        value=False, key="dv_x")
            sel_goonly = st.checkbox("僅 SP=GO",       value=False, key="dv_go")

        with fc4:
            kpi_dates = df["kpi_date"].dropna()
            d_from = st.date_input("KPI From", value=kpi_dates.min() if len(kpi_dates) else date.today(), key="dv_df")
            d_to   = st.date_input("KPI To",   value=kpi_dates.max() if len(kpi_dates) else date.today(), key="dv_dt2")

    # Build mask — date filter only if user changed from dataset defaults
    kpi_min = df["kpi_date"].dropna().min() if df["kpi_date"].notna().any() else date.today()
    kpi_max = df["kpi_date"].dropna().max() if df["kpi_date"].notna().any() else date.today()
    date_filtered = (d_from > kpi_min) or (d_to < kpi_max)

    mask = pd.Series([True]*len(df), index=df.index)
    if sel_ws:             mask &= df["work_status"].isin(sel_ws)
    if sel_p:              mask &= df["priority"].isin(sel_p)
    if sel_bkt:            mask &= df["kpi_bucket"].isin(sel_bkt)
    if sel_sp and sp_col:  mask &= df[sp_col].isin(sel_sp)
    if sel_cu:             mask &= df["customer_display"].isin(sel_cu)
    if sel_dt:             mask &= df["dispatch_today"]
    if sel_xonly:          mask &= df["Special Processing"].astype(str).str.strip()=="X"
    if sel_goonly:         mask &= df["Special Processing"].astype(str).str.strip()=="GO"
    if dn_search and dn_col:
        mask &= df[dn_col].astype(str).str.contains(dn_search.strip(), case=False, na=False)
    if date_filtered:
        # NaN kpi_date rows pass through (not excluded by date filter)
        mask &= df["kpi_date"].apply(
            lambda d: (d_from <= d <= d_to) if pd.notna(d) else True)

    # today_ws pre-filter from dashboard click
    if dfk == "today_ws" and dfv:
        mask &= df["work_status"] == dfv
        mask &= df["days_to_effective"] <= 0

    filtered = df[mask].copy()

    # ── Summary counts (filtered) ──
    sm1, sm2, sm3, sm4 = st.columns(4)
    for col, ws, lbl, bg, fg in [
        (sm1, "未揀貨",      "未揀貨",      "#EAF3DE","#3B6D11"),
        (sm2, "已揀待包",    "已揀待包",    "#FAEEDA","#854F0B"),
        (sm3, "已包待出_GO", "已包待出 GO", "#E6F1FB","#185FA5"),
        (sm4, "已包待出_X",  "已包待出 X",  "#FCEBEB","#A32D2D"),
    ]:
        with col:
            n = len(filtered[filtered["work_status"]==ws])
            tot = len(df[df["work_status"]==ws])
            st.markdown(
                f'<div style="background:{bg};border-radius:8px;padding:10px;text-align:center;">'                f'<div style="font-size:11px;color:{fg};font-weight:600;">{lbl}</div>'                f'<div style="font-size:28px;font-weight:700;color:{fg};">{n}</div>'                f'<div style="font-size:10px;color:#888;">共 {tot} 筆</div>'                f'</div>',
                unsafe_allow_html=True)
    st.markdown("")
    st.caption(f"篩選結果 {len(filtered)} / {len(df)} 筆")

    dcols = [c for c in [
        sp_col, dn_col, "customer_display",
        "New CRSD", "kpi_date", "effective_ship_date",
        "work_status", "priority", "kpi_bucket",
        "dispatch_rule_display", "cip_direct",
        "DN Created Date/Time(TW time)",
        "Picking Status", "Packing Status",
        "sp_display", box_col,
    ] if c and c in filtered.columns]
    seen = set(); dcols = [c for c in dcols if not (c in seen or seen.add(c))]

    def _cws(v):
        c = WS_COLORS.get(v,""); return f"color:{c};font-weight:bold" if c else ""
    def _cp(v):
        c = P_COLORS.get(v,"");  return f"color:{c};font-weight:bold" if c else ""

    _display = filtered[dcols].rename(columns=display_rename)
    _ws_col = display_rename("work_status")
    _p_col  = display_rename("priority")
    _style  = _display.style
    if _ws_col in _display.columns: _style = _style.map(_cws, subset=[_ws_col])
    if _p_col  in _display.columns: _style = _style.map(_cp,  subset=[_p_col])
    st.dataframe(_style, use_container_width=True, height=520)

    csv = filtered[dcols].rename(columns=display_rename).to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "下載 CSV",
        data=csv.encode("utf-8-sig"),
        file_name=f"detail_{date.today()}.csv",
        mime="text/csv")

    if st.button("← 返回 Dashboard (下方)", key="back_bot"):
        go_to_dashboard()

# =============================================================================
# PAGE: CS PRINT LIST
# =============================================================================
elif page == "\U0001f5a8 CS Print List":
    today = date.today()
    today_w = WEEKDAY_MAP.get(today.weekday(),"")
    wd_cn = {"W1":"一","W2":"二","W3":"三","W4":"四","W5":"五"}.get(today_w,"")

    st.markdown("## \U0001f5a8 CS 出貨清單 — 依 Dispatch 規則")
    st.info(
        "⚠️ 注意：未包貨完成（Packing 未結束）的訂單，"
        "將不在此清單中。請確認已包待出_GO 訂單再安排出貨。"
    )

    ct1, ct2, ct3 = st.columns([2, 1, 1])
    with ct1:
        show_mode = st.radio(
            "顯示模式",
            ["今日 Dispatch 可出", "全部 GO 訂單", "今日 KPI 全部"],
            horizontal=True)
    with ct2:
        show_x       = st.checkbox("包含 X 待授權（標注警示）", value=True)
    with ct3:
        filter_etd_today = st.checkbox("僅今日 ETD", value=False, key="cs_etd_today")

    if show_mode == "今日 Dispatch 可出":
        # Use effective_ship_date <= today (same logic as Dashboard "今天必出")
        mp    = (df["days_to_effective"] <= 0) & (df["work_status"]=="已包待出_GO")
        title = f"今日 ({today_w} 星期{wd_cn}) Dispatch — GO 可出"
    elif show_mode == "全部 GO 訂單":
        mp    = df["work_status"]=="已包待出_GO"
        title = "全部 GO 待出訂單"
    else:
        mp    = df["days_to_effective"] <= 0
        title = f"今日 KPI 到期全部（{today}）"

    if show_x:
        mx       = (df["work_status"]=="已包待出_X") & (df["days_to_effective"] <= 0)
        print_df = df[mp|mx].copy()
    else:
        print_df = df[mp].copy()

    # ── ETD today filter ──────────────────────────────────────────────────────
    if filter_etd_today and etd_col and etd_col in print_df.columns:
        def _etd_is_today(v):
            if pd.isna(v): return False
            try:
                return pd.to_datetime(v).date() == today
            except Exception:
                return str(v)[:10] == str(today)
        print_df = print_df[print_df[etd_col].apply(_etd_is_today)]

    print_df["exc_flag"] = ""

    # ── Manual exception section ──────────────────────────────────────────────
    with st.expander("\U0001f527 手動加入例外出貨（不受 Dispatch Rule 限制）", expanded=False):
        exc_go_df = df[(df["work_status"]=="已包待出_GO") & ~df.index.isin(print_df.index)]
        exc_cu_opts = sorted(exc_go_df["customer_display"].dropna().unique())
        exc_dn_opts = sorted(exc_go_df[dn_col].astype(str).unique()) if dn_col else []

        sel_all_cu = st.checkbox("全選所有客戶", key="exc_all_cu")
        if sel_all_cu:
            sel_exc_cu = exc_cu_opts
            st.caption(f"已選全部 {len(exc_cu_opts)} 位客戶 ({len(exc_go_df)} DNs)")
        else:
            sel_exc_cu = st.multiselect("按客戶選擇", exc_cu_opts, key="exc_cu")
        sel_exc_dn = st.multiselect("按 DN 個別加入", exc_dn_opts, key="exc_dn")

    exc_mask = pd.Series([False]*len(df), index=df.index)
    if sel_exc_cu:
        exc_mask |= (df["customer_display"].isin(sel_exc_cu) & (df["work_status"]=="已包待出_GO"))
    if sel_exc_dn and dn_col:
        exc_mask |= (df[dn_col].astype(str).isin(sel_exc_dn) & (df["work_status"]=="已包待出_GO"))

    exc_rows = df[exc_mask & ~df.index.isin(print_df.index)].copy()
    if len(exc_rows):
        exc_rows["exc_flag"] = "手動加入"
        print_df = pd.concat([print_df, exc_rows])

    po = {"P1":0,"P2":1,"P3":2,"P4":3,"P5":4,"P6":5,"P7":6}
    print_df["_po"] = print_df["priority"].map(po).fillna(9)
    print_df = print_df.sort_values(["_po","days_to_kpi","customer_display"])

    st.markdown(f"### {title}")
    st.caption(f"共 {len(print_df)} 筆 | 產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    pcols_raw = [dn_col, sp_col, etd_col, "DN Created Date/Time(TW time)", "New CRSD",
                 "customer_display", box_col, route_col, dst_col, acct_col,
                 "work_status","priority","dispatch_rule_display","cip_direct",
                 "sp_display","effective_ship_date","exc_flag"]
    # days_to_kpi / days_to_effective / dispatch_today are hidden from display
    seen_p = set()
    pcols = [c for c in pcols_raw if c and c in print_df.columns and not (c in seen_p or seen_p.add(c))]

    _ws_r   = display_rename("work_status")
    _exc_r  = display_rename("exc_flag")
    _dkpi_r = display_rename("days_to_kpi")

    def _sp2(row):
        ws  = row.get(_ws_r, "")
        exc = row.get(_exc_r, "") == "手動加入"
        if exc:
            return ["background-color:#FFF3CD;color:#856404"]*len(row)
        if ws=="已包待出_X":
            return ["background-color:#FCEBEB;color:#A32D2D"]*len(row)
        if ws=="已包待出_GO":
            return ["background-color:#E6F1FB"]*len(row)
        if row.get(_dkpi_r, 999)<=0:
            return ["background-color:#FFF5F5"]*len(row)
        return [""]*len(row)

    _print_display = print_df[pcols].rename(columns=display_rename)
    st.dataframe(_print_display.style.apply(_sp2, axis=1), use_container_width=True, height=480)

    st.markdown("#### 客戶彙總")
    agg_d = {
        "DNs":      ("customer_display","count"),
        "Dispatch": ("dispatch_rule_display", lambda x: x.mode()[0] if not x.empty else ""),
        "Status":   ("work_status", lambda x: ", ".join(x.unique()[:2])),
        "Min_CRSD": ("New CRSD","min"),
    }
    if box_col: agg_d["Boxes"] = (box_col,"sum")
    summary = (
        print_df.groupby("customer_display").agg(**agg_d)
        .sort_values("DNs",ascending=False).reset_index()
    )
    st.dataframe(summary.rename(columns=display_rename), use_container_width=True)

    st.markdown("---")
    dl1, dl2 = st.columns(2)
    with dl1:
        csv_p = print_df[pcols].rename(columns=display_rename).to_csv(index=False, encoding="utf-8-sig")
        st.download_button("下載出貨清單 CSV",
                           data=csv_p.encode("utf-8-sig"),
                           file_name=f"cs_print_{date.today()}.csv", mime="text/csv")
    with dl2:
        st.info("Ctrl+P (Windows) / Cmd+P (Mac) 可列印目前畫面")
