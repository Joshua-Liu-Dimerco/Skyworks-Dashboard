#!/usr/bin/env python3
"""
OP&CS Operations Dashboard - Streamlit App
4 Pages: Dashboard | Raw Data | Detail View | CS Print List
Requirements: pip install streamlit pandas openpyxl
"""

import io
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime

st.set_page_config(
    page_title="OP&CS 作業排程",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────────────────────
CUTOFF_HOUR   = 11
CUTOFF_MINUTE = 30

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
    "未撿貨":      "#3B6D11",
    "已撿待包":    "#854F0B",
    "已包待出_GO": "#185FA5",
    "已包待出_X":  "#A32D2D",
}

P_COLORS = {
    "P1": "#E24B4A",
    "P2": "#EF9F27",
    "P3": "#3B6D11",
    "P4": "#888888",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def find_col(df, *keywords):
    for kw in keywords:
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

    # column detection
    customer_col = find_col(df, "sold-to name", "sold to name", "customer name", "customer")
    if not customer_col or customer_col not in df.columns:
        customer_col = find_col(df, "sold") or df.columns[0]
    ship_country_col = find_col(df, "ship to country", "ship-to country", "shipto country")
    incoterms_col    = find_col(df, "incoterms", "inco term", "payment code", "terms")

    # step 1 – parse dates
    df["New CRSD"] = pd.to_datetime(df["New CRSD"], errors="coerce").dt.date
    df["DN Created Date/Time"] = pd.to_datetime(df["DN Created Date/Time"], errors="coerce")

    # step 2 – work status
    def _ws(row):
        pick = str(row.get("Picking Status", ""))
        pack = str(row.get("Packing Status", ""))
        sp   = str(row.get("Special Processing", "")).strip()
        if "A - Not yet" in pick:
            return "未撿貨"
        if "C - Completely" in pick and "Not Relevant" in pack:
            return "已撿待包"
        if "C - Completely" in pick and "C - Completely" in pack:
            return "已包待出_X" if sp == "X" else "已包待出_GO"
        return "其他"

    df["work_status"] = df.apply(_ws, axis=1)

    # step 3 – dispatch rule
    def _rule(customer, ship_country):
        cu = str(customer).upper()
        cy = str(ship_country).upper().strip()
        if "FEDEX" in cu:
            return "FEDEX"
        if "DHL" in cu:
            return "DHL"
        for key, dest_rules in RULES_RAW.items():
            if key.upper() in cu:
                for dk, rule in dest_rules.items():
                    if dk == "*":
                        return rule
                    if dk.upper() in cy or cy in dk.upper():
                        return rule
        return ""

    df["dispatch_rule"] = df.apply(
        lambda r: _rule(
            r.get(customer_col, ""),
            r.get(ship_country_col, "") if ship_country_col else ""
        ),
        axis=1,
    )

    def _dispatch_today(rule):
        if not rule:
            return False
        if rule in ("Everyday", "FEDEX", "DHL", "T3EX"):
            return True
        return today_w in [x.strip() for x in rule.split("/")]

    df["dispatch_today"] = df["dispatch_rule"].apply(_dispatch_today)
    df["today_w"] = today_w

    # step 4 – kpi_date with 11:30 cutoff
    # Applies when: CRSD=today AND work=GO AND dispatch_today AND DN time >= 11:30
    def _kpi_date(row):
        crsd = row["New CRSD"]
        dn   = row["DN Created Date/Time"]
        if pd.isna(crsd):
            return crsd
        is_go        = row["work_status"] == "已包待出_GO"
        crsd_today   = crsd == today
        d_today      = row["dispatch_today"]
        past_cutoff  = pd.notna(dn) and (dn.hour, dn.minute) >= (CUTOFF_HOUR, CUTOFF_MINUTE)
        if crsd_today and is_go and d_today and past_cutoff:
            return next_workday(today)
        return crsd

    df["kpi_date"] = df.apply(_kpi_date, axis=1)
    df["days_to_kpi"] = df["kpi_date"].apply(
        lambda d: (d - today).days if pd.notna(d) else 999
    )

    # step 5 – effective ship date
    def _eff(row):
        kd   = row["kpi_date"]
        rule = row["dispatch_rule"]
        if pd.isna(kd):
            return kd
        return next_dispatch_day(max(kd, today), rule)

    df["effective_ship_date"] = df.apply(_eff, axis=1)
    df["days_to_effective"] = df["effective_ship_date"].apply(
        lambda d: (d - today).days if pd.notna(d) else 999
    )

    # step 6 – priority
    def _priority(row):
        days   = row["days_to_kpi"]
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

    df["priority"] = df.apply(_priority, axis=1)

    # step 7 – kpi_bucket (SP=X always "待核准出貨")
    def _bucket(row):
        if str(row.get("Special Processing", "")).strip() == "X":
            return "待核准出貨"
        days = row["days_to_effective"]
        if days <= 0:
            return "今日必出"
        if days == 1:
            return "明天"
        if days <= 4:
            return "本週"
        if days <= 11:
            return "下週"
        return "中長期"

    df["kpi_bucket"] = df.apply(_bucket, axis=1)

    # step 8 – display fields
    if incoterms_col and incoterms_col in df.columns:
        df["customer_display"] = (
            df[incoterms_col].astype(str).str.strip().str.upper()
            + "-"
            + df[customer_col].astype(str).str.strip().str.upper()
        )
        df["customer_display"] = df["customer_display"].str.replace(r"^NAN-", "", regex=True)
    else:
        df["customer_display"] = df[customer_col].astype(str).str.strip()

    df["dispatch_rule_display"] = df["dispatch_rule"].apply(
        lambda r: "" if r == "Everyday" else r
    )

    return df, customer_col


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## OP&CS 作業排程")
    st.markdown("---")

    page = st.radio(
        "頁面導航",
        ["Dashboard", "Raw Data", "Detail View", "CS Print List"],
        index=st.session_state.get("page_index", 0),
        key="nav_radio",
    )

    st.markdown("---")
    st.markdown("### 上傳資料")
    f1 = st.file_uploader("Open DN — CHBT, AK3T",       type=["xlsx"], key="f1")
    f2 = st.file_uploader("Open DN — ASEM, A3TA, ASEA", type=["xlsx"], key="f2")

    st.markdown("---")
    _td = date.today()
    _wl = WEEKDAY_MAP.get(_td.weekday(), "")
    _wc = {"W1": "一", "W2": "二", "W3": "三", "W4": "四", "W5": "五"}.get(_wl, "")
    st.markdown(f"**今天：** {_td}  \n**{_wl} (星期{_wc})**")
    st.caption("KPI 截止點：11:30 (New CRSD 基準)")


# ── Load data ──────────────────────────────────────────────────────────────────
if not f1 or not f2:
    st.info("請在左側上傳兩份 Open Delivery Notes Excel 檔案")
    st.stop()


@st.cache_data(show_spinner="載入資料中…")
def _load(b1, b2):
    dfs = []
    for b in [b1, b2]:
        dfs.append(pd.read_excel(io.BytesIO(b), sheet_name="Open Delivery Notes", header=1))
    return pd.concat(dfs, ignore_index=True)


raw_df = _load(f1.read(), f2.read())
df, customer_col = process_data(raw_df)
f1.seek(0)
f2.seek(0)


def go_to_detail(key, val):
    st.session_state["detail_filter_key"] = key
    st.session_state["detail_filter_val"] = val
    st.session_state["page_index"] = 2
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 – DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    today = date.today()

    counts  = df["work_status"].value_counts()
    ws_pick = counts.get("未撿貨", 0)
    ws_pack = counts.get("已撿待包", 0)
    ws_go   = counts.get("已包待出_GO", 0)
    ws_x    = counts.get("已包待出_X", 0)

    box_col  = find_col(df, "件數", "box", "carton", "qty")
    boxes_go = int(df[df["work_status"] == "已包待出_GO"][box_col].sum()) if box_col else 0
    boxes_x  = int(df[df["work_status"] == "已包待出_X"][box_col].sum()) if box_col else 0

    t_pick = len(df[(df["work_status"] == "未撿貨")     & (df["days_to_kpi"] <= 0)])
    t_pack = len(df[(df["work_status"] == "已撿待包")    & (df["days_to_kpi"] <= 0)])
    t_x    = len(df[(df["work_status"] == "已包待出_X")  & (df["days_to_kpi"] <= 0)])
    t_go   = len(df[(df["work_status"] == "已包待出_GO") & (df["days_to_kpi"] <= 0)])
    t_tot  = t_pick + t_pack + t_x + t_go

    wl = WEEKDAY_MAP.get(today.weekday(), "")
    wc = {"W1": "一", "W2": "二", "W3": "三", "W4": "四", "W5": "五"}.get(wl, "")

    hc1, hc2 = st.columns([3, 1])
    with hc1:
        st.markdown("## OP&CS 作業排程")
    with hc2:
        st.markdown(f"**{wl} 星期{wc}** · {today}")
    st.caption(f"KPI 截止點 11:30 | New CRSD 基準 | 今天 = {wl}")
    st.divider()

    # three status cards
    col1, col2, col3 = st.columns(3, gap="medium")

    with col1:
        st.markdown(
            f'<div style="background:#EAF3DE;border-radius:10px;padding:16px;">'
            f'<div style="font-size:12px;color:#3B6D11;font-weight:600;">① 未撿貨</div>'
            f'<div style="font-size:11px;color:#5a7a3a;margin-bottom:8px;">Picking=A Not yet processed</div>'
            f'<div style="font-size:38px;font-weight:600;color:#3B6D11;line-height:1;">{ws_pick}</div>'
            f'<div style="font-size:11px;color:#5a7a3a;margin-top:4px;">DNs 待備貨</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        pick_df = df[df["work_status"] == "未撿貨"]
        for bkt, clr in [("今日必出", "#E24B4A"), ("明天", "#EF9F27"),
                          ("本週", "#3B6D11"), ("下週", "#888"), ("中長期", "#aaa")]:
            n = len(pick_df[pick_df["kpi_bucket"] == bkt])
            st.markdown(
                f'<span style="color:{clr};font-weight:500;">{bkt}</span>'
                f'<span style="float:right;font-weight:600;">{n}</span>',
                unsafe_allow_html=True,
            )
        if st.button("詳細查看 未撿貨", key="db_pick"):
            go_to_detail("work_status", "未撿貨")

    with col2:
        st.markdown(
            f'<div style="background:#FAEEDA;border-radius:10px;padding:16px;">'
            f'<div style="font-size:12px;color:#854F0B;font-weight:600;">② 已撿待包</div>'
            f'<div style="font-size:11px;color:#a06020;margin-bottom:8px;">Picking=C Packing=Not Relevant</div>'
            f'<div style="font-size:38px;font-weight:600;color:#854F0B;line-height:1;">{ws_pack}</div>'
            f'<div style="font-size:11px;color:#a06020;margin-top:4px;">DNs 待包裝</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        pack_df = df[df["work_status"] == "已撿待包"]
        for bkt, clr in [("今日必出", "#E24B4A"), ("明天", "#EF9F27"),
                          ("本週", "#3B6D11"), ("下週", "#888"), ("中長期", "#aaa")]:
            n = len(pack_df[pack_df["kpi_bucket"] == bkt])
            st.markdown(
                f'<span style="color:{clr};font-weight:500;">{bkt}</span>'
                f'<span style="float:right;font-weight:600;">{n}</span>',
                unsafe_allow_html=True,
            )
        if st.button("詳細查看 已撿待包", key="db_pack"):
            go_to_detail("work_status", "已撿待包")

    with col3:
        boxes_total = boxes_go + boxes_x
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#E6F1FB 50%,#FCEBEB 50%);'
            f'border-radius:10px;padding:16px;">'
            f'<div style="font-size:12px;font-weight:600;">③ 已包待出</div>'
            f'<div style="font-size:11px;color:#555;margin-bottom:8px;">Picking=C Packing=C {boxes_total} boxes</div>'
            f'<div style="font-size:38px;font-weight:600;line-height:1;">{ws_go + ws_x}</div>'
            f'<div style="font-size:11px;color:#555;margin-top:4px;">DNs 待出貨</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        c3a, c3b = st.columns(2)
        with c3a:
            st.markdown(
                f'<div style="background:#E6F1FB;border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="color:#042C53;font-size:11px;font-weight:600;">GO 可出</div>'
                f'<div style="color:#185FA5;font-size:26px;font-weight:600;">{ws_go}</div>'
                f'<div style="color:#185FA5;font-size:10px;">{boxes_go} boxes</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("查看 GO", key="db_go"):
                go_to_detail("work_status", "已包待出_GO")
        with c3b:
            st.markdown(
                f'<div style="background:#FCEBEB;border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="color:#791F1F;font-size:11px;font-weight:600;">X 待授權</div>'
                f'<div style="color:#A32D2D;font-size:26px;font-weight:600;">{ws_x}</div>'
                f'<div style="color:#A32D2D;font-size:10px;">{boxes_x} boxes</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("查看 X", key="db_x"):
                go_to_detail("work_status", "已包待出_X")

    st.divider()

    # today must-ship
    st.markdown(
        f'<div style="background:#FCEBEB;border:1px solid #F7C1C1;border-radius:10px;'
        f'padding:14px 20px;margin-bottom:16px;">'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<span style="font-size:16px;">🔴</span>'
        f'<span style="font-size:15px;font-weight:600;color:#A32D2D;">今天必出 — New CRSD 到期</span>'
        f'<span style="font-size:26px;font-weight:600;color:#A32D2D;margin-left:auto;">{t_tot}</span>'
        f'<span style="font-size:12px;color:#A32D2D;">DNs</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    tc1, tc2, tc3, tc4 = st.columns(4)
    for col, lbl, val, sub, act, bg, fg in [
        (tc1, "未撿貨",      t_pick, "逾期未備",  "立即備貨",   "#C0DD97", "#27500A"),
        (tc2, "已撿待包",    t_pack, "待包裝",     "立即包裝",   "#FAC775", "#633806"),
        (tc3, "已包待出 X",  t_x,    "等授權",     "催授權",     "#F7C1C1", "#791F1F"),
        (tc4, "已包待出 GO", t_go,   "可立即出貨", "立即出貨",   "#378ADD", "#fff"),
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
                unsafe_allow_html=True,
            )

    st.divider()

    # future planning
    st.markdown("#### 未來 KPI 規劃")
    fc1, fc2, fc3, fc4 = st.columns(4)
    for col, lbl, dr, clr in [
        (fc1, "明天",   (1, 1),    "#854F0B"),
        (fc2, "本週",   (2, 4),    "#3B6D11"),
        (fc3, "下週",   (5, 11),   "#185FA5"),
        (fc4, "中長期", (12, 999), "#888"),
    ]:
        with col:
            m = (df["days_to_effective"] >= dr[0]) & (df["days_to_effective"] <= dr[1])
            sub = df[m]
            n   = len(sub)
            bd  = sub["work_status"].value_counts().to_dict()
            ds  = "  ".join(
                f'<span style="color:{WS_COLORS.get(k,"#888")};font-size:10px;">{k} {v}</span>'
                for k, v in bd.items()
            )
            st.markdown(
                f'<div style="border:0.5px solid #ddd;border-radius:8px;padding:12px;">'
                f'<div style="font-size:12px;font-weight:500;color:{clr};">{lbl}</div>'
                f'<div style="font-size:26px;font-weight:600;color:{clr};line-height:1.1;">{n}</div>'
                f'<div style="margin-top:4px;">{ds}</div></div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # SP=X section
    st.markdown("#### Special Processing = X — 待核准出貨分析")
    x_df    = df[df["Special Processing"].astype(str).str.strip() == "X"].copy()
    x_total = len(x_df)
    x_boxes = int(x_df[box_col].sum()) if box_col else 0

    if x_total == 0:
        st.success("目前無 Special Processing = X 的訂單")
    else:
        x_packed   = len(x_df[x_df["work_status"] == "已包待出_X"])
        x_need_pk  = len(x_df[x_df["work_status"] == "已撿待包"])
        x_not_pick = len(x_df[x_df["work_status"] == "未撿貨"])

        xm1, xm2, xm3, xm4 = st.columns(4)
        for col, lbl, val, clr, sub in [
            (xm1, "X 總計",        x_total,    "#791F1F", f"{x_boxes} boxes"),
            (xm2, "已包待授權",    x_packed,   "#A32D2D", "已包待出_X"),
            (xm3, "需包裝 (已撿)", x_need_pk,  "#854F0B", "已撿待包"),
            (xm4, "需備貨 (未撿)", x_not_pick, "#3B6D11", "未撿貨"),
        ]:
            with col:
                st.markdown(
                    f'<div style="border-left:4px solid {clr};padding:8px 12px;'
                    f'background:#fafafa;border-radius:4px;">'
                    f'<div style="font-size:11px;color:{clr};font-weight:600;">{lbl}</div>'
                    f'<div style="font-size:24px;font-weight:600;color:{clr};">{val}</div>'
                    f'<div style="font-size:10px;color:#888;">{sub}</div></div>',
                    unsafe_allow_html=True,
                )

        dn_col_x  = find_col(df, "delivery")
        sp_col_x  = find_col(df, "shipping point", "ship. pt")
        xcols_raw = [sp_col_x, dn_col_x, "customer_display",
                     "New CRSD", "DN Created Date/Time",
                     "effective_ship_date", "dispatch_rule_display",
                     "work_status", "priority", box_col]
        seen_x  = set()
        x_cols  = [c for c in xcols_raw
                   if c and c in x_df.columns and not (c in seen_x or seen_x.add(c))]
        x_sorted = x_df.sort_values(["days_to_kpi", "customer_display"])[x_cols]

        def _sx(row):
            ws = row.get("work_status", "")
            if ws == "已包待出_X":
                return ["background-color:#FCEBEB"] * len(row)
            if ws == "已撿待包":
                return ["background-color:#FAEEDA"] * len(row)
            if ws == "未撿貨":
                return ["background-color:#EAF3DE"] * len(row)
            return [""] * len(row)

        st.caption("KPI Bucket 一律為「待核准出貨」| effective_ship_date = 依 dispatch rule 最近可出日")
        st.dataframe(x_sorted.style.apply(_sx, axis=1), use_container_width=True, height=320)

        with st.expander("X 訂單客戶彙總", expanded=False):
            xagg = (
                x_df.groupby("customer_display")
                .agg(
                    DNs=("customer_display", "count"),
                    Min_CRSD=("New CRSD", "min"),
                    Max_CRSD=("New CRSD", "max"),
                    Earliest_Ship=("effective_ship_date", "min"),
                    Dispatch=("dispatch_rule_display",
                              lambda s: s.mode()[0] if not s.empty else ""),
                    Stage=("work_status",
                           lambda s: ", ".join(s.unique()[:3])),
                )
                .sort_values("Min_CRSD")
                .reset_index()
            )
            if box_col:
                xb = x_df.groupby("customer_display")[box_col].sum().rename("Boxes")
                xagg = xagg.merge(xb, on="customer_display", how="left")
            st.dataframe(xagg, use_container_width=True)

    st.divider()

    # SP breakdown
    st.markdown("#### Shipping Point 分佈")
    sp_col_db = find_col(df, "shipping point", "ship. pt")
    if sp_col_db:
        sp_pivot = df.groupby([sp_col_db, "work_status"]).size().unstack(fill_value=0)
        st.dataframe(sp_pivot, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 – RAW DATA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Raw Data":
    st.markdown("## Raw Data — 完整訂單列表")

    sp_col = find_col(df, "shipping point", "ship. pt")
    dn_col = find_col(df, "delivery")

    with st.expander("篩選條件", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            sel_ws = st.multiselect("作業狀態", options=sorted(df["work_status"].dropna().unique()), default=[])
            sel_p  = st.multiselect("優先級",   options=["P1", "P2", "P3", "P4"], default=[])
        with fc2:
            sp_opts = sorted(df[sp_col].dropna().unique()) if sp_col else []
            sel_sp  = st.multiselect("Shipping Point", options=sp_opts, default=[])
            sel_bkt = st.multiselect("KPI 區間",
                                     options=["今日必出", "明天", "本週", "下週", "中長期", "待核准出貨"],
                                     default=[])
        with fc3:
            sel_cust  = st.multiselect("客戶", options=sorted(df["customer_display"].dropna().unique()), default=[])
            sel_dt    = st.checkbox("僅今日 dispatch", value=False)
            sel_xonly = st.checkbox("僅 Special Processing = X", value=False)

        cr1, cr2 = st.columns(2)
        with cr1:
            date_from = st.date_input("KPI 日期 From", value=df["kpi_date"].dropna().min())
        with cr2:
            date_to   = st.date_input("KPI 日期 To",   value=df["kpi_date"].dropna().max())

    mask = pd.Series([True] * len(df), index=df.index)
    if sel_ws:
        mask &= df["work_status"].isin(sel_ws)
    if sel_p:
        mask &= df["priority"].isin(sel_p)
    if sel_sp and sp_col:
        mask &= df[sp_col].isin(sel_sp)
    if sel_bkt:
        mask &= df["kpi_bucket"].isin(sel_bkt)
    if sel_cust:
        mask &= df["customer_display"].isin(sel_cust)
    if sel_dt:
        mask &= df["dispatch_today"]
    if sel_xonly:
        mask &= df["Special Processing"].astype(str).str.strip() == "X"
    mask &= df["kpi_date"].apply(lambda d: date_from <= d <= date_to if pd.notna(d) else False)

    filtered = df[mask].copy()
    st.caption(f"顯示 {len(filtered)} / {len(df)} 筆")

    dcols = [c for c in [
        sp_col, dn_col, "customer_display",
        "New CRSD", "kpi_date", "effective_ship_date", "days_to_kpi",
        "work_status", "priority", "kpi_bucket",
        "dispatch_rule_display", "dispatch_today",
        "Picking Status", "Packing Status", "Special Processing",
    ] if c and c in filtered.columns]

    def _cws(v):
        c = WS_COLORS.get(v, "")
        return f"color:{c};font-weight:bold" if c else ""

    def _cp(v):
        c = P_COLORS.get(v, "")
        return f"color:{c};font-weight:bold" if c else ""

    st.dataframe(
        filtered[dcols].style.map(_cws, subset=["work_status"]).map(_cp, subset=["priority"]),
        use_container_width=True, height=500,
    )
    csv = filtered[dcols].to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載篩選結果 CSV", data=csv.encode("utf-8-sig"),
                       file_name=f"opcs_raw_{date.today()}.csv", mime="text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 – DETAIL VIEW
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Detail View":
    st.markdown("## Detail View")

    dfk = st.session_state.get("detail_filter_key")
    dfv = st.session_state.get("detail_filter_val")
    sp_col = find_col(df, "shipping point", "ship. pt")

    c1, c2, c3 = st.columns(3)
    with c1:
        ws_opts = sorted(df["work_status"].dropna().unique())
        dws = [dfv] if dfk == "work_status" and dfv in ws_opts else []
        sel_ws_d = st.multiselect("作業狀態", options=ws_opts, default=dws, key="d_ws")
    with c2:
        cu_opts = sorted(df["customer_display"].dropna().unique())
        dcu = [dfv] if dfk == "customer" and dfv in cu_opts else []
        sel_cu_d = st.multiselect("客戶", options=cu_opts, default=dcu, key="d_cu")
    with c3:
        sp_opts = sorted(df[sp_col].dropna().unique()) if sp_col else []
        dsp = [dfv] if dfk == "sp" and dfv in sp_opts else []
        sel_sp_d = st.multiselect("Shipping Point", options=sp_opts, default=dsp, key="d_sp")

    md = pd.Series([True] * len(df), index=df.index)
    if sel_ws_d:
        md &= df["work_status"].isin(sel_ws_d)
    if sel_cu_d:
        md &= df["customer_display"].isin(sel_cu_d)
    if sel_sp_d and sp_col:
        md &= df[sp_col].isin(sel_sp_d)

    sub_d = df[md].copy()
    if dfv:
        st.info(f"Dashboard 來源：**{dfv}** → {len(sub_d)} 筆")

    d1, d2, d3, d4 = st.columns(4)
    for col, ws, lbl in [
        (d1, "未撿貨",      "未撿貨"),
        (d2, "已撿待包",    "已撿待包"),
        (d3, "已包待出_GO", "已包待出 GO"),
        (d4, "已包待出_X",  "已包待出 X"),
    ]:
        with col:
            n  = len(sub_d[sub_d["work_status"] == ws])
            clr = WS_COLORS.get(ws, "#888")
            st.markdown(
                f'<div style="border-left:4px solid {clr};padding:8px 12px;'
                f'background:#fafafa;border-radius:4px;">'
                f'<div style="font-size:11px;color:{clr};font-weight:600;">{lbl}</div>'
                f'<div style="font-size:24px;font-weight:600;">{n}</div></div>',
                unsafe_allow_html=True,
            )

    box_col_d  = find_col(df, "件數", "box", "carton")
    wt_col_d   = find_col(df, "weight", "wt")
    dn_col_d   = find_col(df, "delivery")

    dcols_d = [c for c in [
        sp_col, dn_col_d, "customer_display",
        "New CRSD", "kpi_date", "effective_ship_date",
        "days_to_kpi", "kpi_bucket",
        "work_status", "priority",
        "dispatch_rule_display", "dispatch_today",
        "Picking Status", "Packing Status", "Special Processing",
        box_col_d, wt_col_d,
    ] if c and c in sub_d.columns]
    seen_d = set()
    dcols_d = [c for c in dcols_d if not (c in seen_d or seen_d.add(c))]

    def _hr(row):
        bg = {"未撿貨": "#EAF3DE", "已撿待包": "#FAEEDA",
              "已包待出_GO": "#E6F1FB", "已包待出_X": "#FCEBEB"}.get(row.get("work_status", ""), "")
        return [f"background-color:{bg}" if bg else "" for _ in row]

    st.dataframe(sub_d[dcols_d].style.apply(_hr, axis=1), use_container_width=True, height=520)

    csv_d = sub_d[dcols_d].to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載此列表 CSV", data=csv_d.encode("utf-8-sig"),
                       file_name=f"detail_{dfv or 'all'}_{date.today()}.csv", mime="text/csv")

    if st.button("返回 Dashboard"):
        st.session_state.pop("detail_filter_key", None)
        st.session_state.pop("detail_filter_val", None)
        st.session_state["page_index"] = 0
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 – CS PRINT LIST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "CS Print List":
    st.markdown("## CS 出貨清單 — 依 Dispatch 規則")

    today   = date.today()
    today_w = WEEKDAY_MAP.get(today.weekday(), "")
    wd_cn   = {"W1": "一", "W2": "二", "W3": "三", "W4": "四", "W5": "五"}.get(today_w, "")

    sp_col    = find_col(df, "shipping point", "ship. pt")
    dn_col    = find_col(df, "delivery")
    etd_col   = find_col(df, "etd")
    box_col   = find_col(df, "件數", "box", "carton", "qty")
    route_col = find_col(df, "route")
    dst_col   = find_col(df, "ship to country", "ship-to country", "dst", "destination")
    acct_col  = find_col(df, "delivery account", "account")

    ct1, ct2 = st.columns([2, 1])
    with ct1:
        show_mode = st.radio(
            "顯示模式",
            ["今日 Dispatch 可出", "全部 GO 訂單", "今日 KPI 全部"],
            horizontal=True,
        )
    with ct2:
        show_x = st.checkbox("包含 X 待授權（標注警示）", value=True)

    if show_mode == "今日 Dispatch 可出":
        mp    = df["dispatch_today"] & (df["work_status"] == "已包待出_GO")
        title = f"今日 ({today_w} 星期{wd_cn}) Dispatch — GO 可出"
    elif show_mode == "全部 GO 訂單":
        mp    = df["work_status"] == "已包待出_GO"
        title = "全部 GO 待出訂單"
    else:
        mp    = df["days_to_kpi"] <= 0
        title = f"今日 KPI 到期全部（{today}）"

    if show_x:
        mx       = (df["work_status"] == "已包待出_X") & (df["days_to_kpi"] <= 0)
        print_df = df[mp | mx].copy()
    else:
        print_df = df[mp].copy()

    po = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    print_df["_po"] = print_df["priority"].map(po).fillna(9)
    print_df = print_df.sort_values(["_po", "days_to_kpi", "customer_display"])

    st.markdown(f"### {title}")
    st.caption(f"共 {len(print_df)} 筆 | 產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    pcols_raw = [
        dn_col, sp_col, etd_col, "DN Created Date/Time", "New CRSD",
        "customer_display", box_col, route_col, dst_col, acct_col,
        "work_status", "priority", "dispatch_rule_display",
        "Special Processing", "effective_ship_date",
    ]
    seen_p  = set()
    pcols   = [c for c in pcols_raw
               if c and c in print_df.columns and not (c in seen_p or seen_p.add(c))]

    def _sp(row):
        ws = row.get("work_status", "")
        if ws == "已包待出_X":
            return ["background-color:#FCEBEB;color:#A32D2D"] * len(row)
        if ws == "已包待出_GO":
            return ["background-color:#E6F1FB"] * len(row)
        if row.get("days_to_kpi", 999) <= 0:
            return ["background-color:#FFF5F5"] * len(row)
        return [""] * len(row)

    st.dataframe(print_df[pcols].style.apply(_sp, axis=1), use_container_width=True, height=480)

    st.markdown("#### 客戶彙總")
    agg_d = {
        "DNs":      ("customer_display", "count"),
        "Dispatch": ("dispatch_rule_display", lambda x: x.mode()[0] if not x.empty else ""),
        "Status":   ("work_status", lambda x: ", ".join(x.unique()[:2])),
        "Min_CRSD": ("New CRSD", "min"),
    }
    if box_col:
        agg_d["Boxes"] = (box_col, "sum")

    summary = (
        print_df.groupby("customer_display")
        .agg(**agg_d)
        .sort_values("DNs", ascending=False)
        .reset_index()
    )
    st.dataframe(summary, use_container_width=True)

    st.markdown("---")
    dl1, dl2 = st.columns(2)
    with dl1:
        csv_p = print_df[pcols].to_csv(index=False, encoding="utf-8-sig")
        st.download_button("下載出貨清單 CSV", data=csv_p.encode("utf-8-sig"),
                           file_name=f"cs_print_{today}.csv", mime="text/csv")
    with dl2:
        st.info("Ctrl+P (Windows) / Cmd+P (Mac) 可列印目前畫面")
