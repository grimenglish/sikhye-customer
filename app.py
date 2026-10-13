
import io
import re
import json
from datetime import datetime, date

from datetime import timedelta
from zoneinfo import ZoneInfo


import pandas as pd
import streamlit as st
import requests
import altair as alt

try:
    import msoffcrypto
except Exception:
    msoffcrypto = None

try:
    from supabase import create_client
except Exception:
    create_client = None


st.set_page_config(
    page_title="식혜명가 저장형 고객 CRM",
    page_icon="📦",
    layout="wide",
)

st.markdown("""
<style>
.block-container {padding-top: 2rem;}
.kpi-card {
    background: white;
    border: 1px solid #ECECEC;
    border-radius: 18px;
    padding: 20px 22px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.kpi-title {color:#666;font-size:14px;margin-bottom:8px;}
.kpi-value {font-size:28px;font-weight:800;color:#111;}
.note {
    background:#f6f8fa;
    border:1px solid #e5e7eb;
    padding:14px 16px;
    border-radius:12px;
}
.warn {
    background:#fff7ed;
    border:1px solid #fed7aa;
    padding:14px 16px;
    border-radius:12px;
}

.upload-guide {
    border: 2px dashed #cbd5e1;
    background: #f8fafc;
    border-radius: 18px;
    padding: 22px;
    text-align: center;
    margin-bottom: 14px;
}
.upload-title {
    font-size: 22px;
    font-weight: 800;
    margin-bottom: 6px;
}
.upload-sub {
    color: #64748b;
    font-size: 14px;
}
.summary-box {
    background: #ecfdf5;
    border: 1px solid #bbf7d0;
    border-radius: 16px;
    padding: 16px 18px;
    margin: 12px 0;
}


/* V12 시각 정리: 기존 기능·위젯 구조는 유지 */
:root { color-scheme: light; }
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    overflow-x: auto;
    scrollbar-width: thin;
    border-bottom: 1px solid #e5e7eb;
}
.stTabs [data-baseweb="tab"] {
    white-space: nowrap;
    border-radius: 10px 10px 0 0;
    padding: 10px 12px;
}
.stTabs [aria-selected="true"] {
    color: #b45309 !important;
    background: #fff7ed !important;
    font-weight: 700 !important;
}
[data-testid="stMetric"] {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 12px 14px;
    background-color: #ffffff;
}
[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stNumberInput"]) {
    border-color: #e5e7eb;
}
@media (max-width: 650px) {
    .block-container {padding-top: 1rem; padding-left: .65rem; padding-right: .65rem;}
    h1 {font-size: 1.7rem !important;}
    h2 {font-size: 1.35rem !important;}
    [data-testid="stMetric"] {padding: 8px;}
    .stTabs [data-baseweb="tab"] {padding: 8px 10px;}
}

/* 모바일/다크모드 표 가독성 보정 */
[data-testid="stDataFrame"] {
    background: #ffffff !important;
}
[data-testid="stDataFrame"] div {
    font-size: 13px;
}


/* 실제 Streamlit 파일 업로더 드래그앤드롭 영역 확대 */
[data-testid="stFileUploaderDropzone"] {
    min-height: 130px !important;
    border: 2px dashed #94a3b8 !important;
    border-radius: 18px !important;
    background: #f8fafc !important;
}

</style>
""", unsafe_allow_html=True)

SMARTSTORE_PASSWORD = "1111"



# =========================
# 앱 비밀번호 로그인
# =========================
def require_login():
    app_password = st.secrets.get("APP_PASSWORD", "")

    if not app_password:
        st.error("APP_PASSWORD가 Streamlit Secrets에 설정되지 않았습니다. 개인정보 보호를 위해 앱을 열 수 없습니다.")
        st.stop()

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        with st.sidebar:
            st.success("로그인됨")
            if st.button("로그아웃"):
                st.session_state["authenticated"] = False
                st.rerun()
        return

    st.title("🔐 식혜명가 CRM 로그인")
    st.caption("고객 개인정보 보호를 위해 비밀번호가 필요합니다.")

    password = st.text_input("비밀번호", type="password")
    if st.button("로그인", type="primary"):
        if password == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")

    st.stop()


require_login()


# =========================
# Supabase 연결
# =========================
def get_supabase():
    if create_client is None:
        return None

    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")

    if not url or not key:
        return None

    return create_client(url, key)


sb = get_supabase()


# =========================
# 유틸
# =========================
def normalize_phone(x):
    if pd.isna(x):
        return ""
    return re.sub(r"[^0-9]", "", str(x))


def normalize_text(x):
    if pd.isna(x):
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def normalize_address(x):
    s = normalize_text(x)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def pick_col(df, candidates):
    cols = list(df.columns)
    exact = {str(c).strip(): c for c in cols}

    for c in candidates:
        if c in exact:
            return exact[c]

    for col in cols:
        col_s = str(col).strip()
        for c in candidates:
            if c in col_s:
                return col

    return None


def safe_series(df, col, default=""):
    if col and col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def read_excel_file(uploaded_file):
    raw = uploaded_file.getvalue()

    try:
        return pd.read_excel(io.BytesIO(raw))
    except Exception as first_error:
        if msoffcrypto is None:
            raise RuntimeError("암호화 엑셀을 읽으려면 requirements.txt 최신본이 필요합니다.")

        try:
            office = msoffcrypto.OfficeFile(io.BytesIO(raw))
            office.load_key(password=SMARTSTORE_PASSWORD)
            decrypted = io.BytesIO()
            office.decrypt(decrypted)
            decrypted.seek(0)
            return pd.read_excel(decrypted)
        except Exception as second_error:
            raise RuntimeError(f"엑셀 읽기 실패: {first_error} / 암호해제 실패: {second_error}")


def detect_market(filename, df):
    name = filename.lower()
    cols = set(map(str, df.columns))

    if "delivery" in name or "coupang" in name or "쿠팡" in name:
        return "쿠팡"
    if "스마트스토어" in name or "smartstore" in name or "naver" in name or "네이버" in name:
        return "네이버"
    if "묶음배송번호" in cols or "노출상품명(옵션명)" in cols:
        return "쿠팡"
    if "상품주문번호" in cols or "통합배송지" in cols or "수취인연락처1" in cols:
        return "네이버"

    return "기타"


def standardize(df, market, filename):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if market == "네이버":
        order_unit_col = pick_col(df, ["주문번호"])
        product_order_col = pick_col(df, ["상품주문번호"])
        order_date_col = pick_col(df, ["주문일시", "결제일", "발주확인일", "송장출력일", "발송일"])
        amount_col = pick_col(df, ["최종 상품별 총 주문금액", "최초 상품별 총 주문금액", "정산예정금액"])
        address_col = pick_col(df, ["통합배송지", "기본배송지", "배송지주소", "수취인주소"])
        product_col = pick_col(df, ["상품명"])
    elif market == "쿠팡":
        order_unit_col = pick_col(df, ["묶음배송번호", "주문번호"])
        product_order_col = pick_col(df, ["주문번호"])
        order_date_col = pick_col(df, ["주문일", "출고일(발송일)", "배송완료일"])
        amount_col = pick_col(df, ["결제액", "옵션판매가(판매단가)"])
        address_col = pick_col(df, ["수취인 주소", "배송지주소", "수취인주소", "주소"])
        product_col = pick_col(df, ["노출상품명(옵션명)", "등록상품명"])
    else:
        order_unit_col = pick_col(df, ["주문번호", "묶음배송번호", "상품주문번호"])
        product_order_col = pick_col(df, ["상품주문번호", "주문번호"])
        order_date_col = pick_col(df, ["주문일시", "주문일", "결제일"])
        amount_col = pick_col(df, ["결제금액", "결제액", "최종 상품별 총 주문금액"])
        address_col = pick_col(df, ["통합배송지", "수취인 주소", "주소"])
        product_col = pick_col(df, ["상품명", "노출상품명(옵션명)", "등록상품명"])

    receiver_col = pick_col(df, ["수취인명", "수취인이름", "수령인", "받는분", "수령자명"])
    receiver_phone_col = pick_col(df, ["수취인연락처1", "수취인전화번호", "수취인연락처", "수령인전화번호"])
    buyer_col = pick_col(df, ["구매자명", "구매자", "주문자명"])
    buyer_phone_col = pick_col(df, ["구매자연락처", "구매자전화번호", "주문자연락처"])
    qty_col = pick_col(df, ["수량", "구매수(수량)", "구매수량"])
    option_col = pick_col(df, ["옵션정보", "옵션명", "옵션값", "옵션내용"])

    out = pd.DataFrame(index=df.index)
    out["channel"] = market
    out["source_file"] = filename

    out["order_no"] = safe_series(df, order_unit_col, "").astype(str).str.replace(".0", "", regex=False)
    out["product_order_no"] = safe_series(df, product_order_col, "").astype(str).str.replace(".0", "", regex=False)
    out["order_no"] = out["order_no"].where(out["order_no"].str.strip() != "", out["product_order_no"])

    out["order_date"] = pd.to_datetime(safe_series(df, order_date_col, pd.NaT), errors="coerce")
    out["receiver_name"] = safe_series(df, receiver_col, "").map(normalize_text)
    out["receiver_phone"] = safe_series(df, receiver_phone_col, "").map(normalize_phone)
    out["buyer_name"] = safe_series(df, buyer_col, "").map(normalize_text)
    out["buyer_phone"] = safe_series(df, buyer_phone_col, "").map(normalize_phone)
    out["address"] = safe_series(df, address_col, "").map(normalize_address)
    product_base = safe_series(df, product_col, "").map(normalize_text)
    option_text = safe_series(df, option_col, "").map(normalize_text)
    if market == "네이버":
        out["product_name"] = option_text.where(option_text.str.strip() != "", product_base)
    else:
        out["product_name"] = (product_base + " " + option_text).str.strip()
    out["quantity"] = pd.to_numeric(safe_series(df, qty_col, 1), errors="coerce").fillna(1).astype(int)
    out["amount"] = pd.to_numeric(safe_series(df, amount_col, 0), errors="coerce").fillna(0).astype(int)

    name_key = out["receiver_name"].where(out["receiver_name"] != "", out["buyer_name"])
    phone_key = out["receiver_phone"].where(out["receiver_phone"] != "", out["buyer_phone"])

    out["customer_key"] = name_key.fillna("").astype(str).str.strip() + "|" + out["address"].fillna("").astype(str).str.strip()
    out["customer_key_strict"] = (
        name_key.fillna("").astype(str).str.strip()
        + "|" + phone_key.fillna("").astype(str).str.strip()
        + "|" + out["address"].fillna("").astype(str).str.strip()
    )

    out["order_key"] = out["channel"] + "|" + out["order_no"].astype(str)
    out = out[(name_key != "") | (phone_key != "") | (out["address"] != "")]
    out = out.dropna(subset=["order_date"])
    return out


def join_unique(series):
    vals = []
    for v in series:
        v = str(v).strip()
        if v and v.lower() != "nan" and v not in vals:
            vals.append(v)
    return ", ".join(vals)


def grade(n):
    if n >= 5:
        return "VIP"
    if n >= 3:
        return "우수고객"
    if n >= 2:
        return "재구매"
    return "신규"


def churn(days):
    if days >= 180:
        return "장기이탈"
    if days >= 90:
        return "이탈위험"
    if days >= 60:
        return "관심필요"
    return "정상"


def make_order_level(raw_orders, use_strict=False):
    key_col = "customer_key_strict" if use_strict else "customer_key"

    grouped = (
        raw_orders.groupby(["channel", "order_no", "order_key", key_col, "receiver_name", "receiver_phone", "buyer_name", "buyer_phone", "address"], dropna=False)
        .agg(
            order_date=("order_date", "min"),
            product_order_nos=("product_order_no", join_unique),
            product_names=("product_name", join_unique),
            total_quantity=("quantity", "sum"),
            total_amount=("amount", "sum"),
            source_files=("source_file", join_unique),
            raw_rows=("product_order_no", "count"),
        )
        .reset_index()
        .rename(columns={key_col: "analysis_customer_key"})
    )
    return grouped


def make_customer_df(order_level):
    if order_level.empty:
        return pd.DataFrame()

    customer = (
        order_level.groupby("analysis_customer_key", dropna=False)
        .agg(
            customer_name=("receiver_name", "first"),
            phone=("receiver_phone", "first"),
            address=("address", "first"),
            order_count=("order_key", pd.Series.nunique),
            first_order_date=("order_date", "min"),
            last_order_date=("order_date", "max"),
            total_amount=("total_amount", "sum"),
            total_quantity=("total_quantity", "sum"),
            channels=("channel", join_unique),
            products=("product_names", join_unique),
        )
        .reset_index()
    )

    # Supabase timestamptz는 timezone-aware 값으로 들어오므로 UTC 기준으로 통일
    today = pd.Timestamp.now(tz="UTC").normalize()
    customer["grade"] = customer["order_count"].apply(grade)
    customer["customer_type"] = customer["order_count"].apply(lambda x: "재구매" if x >= 2 else "신규")
    last_order = pd.to_datetime(customer["last_order_date"], utc=True, errors="coerce").dt.normalize()
    customer["days_since_last_order"] = (today - last_order).dt.days.fillna(0).astype(int)
    customer["churn_status"] = customer["days_since_last_order"].apply(churn)
    customer["avg_order_amount"] = (customer["total_amount"] / customer["order_count"]).round(0).fillna(0).astype(int)
    return customer


@st.cache_data(ttl=120, show_spinner=False)
def fetch_all(table_name):
    if sb is None:
        return pd.DataFrame()

    rows = []
    step = 1000
    start = 0

    while True:
        res = sb.table(table_name).select("*").range(start, start + step - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < step:
            break
        start += step

    return pd.DataFrame(rows)


def upsert_orders(order_level):
    if sb is None or order_level.empty:
        return 0

    records = []
    now = datetime.now().isoformat(timespec="seconds")

    for _, r in order_level.iterrows():
        records.append({
            "order_key": str(r["order_key"]),
            "channel": str(r["channel"]),
            "order_no": str(r["order_no"]),
            "customer_key": str(r["analysis_customer_key"]),
            "receiver_name": str(r["receiver_name"]),
            "receiver_phone": str(r["receiver_phone"]),
            "buyer_name": str(r["buyer_name"]),
            "buyer_phone": str(r["buyer_phone"]),
            "address": str(r["address"]),
            "order_date": pd.to_datetime(r["order_date"], utc=True, errors="coerce").isoformat(),
            "product_order_nos": str(r["product_order_nos"]),
            "product_names": str(r["product_names"]),
            "total_quantity": int(r["total_quantity"]),
            "total_amount": int(r["total_amount"]),
            "source_files": str(r["source_files"]),
            "raw_rows": int(r["raw_rows"]),
            "updated_at": now,
        })

    # 같은 주문번호가 여러 파일에 중복 업로드돼도 DB 저장 전에 1개만 남김
    dedup = {}
    for rec in records:
        dedup[rec["order_key"]] = rec
    records = list(dedup.values())

    def save_chunk_safely(chunk):
        """큰 묶음 저장 실패 시 자동으로 반씩 쪼개 저장"""
        if not chunk:
            return 0

        try:
            sb.table("orders").upsert(chunk, on_conflict="order_key").execute()
            return len(chunk)
        except Exception as e:
            if len(chunk) <= 1:
                # 어떤 주문 1건 자체가 문제일 때만 화면에 명확히 표시
                raise RuntimeError(f"저장 실패 주문: {chunk[0].get('order_key')} / 원인: {e}")

            mid = len(chunk) // 2
            return save_chunk_safely(chunk[:mid]) + save_chunk_safely(chunk[mid:])

    # 기본은 1000건씩 시도, 실패하면 자동 분할
    chunk_size = 1000
    saved_count = 0

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        saved_count += save_chunk_safely(chunk)

    fetch_all.clear()
    return saved_count


def fetch_orders_as_order_level():
    df = fetch_all("orders")
    if df.empty:
        return df

    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df = df.rename(columns={
        "customer_key": "analysis_customer_key",
        "receiver_name": "receiver_name",
        "receiver_phone": "receiver_phone",
        "buyer_name": "buyer_name",
        "buyer_phone": "buyer_phone",
        "address": "address",
        "product_order_nos": "product_order_nos",
        "product_names": "product_names",
        "total_quantity": "total_quantity",
        "total_amount": "total_amount",
        "source_files": "source_files",
        "raw_rows": "raw_rows",
    })
    return df


def fetch_blacklist():
    df = fetch_all("blacklist")
    if df.empty:
        return pd.DataFrame(columns=["customer_key", "customer_name", "phone", "address", "status", "reason", "memo", "incident_date", "result", "updated_at"])
    return df


def save_blacklist(row):
    if sb is None:
        return

    row["updated_at"] = datetime.now().isoformat(timespec="seconds")
    sb.table("blacklist").upsert([row], on_conflict="customer_key").execute()
    fetch_all.clear()


def delete_blacklist(customer_key):
    if sb is None:
        return
    sb.table("blacklist").delete().eq("customer_key", customer_key).execute()
    fetch_all.clear()




def fetch_customer_notes():
    df = fetch_blacklist()
    if df.empty:
        return pd.DataFrame(columns=["customer_key", "memo", "updated_at"])
    notes = df[df.get("reason", "") == "고객메모"].copy() if "reason" in df.columns else pd.DataFrame()
    if notes.empty:
        return pd.DataFrame(columns=["customer_key", "memo", "updated_at"])
    return notes[["customer_key", "memo", "updated_at"]].copy()


def save_customer_note(customer_key, customer_name, phone, address, memo):
    if sb is None:
        return
    row = {
        "customer_key": str(customer_key),
        "customer_name": str(customer_name),
        "phone": str(phone),
        "address": str(address),
        "status": "메모",
        "reason": "고객메모",
        "memo": str(memo),
        "incident_date": str(date.today()),
        "result": "",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    sb.table("blacklist").upsert([row], on_conflict="customer_key").execute()
    fetch_all.clear()


@st.cache_data(ttl=300, max_entries=3, show_spinner=False)
def to_excel_bytes(sheets):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe_df = df.copy()
            # Excel은 timezone-aware datetime을 저장하지 못하므로 timezone 제거
            for col in safe_df.columns:
                if pd.api.types.is_datetime64_any_dtype(safe_df[col]):
                    try:
                        safe_df[col] = safe_df[col].dt.tz_localize(None)
                    except Exception:
                        safe_df[col] = pd.to_datetime(safe_df[col], errors="coerce", utc=True).dt.tz_localize(None)
                elif safe_df[col].dtype == "object":
                    # 문자열 안에 섞인 UTC datetime도 안전하게 문자열 처리
                    safe_df[col] = safe_df[col].apply(lambda x: x.isoformat() if hasattr(x, "isoformat") else x)
            safe_df.to_excel(writer, index=False, sheet_name=name[:31])
    output.seek(0)
    return output.getvalue()




def analyze_today_orders(order_preview, orders_db, customer_df, black_df):
    """업로드한 주문을 DB 저장 전 상태에서 기존 DB와 비교"""
    if order_preview is None or order_preview.empty:
        return pd.DataFrame(), pd.DataFrame()

    today_orders = order_preview.copy()
    today_orders["order_date"] = pd.to_datetime(today_orders["order_date"], utc=True, errors="coerce")

    if customer_df is None or customer_df.empty:
        existing = pd.DataFrame(columns=[
            "analysis_customer_key", "order_count", "first_order_date", "last_order_date",
            "grade", "days_since_last_order", "total_amount", "avg_order_amount"
        ])
    else:
        need_cols = [
            "analysis_customer_key", "order_count", "first_order_date", "last_order_date",
            "grade", "days_since_last_order", "total_amount", "avg_order_amount"
        ]
        existing = customer_df.copy()
        for c in need_cols:
            if c not in existing.columns:
                existing[c] = None
        existing = existing[need_cols]

    today_customer = (
        today_orders.groupby("analysis_customer_key", dropna=False)
        .agg(
            오늘고객명=("receiver_name", "first"),
            오늘전화번호=("receiver_phone", "first"),
            오늘주소=("address", "first"),
            오늘주문수=("order_key", pd.Series.nunique),
            오늘상품=("product_names", join_unique),
            오늘수량=("total_quantity", "sum"),
            오늘금액=("total_amount", "sum"),
            오늘채널=("channel", join_unique),
            오늘첫주문일=("order_date", "min"),
            오늘주문번호=("order_no", join_unique),
        )
        .reset_index()
    )

    result = today_customer.merge(existing, on="analysis_customer_key", how="left")
    result["기존주문횟수"] = result["order_count"].fillna(0).astype(int)
    result["이번포함총주문"] = result["기존주문횟수"] + result["오늘주문수"].fillna(0).astype(int)
    result["첫주문일"] = result["first_order_date"]
    result["최근주문일"] = result["last_order_date"]

    def status_row(r):
        old_count = int(r["기존주문횟수"])
        old_grade = str(r.get("grade", ""))
        days = r.get("days_since_last_order", None)

        if old_count <= 0:
            return "⚪ 신규"
        if old_grade == "VIP" or old_count >= 5:
            return "🟡 VIP 재주문"
        try:
            if pd.notna(days) and int(days) >= 90:
                return "🔵 복귀 재주문"
        except Exception:
            pass
        return "🟢 재주문"

    result["오늘고객상태"] = result.apply(status_row, axis=1)

    if black_df is not None and not black_df.empty:
        b = black_df.copy()
        for c in ["customer_key", "status", "reason", "memo", "incident_date", "result"]:
            if c not in b.columns:
                b[c] = ""
        b = b[["customer_key", "status", "reason", "memo", "incident_date", "result"]]
        result = result.merge(b, left_on="analysis_customer_key", right_on="customer_key", how="left")
    else:
        result["status"] = ""
        result["reason"] = ""
        result["memo"] = ""
        result["incident_date"] = ""
        result["result"] = ""

    result["블랙상태"] = result["status"].fillna("정상").replace("", "정상")
    result.loc[result["블랙상태"].isin(["주의", "블랙"]), "오늘고객상태"] = "🔴 주의/블랙"

    final_cols = [
        "오늘고객상태", "오늘고객명", "오늘전화번호", "오늘채널", "오늘상품",
        "오늘주문수", "기존주문횟수", "이번포함총주문",
        "첫주문일", "최근주문일", "days_since_last_order",
        "오늘금액", "오늘수량", "블랙상태", "reason", "memo", "result",
        "오늘주소", "오늘주문번호", "analysis_customer_key"
    ]

    for c in final_cols:
        if c not in result.columns:
            result[c] = ""

    result = result[final_cols].rename(columns={
        "days_since_last_order": "최근구매후경과일",
        "reason": "블랙사유",
        "memo": "블랙메모",
        "result": "처리결과",
        "analysis_customer_key": "고객키",
    })

    result = result.sort_values(
        by=["오늘고객상태", "이번포함총주문", "오늘금액"],
        ascending=[True, False, False]
    )

    detail = today_orders.merge(
        result[["고객키", "오늘고객상태", "기존주문횟수", "이번포함총주문", "블랙상태", "블랙사유"]],
        left_on="analysis_customer_key",
        right_on="고객키",
        how="left"
    )

    return result, detail



def style_customer_crm_table(df):
    if df is None or df.empty:
        return df

    def row_style(row):
        black = str(row.get("black_status", row.get("status", "")))
        grade_val = str(row.get("grade", ""))
        order_count = int(row.get("order_count", 0)) if pd.notna(row.get("order_count", 0)) else 0

        if black == "블랙":
            return ["background-color: #000000; color: #ffffff; font-weight: 800"] * len(row)
        if black == "주의":
            return ["background-color: #fee2e2; color: #111827; font-weight: 600"] * len(row)
        if grade_val == "VIP" or order_count >= 5:
            return ["background-color: #fef3c7; color: #111827; font-weight: 700"] * len(row)
        if order_count >= 2:
            return ["background-color: #ffedd5; color: #111827; font-weight: 600"] * len(row)
        return ["background-color: #dcfce7; color: #111827; font-weight: 600"] * len(row)

    return df.style.apply(row_style, axis=1)

def style_today_customer_table(df):
    """오늘 주문 분석 표 색상"""
    if df is None or df.empty:
        return df

    def row_style(row):
        status = str(row.get("오늘고객상태", ""))
        black = str(row.get("블랙상태", ""))

        if "🔴" in status or black in ["주의", "블랙"]:
            return ["background-color: #fee2e2; color: #111827; font-weight: 600"] * len(row)
        if "🟡" in status:
            return ["background-color: #fef3c7; color: #111827; font-weight: 700"] * len(row)
        if "🔵" in status:
            return ["background-color: #dbeafe"] * len(row)
        if "🟢" in status:
            return ["background-color: #dcfce7; color: #111827; font-weight: 600"] * len(row)
        return [""] * len(row)

    return df.style.apply(row_style, axis=1)


def make_ai_context(customer_df, orders_db):
    """AI에게 넘길 CRM 요약. 개인정보 보호를 위해 이름/전화번호/주소는 전송하지 않음."""
    if customer_df is None or customer_df.empty:
        return "저장된 고객 데이터가 없습니다."

    total_orders = len(orders_db) if orders_db is not None else 0
    total_customers = len(customer_df)

    repeat_customers = int((customer_df["order_count"] >= 2).sum()) if "order_count" in customer_df.columns else 0
    vip_customers = int((customer_df["order_count"] >= 5).sum()) if "order_count" in customer_df.columns else 0
    repeat_rate = round(repeat_customers / total_customers * 100, 1) if total_customers else 0

    one_time = int((customer_df["order_count"] == 1).sum()) if "order_count" in customer_df.columns else 0
    two_time = int((customer_df["order_count"] == 2).sum()) if "order_count" in customer_df.columns else 0
    three_plus = int((customer_df["order_count"] >= 3).sum()) if "order_count" in customer_df.columns else 0

    if "order_count" in customer_df.columns:
        top_order_counts = customer_df["order_count"].value_counts().sort_index().head(20).to_dict()
    else:
        top_order_counts = {}

    product_text = ""
    if orders_db is not None and not orders_db.empty and "product_names" in orders_db.columns:
        product_counts = orders_db["product_names"].astype(str).value_counts().head(10)
        product_text = "\n".join([f"- {idx}: {val}건" for idx, val in product_counts.items()])

    monthly_text = ""
    if orders_db is not None and not orders_db.empty and "order_date" in orders_db.columns:
        temp = orders_db.copy()
        temp["월"] = pd.to_datetime(temp["order_date"], errors="coerce", utc=True).dt.to_period("M").astype(str)
        monthly = temp.groupby("월").size().tail(12)
        monthly_text = "\n".join([f"- {idx}: {val}건" for idx, val in monthly.items()])

    return f"""
식혜명가 CRM 집계 요약:
- 누적 주문수: {total_orders:,}건
- 누적 고객수: {total_customers:,}명
- 1회 구매 고객수: {one_time:,}명
- 2회 구매 고객수: {two_time:,}명
- 3회 이상 구매 고객수: {three_plus:,}명
- 재구매 고객수: {repeat_customers:,}명
- 재구매율: {repeat_rate}%
- VIP 고객수(5회 이상): {vip_customers:,}명

구매횟수 분포:
{top_order_counts}

최근 12개월 주문수:
{monthly_text}

주요 상품 빈도:
{product_text}

주의:
- 이 요약에는 고객명, 전화번호, 주소 등 개인정보를 포함하지 않는다.
- 답변도 개인정보 없이 집계와 전략 중심으로 한다.
"""


def auto_ai_crm_analysis(customer_df, orders_db):
    """버튼 한 번으로 CRM 자동 분석"""
    question = """
현재 CRM 데이터를 바탕으로 아래 항목을 실무적으로 분석해줘.

1. 현재 고객 구조 요약
2. 재구매율 상태 평가
3. VIP 고객 관리 포인트
4. 신규 고객을 재구매로 전환하기 위한 전략
5. 당장 실행할 마케팅 액션 TOP 5
6. 문자/쿠폰을 보낸다면 어떤 고객군을 우선해야 하는지
7. 사장님이 이번 주에 확인해야 할 체크리스트

답변은 너무 길지 않게, 바로 실행 가능한 형태로 정리해줘.
"""
    return ask_ai_crm(question, customer_df, orders_db)


def _ai_settings():
    """AI 설정 진단. 키는 UI/로그에 절대 표시하지 않음."""
    preferred = str(st.secrets.get("AI_PROVIDER", "")).strip().lower()
    gemini_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    openai_key = str(st.secrets.get("OPENAI_API_KEY", "")).strip()

    # 과거 버전은 AI_PROVIDER를 생략하면 OpenAI로 고정돼 Gemini 키가 무시됐음.
    if preferred not in ("gemini", "openai"):
        preferred = "gemini" if gemini_key else "openai"
    if preferred == "openai" and not openai_key and gemini_key:
        preferred = "gemini"
    if preferred == "gemini" and not gemini_key and openai_key:
        preferred = "openai"

    if preferred == "gemini":
        configured_model = str(st.secrets.get("GEMINI_MODEL", "")).strip()
        retired = {
            "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash",
            "gemini-2.0-flash-001", "gemini-2.0-flash-lite",
            "gemini-2.0-flash-lite-001", "gemini-1.5-flash-002",
        }
        # 2026-10 현행 안정 모델. 기존 중단 모델 설정은 자동 대체.
        model = "gemini-3.5-flash-lite" if not configured_model or configured_model in retired else configured_model
        switched = configured_model in retired
        return {"provider": "gemini", "key": gemini_key, "model": model,
                "ready": bool(gemini_key), "switched": switched}

    return {"provider": "openai", "key": openai_key,
            "model": str(st.secrets.get("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini",
            "ready": bool(openai_key), "switched": False}


def _safe_ai_error(response, provider):
    """서비스의 원본 오류 본문에는 계정정보가 있을 수 있으므로 그대로 출력하지 않음."""
    status = response.status_code
    if status in (401, 403):
        detail = "API 키가 유효한지, 해당 모델을 사용할 권한이 있는지 확인해 주세요."
    elif status == 404:
        detail = "모델을 찾을 수 없습니다. Streamlit Secrets의 모델명을 확인해 주세요."
    elif status == 429:
        detail = "API 요청 한도 또는 사용량 제한에 걸렸습니다. 사용량/결제 설정을 확인해 주세요."
    elif status == 400:
        detail = "요청 또는 모델 설정이 맞지 않습니다. 모델명을 확인해 주세요."
    elif status >= 500:
        detail = "AI 서비스 쪽 서버 문제가 발생했습니다. 잠시 후 재시도해 주세요."
    else:
        detail = "호출에 실패했습니다. API 설정과 네트워크 상태를 확인해 주세요."
    return f"⚠️ {provider} API 오류 (HTTP {status}): {detail}"


def ask_ai_crm(question, customer_df, orders_db):
    """Gemini/OpenAI 집계 기반 분석. 키 선택, 예외 처리, 결과 상태를 명확하게 함."""
    config = _ai_settings()
    if not config["ready"]:
        return "⚠️ AI 연결 키가 없습니다. Streamlit Secrets에 GEMINI_API_KEY 또는 OPENAI_API_KEY를 설정해 주세요."

    context = make_ai_context(customer_df, orders_db)
    system_prompt = (
        "너는 식혜 온라인 판매자의 CRM 분석 비서다. 한국어로 짧고 실무적으로 답하라. "
        "고객 이름, 전화번호, 주소 등 개인정보는 출력하지 말고, "
        "제공된 집계 수치만 활용하며 근거 없는 정밀 예측을 하지 마라."
    )
    try:
        if config["provider"] == "gemini":
            # 키를 URL 쿼리 파라미터에 넣지 않고 헤더로 전송 (로그 유출 최소화)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{config['model']}:generateContent"
            headers = {"x-goog-api-key": config["key"], "Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": system_prompt + "\n\n" + context + "\n\n사용자 질문: " + question}]}]}
            res = requests.post(url, headers=headers, json=payload, timeout=55)
            if res.status_code >= 400:
                return _safe_ai_error(res, "Gemini")
            data = res.json()
            chunks = [p.get("text", "") for c in data.get("candidates", [])
                      for p in c.get("content", {}).get("parts", []) if isinstance(p, dict)]
            answer = "\n".join(chunks).strip()
            if answer:
                return answer
            return "⚠️ Gemini가 텍스트를 반환하지 않았습니다. 다시 실행하거나 모델 설정을 확인해 주세요."

        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {config['key']}", "Content-Type": "application/json"}
        payload = {"model": config["model"], "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context + "\n\n질문: " + question}
        ]}
        res = requests.post(url, headers=headers, json=payload, timeout=55)
        if res.status_code >= 400:
            return _safe_ai_error(res, "OpenAI")
        data = res.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content") or "⚠️ AI 응답이 비어 있습니다."
    except requests.exceptions.Timeout:
        return "⚠️ AI 서버 응답 시간이 초과됐습니다. 잠시 후 다시 실행해 주세요."
    except requests.exceptions.RequestException:
        return "⚠️ AI 서버에 연결하지 못했습니다. 네트워크 또는 서비스 상태를 확인해 주세요."
    except (ValueError, KeyError, TypeError, IndexError):
        return "⚠️ AI 응답을 읽는 중 문제가 생겼습니다. 모델 설정을 확인해 주세요."


def ai_status_line():
    config = _ai_settings()
    if not config["ready"]:
        st.warning("AI API 키가 없습니다. Streamlit Secrets에 GEMINI_API_KEY 또는 OPENAI_API_KEY가 필요합니다.")
        return False
    provider_label = "Gemini" if config["provider"] == "gemini" else "OpenAI"
    st.caption(f"연결 설정: {provider_label} · {config['model']} · API 키 등록됨 (실제 호출 성공 여부는 분석 실행 시 확인)")
    if config["switched"]:
        st.info("기존 GEMINI_MODEL에 종료된 모델이 설정돼 있어 지원되는 기본 모델로 자동 전환했습니다.")
    return True



def infer_shipping_item(product_name, channel=""):
    text = str(product_name).strip()
    channel = str(channel)

    if channel == "네이버":
        m_opt = re.search(r'용량\s*:\s*(.*)', text)
        if m_opt:
            text = m_opt.group(1).strip()

    unit_count = 1
    m = re.search(r'(\d+)\s*(개입|개|병|팩|입)', text)
    if m:
        try:
            unit_count = int(m.group(1))
        except Exception:
            unit_count = 1

    if channel == "쿠팡":
        m2 = re.search(r'(?:1\s*L|1리터|1000\s*ml|1000\s*ML).*?(\d+)\s*(개|병|팩)', text, flags=re.I)
        if m2:
            unit_count = int(m2.group(1))
        m3 = re.search(r'(\d+)\s*(개|병|팩).*?(?:1\s*L|1리터|1000\s*ml|1000\s*ML)', text, flags=re.I)
        if m3:
            unit_count = int(m3.group(1))

    if re.search(r'200\s*ML|200\s*ml|200미리|200', text):
        size = "200ml"
    elif re.search(r'500\s*ML|500\s*ml|500미리|500', text):
        size = "500ml"
    elif re.search(r'1\s*L|1리터|1ℓ|1000\s*ML|1000\s*ml', text, flags=re.I):
        size = "1L"
    else:
        size = "기타"

    kind = "단호박식혜" if ("단호박" in text or "호박" in text) else "식혜"
    return f"{kind} {size}", unit_count


def make_shipping_line_items(raw_orders):
    if raw_orders is None or raw_orders.empty:
        return pd.DataFrame(columns=["품목", "채널", "상품명", "주문수량", "개입수", "실제출고수량", "주문일"])

    rows = []
    for _, r in raw_orders.iterrows():
        product = str(r.get("product_name", ""))
        channel = str(r.get("channel", ""))
        qty = int(r.get("quantity", 0)) if pd.notna(r.get("quantity", 0)) else 0
        item, unit_count = infer_shipping_item(product, channel)
        rows.append({
            "품목": item,
            "채널": channel,
            "상품명": product,
            "주문수량": qty,
            "개입수": unit_count,
            "실제출고수량": qty * unit_count,
            "주문일": pd.to_datetime(r.get("order_date", pd.NaT), errors="coerce"),
        })
    return pd.DataFrame(rows)


def make_shipping_summary(raw_orders):
    line = make_shipping_line_items(raw_orders)
    if line.empty:
        return pd.DataFrame(columns=["품목", "실제출고수량", "주문수량", "상품종류수"])

    return (
        line.groupby("품목", dropna=False)
        .agg(
            실제출고수량=("실제출고수량", "sum"),
            주문수량=("주문수량", "sum"),
            상품종류수=("상품명", "nunique"),
        )
        .reset_index()
        .sort_values("실제출고수량", ascending=False)
    )


def make_weekly_shipping_table_from_orders(raw_orders):
    line = make_shipping_line_items(raw_orders)
    if line.empty:
        return pd.DataFrame(), pd.DataFrame()

    line = line.dropna(subset=["주문일"]).copy()
    if line.empty:
        return pd.DataFrame(), pd.DataFrame()

    line["주"] = line["주문일"].dt.to_period("W").astype(str)

    weekly = line.groupby(["주", "품목"], dropna=False)["실제출고수량"].sum().reset_index()
    pivot = weekly.pivot(index="주", columns="품목", values="실제출고수량").fillna(0).astype(int).reset_index()
    avg = weekly.groupby("품목")["실제출고수량"].mean().round(1).reset_index(name="주별평균출고수량")
    avg = avg.sort_values("주별평균출고수량", ascending=False)
    return pivot, avg


def make_weekly_shipping_average(orders_db, weeks=8):
    if orders_db is None or orders_db.empty:
        return pd.DataFrame(columns=["품목", "최근주간평균출고수량", "최근총출고수량", "분석주수"])

    df = orders_db.copy()
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df = df.dropna(subset=["order_date"])
    if df.empty:
        return pd.DataFrame(columns=["품목", "최근주간평균출고수량", "최근총출고수량", "분석주수"])

    max_date = df["order_date"].max()
    start_date = max_date - pd.Timedelta(weeks=weeks)
    df = df[df["order_date"] >= start_date]

    rows = []
    for _, r in df.iterrows():
        product = str(r.get("product_names", ""))
        channel = str(r.get("channel", ""))
        qty = int(r.get("total_quantity", 0)) if pd.notna(r.get("total_quantity", 0)) else 0
        item, unit_count = infer_shipping_item(product, channel)
        rows.append({"품목": item, "실제출고수량": qty * unit_count})

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["품목", "최근주간평균출고수량", "최근총출고수량", "분석주수"])

    summary = out.groupby("품목", dropna=False).agg(최근총출고수량=("실제출고수량", "sum")).reset_index()
    summary["분석주수"] = weeks
    summary["최근주간평균출고수량"] = (summary["최근총출고수량"] / weeks).round(1)
    return summary[["품목", "최근주간평균출고수량", "최근총출고수량", "분석주수"]].sort_values("최근주간평균출고수량", ascending=False)


# 같은 파일을 다시 렌더링할 때 복호화/엑셀 분석을 반복하지 않습니다.
@st.cache_data(ttl=900, max_entries=12, show_spinner=False)
def parse_uploaded_file_cached(filename, content):
    file_like = io.BytesIO(content)
    if filename.lower().endswith(".csv"):
        raw = pd.read_csv(file_like)
    else:
        raw = read_excel_file(file_like)
    market = detect_market(filename, raw)
    std = standardize(raw, market, filename)
    return std, market, len(raw)


# ===== 재고관리 통합 기능 (별도 모듈 필요 없음) =====
# 품목 코드는 저장 후 이름이 바뀌더라도 유지되는 키로 사용한다.
ITEMS = [
    ("sikhye_1l", "식혜 1L", 150, False),
    ("sikhye_500ml", "식혜 500ml", 100, True),
    ("sikhye_200ml", "식혜 200ml", 100, False),
    ("pumpkin_1l", "단호박식혜 1L", 60, False),
    ("pumpkin_500ml", "단호박식혜 500ml", 30, False),
]
KST = ZoneInfo("Asia/Seoul")
KEYS = [p[0] for p in ITEMS]
LABELS = {p[0]: p[1] for p in ITEMS}


def _safe_int(x):
    try:
        return max(0, int(x))
    except (ValueError, TypeError, OverflowError):
        return 0


def _is_low(key, remaining):
    limit, inclusive = next((p[2], p[3]) for p in ITEMS if p[0] == key)
    return remaining <= limit if inclusive else remaining < limit


def classify_label(label):
    s = str(label).lower().replace(" ", "")
    pumpkin = "단호박" in s or "호박" in s
    if "200ml" in s:
        return None if pumpkin else "sikhye_200ml"
    if "500ml" in s:
        return "pumpkin_500ml" if pumpkin else "sikhye_500ml"
    if "1l" in s or "1000ml" in s:
        return "pumpkin_1l" if pumpkin else "sikhye_1l"
    return None


def today_shipment(raw_orders, shipping_summary_func):
    """기존 쿠팡/네이버 수량 파서를 재사용해 출고량을 정확히 가져온다."""
    out = {key: 0 for key in KEYS}
    unknown = []
    if raw_orders is None or raw_orders.empty:
        return out, unknown
    shipping = shipping_summary_func(raw_orders)
    for _, r in shipping.iterrows():
        key = classify_label(r.get("품목", ""))
        if key:
            out[key] += _safe_int(r.get("실제출고수량"))
        else:
            unknown.append((str(r.get("품목", "기타")), _safe_int(r.get("실제출고수량"))))
    return out, unknown


def _get_db_client():
    """공개용 publishable key로 재고를 수정할 수 없도록 별도의 서버 비밀키 사용."""
    secret = st.secrets.get("INVENTORY_DB_KEY", "")
    url = st.secrets.get("SUPABASE_URL", "")
    if not secret or not url:
        return None
    if not (secret.startswith("sb_secret_") or secret.startswith("eyJ")):
        return None
    try:
        from supabase import create_client
        return create_client(url, secret)
    except Exception:
        return None


@st.cache_data(ttl=90, show_spinner=False)
def _read_inventory_data(url, secret, nonce=0):
    """캐시 키에는 비밀키가 포함되지만 UI에 출력하지 않는다."""
    from supabase import create_client
    client = create_client(url, secret)
    rows = []
    start = 0
    while True:
        result = client.table("inventory_daily").select("inventory_date,item_key,opening_qty,received_qty,auto_ship_qty,actual_ship_qty,closing_qty,note,updated_at").order("inventory_date", desc=True).range(start, start + 999).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start += 1000
    return rows


def fetch_inventory_rows():
    secret = st.secrets.get("INVENTORY_DB_KEY", "")
    url = st.secrets.get("SUPABASE_URL", "")
    if not secret or not url:
        return [], "DB 저장 준비 중: Streamlit Secrets에 INVENTORY_DB_KEY를 추가해주세요."
    try:
        return _read_inventory_data(url, secret), ""
    except Exception as exc:
        # DB 테이블 미생성, 네트워크 오류 등을 앱 전체 장애로 확대하지 않는다.
        return [], f"재고 DB를 불러오지 못했습니다. inventory_schema.sql 적용 여부와 DB 연결을 확인하세요. ({type(exc).__name__})"


def previous_inventory(rows, as_of):
    prev = {}
    for r in rows:
        try:
            d = date.fromisoformat(str(r["inventory_date"])[:10])
            key = r["item_key"]
            if d < as_of and key in KEYS and (key not in prev or d > prev[key][0]):
                prev[key] = (d, _safe_int(r["closing_qty"]))
        except (KeyError, ValueError, TypeError):
            pass
    return prev


def existing_today(rows, as_of):
    return {
        str(r.get("item_key")): r
        for r in rows if str(r.get("inventory_date"))[:10] == as_of.isoformat()
    }


# 카카오톡에서 글꼴 폭이 달라도 보기 좋도록 공백 정렬 대신 한 줄씩 구성.
# 칠판에 옮겨 적기 쉽도록 단위 '개', 긴 품목명, 요약 경고를 제외한다.
COPY_NAMES = {
    "sikhye_1l": "1L",
    "sikhye_500ml": "500ML",
    "sikhye_200ml": "200ML",
    "pumpkin_1l": "단호박 1L",
    "pumpkin_500ml": "단호박 500ML",
}


def make_message(as_of, rows, compact=False):
    header = f"📦 재고 ({as_of:%m/%d})" if compact else f"📦 출고 / 재고 ({as_of:%m/%d})"
    lines = [header, ""]
    # 저장된 records에 같은 품목이 없으면 생략하고, 품목 순서는 고정한다.
    by_key = {r["item_key"]: r for r in rows}
    for key in KEYS:
        r = by_key.get(key)
        if r is None:
            continue
        name = COPY_NAMES[key]
        warning = "   ⚠️" if _is_low(key, r["closing_qty"]) else ""
        if compact:
            lines.append(f"{name}: {r['closing_qty']:,}{warning}")
        else:
            lines.append(f"{name}: 출고 {r['actual_ship_qty']:,} / 재고 {r['closing_qty']:,}{warning}")
    return "\n".join(lines)


def render_oneclick_copy_button(message, label, button_id, accent=False):
    """한 번 클릭하면 실제 클립보드에 복사 (Streamlit 1.56 st.html JS 지원).

    복사 텍스트는 숫자/품목 이름으로 만든 값을 JSON으로 직렬화하며
    HTML 태그나 스크립트로 해석되지 않도록 특수문자를 이스케이프한다.
    """
    # 비신뢰 데이터가 JS 문자열 경계를 벗어나지 않도록 < 등 이스케이프.
    payload = json.dumps(message, ensure_ascii=False).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
    button_text = json.dumps(label, ensure_ascii=False)
    tone = '#eaf7ee' if accent else '#f7f8fa'
    border = '#89c7a0' if accent else '#c9cdd3'
    markup = f"""
    <div class="inventory-copy-root" id="{button_id}">
      <button class="inventory-copy-button" type="button" aria-label={label}>
        <span class="copy-label"></span>
      </button>
      <span class="copy-status" aria-live="polite"></span>
    </div>
    <style>
      #{button_id} {{display:flex; align-items:center; gap:6px; width:100%; font-family:inherit;}}
      #{button_id} .inventory-copy-button {{cursor:pointer; font-family:inherit; font-size:13px; font-weight:600; line-height:1.3;
        box-sizing:border-box; width:100%; min-height:37px; padding:8px 6px; border-radius:8px;
        background:{tone}; color:#173023; border:1px solid {border}; white-space:nowrap;}}
      #{button_id} .inventory-copy-button:hover {{filter:brightness(.97)}}
      #{button_id} .inventory-copy-button:focus-visible {{outline:2px solid #2a8a5b; outline-offset:2px}}
      #{button_id} .copy-status {{font-size:11px; white-space:nowrap; color:#ad2222;}}
    </style>
    <script>
      (() => {{
        const root = document.getElementById({json.dumps(button_id)});
        if (!root) return;
        const button = root.querySelector('button');
        const label = root.querySelector('.copy-label');
        const status = root.querySelector('.copy-status');
        const originalLabel = {button_text};
        const copyValue = {payload};
        label.textContent = originalLabel;
        // Streamlit 재렌더링 시 최신 문구로 이벤트를 덮어쓴다.
        let resetTimer;
        function fallbackCopy(text) {{
          const node = document.createElement('textarea');
          node.value = text;
          node.setAttribute('readonly', '');
          node.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
          document.body.appendChild(node);
          node.focus();
          node.select();
          try {{ return document.execCommand('copy'); }}
          finally {{ node.remove(); }}
        }}
        button.onclick = async () => {{
          let ok = false;
          try {{
            if (navigator.clipboard && window.isSecureContext) {{
              await navigator.clipboard.writeText(copyValue);
              ok = true;
            }} else {{ ok = fallbackCopy(copyValue); }}
          }} catch (error) {{
            try {{ ok = fallbackCopy(copyValue); }} catch (_) {{ ok = false; }}
          }}
          clearTimeout(resetTimer);
          label.textContent = ok ? '✅ 복사 완료!' : originalLabel;
          status.textContent = ok ? '' : '복사 불가';
          resetTimer = setTimeout(() => {{ label.textContent = originalLabel; status.textContent = ''; }}, 1500);
        }};
      }})();
    </script>
    """
    st.html(markup, width="stretch", unsafe_allow_javascript=True)


def snapshots_weekly(rows, weeks=12, as_of=None):
    """날짜별 스냅샷을 동일 주·품목으로 합산. 기록한 날짜 수 함께 제공."""
    if as_of is None:
        as_of = datetime.now(KST).date()
    current_week = as_of - timedelta(days=as_of.weekday())
    start_week = current_week - timedelta(weeks=weeks - 1)
    data = []
    for r in rows:
        try:
            d = date.fromisoformat(str(r.get("inventory_date", ""))[:10])
            if start_week <= d <= as_of and d.weekday() < 5 and r.get("item_key") in KEYS:
                start = d - timedelta(days=d.weekday())
                data.append({"주": start.isoformat(), "품목": LABELS[r["item_key"]], "출고수량": _safe_int(r.get("actual_ship_qty")), "날짜": d.isoformat()})
        except ValueError:
            continue
    if not data:
        return pd.DataFrame(), pd.DataFrame()
    df = pd.DataFrame(data)
    weekly = df.groupby(["주", "품목"], as_index=False).agg(출고수량=("출고수량", "sum"), 기록일수=("날짜", "nunique"))
    # 평일 5일 기록을 모두 남긴 주만 평균 산출한다. 미기록일은 0출고로 취급하지 않는다.
    completed = weekly[weekly["기록일수"] >= 5]
    avg = (completed.groupby("품목")["출고수량"].agg(["mean", "count"])
           .reset_index().rename(columns={"mean": "완전한_주간_평균", "count": "분석주수"})) if not completed.empty else pd.DataFrame()
    return weekly, avg


def _order_dates_kst(orders_db):
    """주문 시각을 한국 날짜로 통일한다. 기존 주문 테이블은 UTC ISO 문자열을 저장한다."""
    return pd.to_datetime(orders_db["order_date"], utc=True, errors="coerce").dt.tz_convert(KST).dt.date


def historical_weekday_report(orders_db, as_of, infer_fn):
    """작년 같은 ISO주 월~금: 주문 건수(정확)와 단일 상품 주문의 식별 가능한 병수(부분 집계).

    비교 평균: 동일 주를 포함한 작년 직전 4주간 월~금의 평균. 주문 기록이
    존재하는 주만 평균 대상으로 하며, 없는 주를 0으로 취급하지 않는다.
    """
    iso = as_of.isocalendar()
    try:
        monday = date.fromisocalendar(iso.year - 1, iso.week, 1)
    except ValueError:
        # ISO 53주가 직전 연도에 없다면 52주로 조정하고 화면에 기간을 명시한다.
        monday = date.fromisocalendar(iso.year - 1, 52, 1)
    days = [monday + timedelta(days=i) for i in range(5)]
    week_starts = [monday - timedelta(weeks=i) for i in range(3, -1, -1)]
    empty_day = {d: {"orders": 0, "eligible": 0, "qty": {k: 0 for k in KEYS}} for d in days}
    result = {
        "days": days, "monday": monday, "daily": empty_day,
        "weekly_4": {}, "4week_coverage": 0,
        "total_orders": 0, "eligible": 0,
        "qty": {k: 0 for k in KEYS}, "average_orders_4w": None,
        "average_qty_4w": {k: None for k in KEYS},
    }
    if orders_db is None or orders_db.empty or "order_date" not in orders_db.columns:
        return result
    df = orders_db.copy()
    df["_local_date"] = _order_dates_kst(df)
    # 전체 수년치 주문에서 날짜별 상품을 모두 분석하지 말고 필요한 4주치만 처리한다.
    first_day = week_starts[0]
    last_day = days[-1]
    df = df[df["_local_date"].between(first_day, last_day)].copy()
    if df.empty:
        return result
    # 하나의 주문이 하나의 원본 상품행인 경우에 한해 품목과 구성 병수를 추정한다.
    df["_single"] = pd.to_numeric(df.get("raw_rows", pd.Series(index=df.index, dtype="float64")), errors="coerce").eq(1)
    df["_qty"] = pd.to_numeric(df.get("total_quantity", pd.Series(index=df.index, dtype="float64")), errors="coerce").fillna(0)
    df["_item"] = None
    df["_units"] = 0
    valid = df["_single"] & df["_qty"].gt(0)
    for idx, row in df.loc[valid].iterrows():
        name = str(row.get("product_names", ""))
        if not name or name.lower() == "nan":
            continue
        item_name, pack_units = infer_fn(name, str(row.get("channel", "")))
        key = classify_label(item_name)
        if key and _safe_int(pack_units) > 0:
            df.at[idx, "_item"] = key
            df.at[idx, "_units"] = _safe_int(pack_units)
    # 데이터를 갖고 있는 4주만 계산. 미기록은 영업일 0출고가 아니다.
    for monday_i in week_starts:
        weekly_days = [monday_i + timedelta(days=i) for i in range(5)]
        frame = df[df["_local_date"].isin(weekly_days)]
        if frame.empty:
            continue
        counts = {k: 0 for k in KEYS}
        recognized = frame[frame["_item"].isin(KEYS)]
        for _, row in recognized.iterrows():
            counts[row["_item"]] += _safe_int(row["_qty"] * row["_units"])
        result["weekly_4"][monday_i] = {"orders": len(frame), "eligible": len(recognized), "qty": counts}
    result["4week_coverage"] = len(result["weekly_4"])
    if result["4week_coverage"]:
        n = result["4week_coverage"]
        result["average_orders_4w"] = sum(x["orders"] for x in result["weekly_4"].values()) / n
        for key in KEYS:
            result["average_qty_4w"][key] = sum(x["qty"][key] for x in result["weekly_4"].values()) / n
    for d in days:
        frame = df[df["_local_date"] == d]
        result["daily"][d]["orders"] = len(frame)
        recognized = frame[frame["_item"].isin(KEYS)]
        result["daily"][d]["eligible"] = len(recognized)
        for _, row in recognized.iterrows():
            key = row["_item"]
            q = _safe_int(row["_qty"] * row["_units"])
            result["daily"][d]["qty"][key] += q
            result["qty"][key] += q
        result["total_orders"] += len(frame)
        result["eligible"] += len(recognized)
    return result


def render_historical_production_report(orders_db, as_of, infer_fn):
    """작년 월~금 주문/품목별 식별 가능한 수량과 주간 평균을 바로 보여준다."""
    report = historical_weekday_report(orders_db, as_of, infer_fn)
    days = report["days"]
    monday = report["monday"]
    friday = days[-1]
    st.markdown("### 📅 작년 같은 주 월~금 출고 비교")
    st.caption(f"대상 기간: **{monday:%Y.%m.%d}(월) ~ {friday:%m.%d}(금)**  |  주문일 기준  |  날짜별·품목별 비교")
    d_cols = st.columns(3)
    d_cols[0].metric("작년 월~금 주문", f"{report['total_orders']:,}건")
    d_cols[1].metric("작년 하루 평균 주문", f"{report['total_orders']/5:,.1f}건")
    avg_orders = report["average_orders_4w"]
    d_cols[2].metric("작년 인접 4주 월~금 평균", f"{avg_orders:,.1f}건" if avg_orders is not None else "자료 없음")
    if report["total_orders"] == 0:
        st.info("작년 해당 월~금에 저장된 주문이 없습니다. DB에 그 기간 주문이 들어있는지 확인해주세요. 기록이 없다고 실제 출고가 0개였던 것은 아닙니다.")
    n_weeks = report["4week_coverage"]
    if n_weeks < 4:
        st.caption(f"작년 같은 주와 직전 3주 중 주문 기록이 확인되는 기간: **{n_weeks}/4주**. 미기록 주를 0으로 처리하지 않습니다.")
    st.markdown("**품목별 월~금 수량 비교**")
    labels = ["월", "화", "수", "목", "금"]
    rows = []
    for key, label, _, _ in ITEMS:
        avg = report["average_qty_4w"][key]
        row = {"품목": label}
        for d, day_label in zip(days, labels):
            row[f"{day_label} {d:%m/%d}"] = report["daily"][d]["qty"][key] if report["total_orders"] else "—"
        row["5일 합계"] = report["qty"][key] if report["total_orders"] else "—"
        row["하루 평균"] = round(report["qty"][key] / 5, 1) if report["total_orders"] else "—"
        row["인접 주간 평균"] = round(avg, 1) if avg is not None else "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(
        f"⚠️ 위의 품목 수량은 **단일상품 주문 {report['eligible']:,}건 / 해당 주 전체 {report['total_orders']:,}건**을 이용해 계산한 "
        "**확인 가능한 부분 수량**입니다. 혼합 주문과 택배 외 출고는 누락될 수 있어 실제 전체 출고량과 다릅니다. "
        f"'인접 주간 평균'은 작년 해당 주와 그 이전 3주 중 기록이 있는 {n_weeks}주의 월~금 평균입니다. "
        "정확한 생산량 판단에는 과거 원본 상품별 주문 엑셀이 필요합니다."
    )
    if report["total_orders"] > 0:
        day_orders = "  |  ".join(
            f"{weekday} {report['daily'][day]['orders']:,}건"
            for day, weekday in zip(days, labels)
        )
        st.caption("📋 작년 요일별 주문 건수: " + day_orders)


def _recorded_inventory_calendar(rows):
    """확정 저장된 실출고 스냅샷만 날짜별로 묶는다. 미기록일은 0과 구분한다."""
    calendar = {}
    for row in rows:
        try:
            day = date.fromisoformat(str(row.get("inventory_date", ""))[:10])
            key = row.get("item_key")
            if key not in KEYS:
                continue
            calendar.setdefault(day, {})[key] = _safe_int(row.get("actual_ship_qty"))
        except (ValueError, TypeError):
            pass
    return calendar


def _week_snapshot(calendar, monday):
    """품목별 월~금 실출고 및 기록 현황. 미기록일은 None; 0은 실제 0개."""
    days = [monday + timedelta(days=i) for i in range(5)]
    complete_days = [d for d in days if all(k in calendar.get(d, {}) for k in KEYS)]
    result = {}
    for key in KEYS:
        quantities = [calendar.get(d, {}).get(key) for d in days]
        result[key] = {
            "daily": quantities,
            "recorded": sum(q is not None for q in quantities),
            "partial": sum(q for q in quantities if q is not None),
            "total": sum(quantities) if all(q is not None for q in quantities) else None,
        }
    return {"days": days, "complete_days": len(complete_days), "items": result}


def _prior_year_monday(as_of):
    iso = as_of.isocalendar()
    try:
        return date.fromisocalendar(iso.year - 1, iso.week, 1)
    except ValueError:
        # ISO 53주가 전년에 없다면 52주를 참조한다.
        return date.fromisocalendar(iso.year - 1, 52, 1)


def _completed_week_average(calendar, anchor_monday, count=4):
    """기준 주 이전 count주만 비교. 5일 모두 기록된 주만 평균에 포함."""
    completed = []
    for i in range(count, 0, -1):
        monday = anchor_monday - timedelta(weeks=i)
        week = _week_snapshot(calendar, monday)
        if week["complete_days"] == 5:
            completed.append(week)
    if not completed:
        return {k: None for k in KEYS}, 0
    return {
        k: sum(w["items"][k]["total"] for w in completed) / len(completed)
        for k in KEYS
    }, len(completed)


def render_verified_inventory_history(history_rows, as_of):
    """내년에는 작년 같은 ISO주 실제 월~금 기록으로 바뀌는 비교 영역."""
    calendar = _recorded_inventory_calendar(history_rows)
    recorded_days = sorted(d for d, values in calendar.items() if all(k in values for k in KEYS))
    this_monday = as_of - timedelta(days=as_of.weekday())
    last_monday = _prior_year_monday(as_of)
    current = _week_snapshot(calendar, this_monday)
    prior = _week_snapshot(calendar, last_monday)
    prev_avg, prev_count = _completed_week_average(calendar, this_monday, count=4)
    last_avg, last_count = _completed_week_average(calendar, last_monday, count=4)

    st.markdown("### 📆 실제 출고 기록 · 주간 생산 참고")
    st.caption("주문 DB 추정치가 아니라, **재고관리에서 최종 저장한 '오늘 출고'** 수량만 사용합니다. 월~금 기준입니다.")
    cols = st.columns(3)
    cols[0].metric("출고 기록한 날짜", f"{len(recorded_days):,}일")
    cols[1].metric("이번 주 기록", f"{current['complete_days']}/5일")
    cols[2].metric("최근 4주 월~금 평균", f"{prev_count}/4주 확보")
    if recorded_days:
        st.caption(f"기록 시작 **{recorded_days[0]:%Y.%m.%d}** · 마지막 저장 **{recorded_days[-1]:%Y.%m.%d}** · 미기록일은 출고 0개로 처리하지 않습니다.")
    else:
        st.info("아직 확정된 출고 기록이 없습니다. 위에서 매일 수량을 확인한 뒤 **'오늘 재고 최종 저장'**을 누르면 오늘부터 기록이 쌓입니다. 출고가 0개인 날도 저장해야 정확한 주간 평균을 계산할 수 있습니다.")

    st.markdown(f"**이번 주 | {this_monday:%Y.%m.%d}(월) ~ {(this_monday + timedelta(days=4)):%m.%d}(금)**")
    cols = [f"{wk} {day:%m/%d}" for wk, day in zip(["월","화","수","목","금"], current["days"])]
    table_rows = []
    for key, name, _, _ in ITEMS:
        info = current["items"][key]
        row = {"품목": name}
        row.update({c: (f"{v:,}" if v is not None else "—") for c, v in zip(cols, info["daily"])})
        row["기록된 합계"] = f"{info['partial']:,}" if info["recorded"] else "—"
        row["이전 4주 평균"] = f"{prev_avg[key]:,.1f}" if prev_avg[key] is not None else "—"
        table_rows.append(row)
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    st.caption("'기록된 합계'는 저장된 날짜만 합산합니다. **— = 미기록**, **0 = 0개 출고를 확인하고 저장**한 날입니다. 4주 평균은 월~금 모두 기록된 주만 계산합니다.")

    st.markdown(f"**작년 같은 주 | {last_monday:%Y.%m.%d}(월) ~ {(last_monday + timedelta(days=4)):%m.%d}(금)**")
    if prior["complete_days"] == 0:
        st.info("작년 같은 주의 **확정된 실제 출고 기록이 아직 없습니다.** 과거 주문 DB의 부분 집계는 생산량으로 오인하기 쉬워 여기에는 표시하지 않습니다. 오늘부터 저장하면 내년 같은 주 비교에 자동으로 표시돼요.")
    else:
        st.caption(f"작년 기록 {prior['complete_days']}/5일 · 작년 직전 4주 중 완전 기록 {last_count}/4주")
        prior_cols = [f"{wk} {day:%m/%d}" for wk, day in zip(["월","화","수","목","금"], prior["days"])]
        history_table = []
        for key, name, _, _ in ITEMS:
            info = prior["items"][key]
            row = {"품목": name}
            row.update({c: (f"{v:,}" if v is not None else "—") for c, v in zip(prior_cols, info["daily"])})
            row["월~금 합계"] = f"{info['total']:,}" if info["total"] is not None else "—"
            row["하루 평균"] = f"{info['total']/5:,.1f}" if info["total"] is not None else "—"
            row["작년 직전 4주 평균"] = f"{last_avg[key]:,.1f}" if last_avg[key] is not None else "—"
            history_table.append(row)
        st.dataframe(pd.DataFrame(history_table), use_container_width=True, hide_index=True)
        if prior["complete_days"] < 5:
            st.warning("작년 해당 주의 일부 날짜가 빠져 있어 **주간 합계와 일평균은 표시하지 않습니다.** 빠진 날짜를 0개로 간주하면 실제보다 출고량이 작아집니다.")
    st.caption("같은 ISO 주차의 월~금을 비교하므로 해마다 날짜는 조금씩 다를 수 있습니다. 명절이나 배송 휴무일은 별도로 고려해 생산량을 결정하세요.")


def save_inventory(records, summary_note=""):
    client = _get_db_client()
    if client is None:
        raise RuntimeError("재고 DB 비밀키를 설정해야 저장할 수 있습니다.")
    # 재고 재저장 시 같은 날짜·품목 행은 업데이트된다. 이전 재고는 추가로 차감되지 않는다.
    payload = []
    for r in records:
        payload.append({
            "inventory_date": str(r["inventory_date"]),
            "item_key": r["item_key"],
            "opening_qty": _safe_int(r["opening_qty"]),
            "received_qty": _safe_int(r["received_qty"]),
            "auto_ship_qty": _safe_int(r["auto_ship_qty"]),
            "actual_ship_qty": _safe_int(r["actual_ship_qty"]),
            "closing_qty": _safe_int(r["closing_qty"]),
            "note": str(summary_note)[:300],
            "updated_at": datetime.now(KST).isoformat(),
        })
    client.table("inventory_daily").upsert(payload, on_conflict="inventory_date,item_key").execute()
    _read_inventory_data.clear()
    # audit는 스냅샷이 성공적으로 저장된 경우에만 추가한다.
    try:
        audit = [{"inventory_date": p["inventory_date"], "item_key": p["item_key"],
                  "opening_qty": p["opening_qty"], "received_qty": p["received_qty"],
                  "auto_ship_qty": p["auto_ship_qty"], "actual_ship_qty": p["actual_ship_qty"],
                  "closing_qty": p["closing_qty"], "note": p["note"]} for p in payload]
        client.table("inventory_audit").insert(audit).execute()
        return True
    except Exception:
        return False


def _draft_key(as_of, key, field):
    return f"inventory_{as_of.isoformat()}_{key}_{field}"


def _weekly_order_counts(orders_db, as_of):
    """주문 DB의 날짜로 ISO 연도/주를 비교한다. 병 수량이 아닌 주문 건수."""
    this_year, this_week, _ = as_of.isocalendar()
    if orders_db is None or orders_db.empty or "order_date" not in orders_db.columns:
        return 0, 0
    dates = pd.to_datetime(orders_db["order_date"], utc=True, errors="coerce")
    weeks = dates.dt.isocalendar()
    cur = int(((weeks["year"] == this_year) & (weeks["week"] == this_week)).sum())
    prior = int(((weeks["year"] == this_year - 1) & (weeks["week"] == this_week)).sum())
    return cur, prior


def render_inventory(raw_orders, orders_db, shipping_summary_func, infer_shipping_item):
    as_of = datetime.now(KST).date()
    # 맨 위에 복사 버튼 2개 + 미리보기 1개 배치.
    # 입력값은 아래에서 계산되므로 자리만 먼저 확보한 후 채운다.
    title_col, copy_all_col, copy_stock_col, preview_col = st.columns(
        [4.1, 2.25, 2.15, 1.5], gap="small", vertical_alignment="center"
    )
    with title_col:
        st.subheader("📦 재고관리")
    with copy_all_col:
        copy_all_slot = st.empty()
    with copy_stock_col:
        copy_stock_slot = st.empty()
    with preview_col:
        preview_slot = st.empty()
    st.caption(f"{as_of:%Y년 %m월 %d일} 기준  |  출고와 기존 재고 확인 → 저장  |  저장한 실출고량이 내년 같은 주 생산 참고자료가 됩니다.")

    history_rows, error = fetch_inventory_rows()
    today_saved = existing_today(history_rows, as_of)
    prev_saved = previous_inventory(history_rows, as_of)
    auto, unknown = today_shipment(raw_orders, shipping_summary_func)
    if error:
        st.warning(error)
    elif len(today_saved) == len(KEYS):
        st.success("✅ 오늘 실출고 5개 품목이 DB에 저장되어 있습니다. 수량을 바꾸면 다시 **최종 저장**해 덮어쓸 수 있어요.")
    else:
        st.info("📝 오늘 실출고는 아직 미저장 상태입니다. 엑셀과 수동 출고를 확인한 뒤 **최종 저장**을 눌러주세요.")
    if raw_orders is None or raw_orders.empty:
        st.caption("ℹ️ 오늘 업로드한 엑셀이 없어 자동 출고가 0개입니다. 이전 저장값이 있으면 그대로 표시됩니다.")
    if unknown:
        st.warning("자동 분류되지 않은 품목: " + ", ".join(f"{a} {b}개" for a, b in unknown))

    st.markdown("### 오늘 품목별 재고")
    st.caption("**기존 재고** = 오늘 출고 전에 남아 있는 수량(생산 후에는 이 수량을 직접 수정)  /  **오늘 출고** = 실제 나간 수량  /  **남은 재고** = 자동 계산")

    head = st.columns([2.2, 1.55, 1.55, 1.4], gap="small")
    for col, label in zip(head, ["품목", "오늘 출고 ✏️", "기존 재고 ✏️", "남은 재고"]):
        col.markdown(f"**{label}**")

    records = []
    for key, label, threshold, inclusive in ITEMS:
        saved = today_saved.get(key, {})
        # 예전 버전의 생산/입고값도 기존 재고에 합쳐서 불러와야 재고가 줄어들지 않는다.
        opening_default = (
            _safe_int(saved.get("opening_qty", 0)) + _safe_int(saved.get("received_qty", 0))
            if saved else prev_saved.get(key, (None, 0))[1]
        )
        actual_default = _safe_int(saved.get("actual_ship_qty", auto[key]))
        actual_key = _draft_key(as_of, key, "actual")
        auto_key = _draft_key(as_of, key, "last_auto")
        opening_key = _draft_key(as_of, key, "stock_v13")
        if actual_key not in st.session_state:
            st.session_state[actual_key] = actual_default
            st.session_state[auto_key] = auto[key]
        elif st.session_state.get(auto_key, auto[key]) != auto[key]:
            # 엑셀이 추가/변경돼도 기존 직접 수정분은 보존한다.
            delta = auto[key] - st.session_state[auto_key]
            st.session_state[actual_key] = max(0, int(st.session_state[actual_key]) + delta)
            st.session_state[auto_key] = auto[key]

        with st.container(border=True):
            c_name, c_out, c_stock, c_left = st.columns([2.2, 1.55, 1.55, 1.4], gap="small", vertical_alignment="center")
            with c_name:
                st.markdown(f"**{label}**")
                st.caption(f"엑셀 자동 {auto[key]:,}개  ·  부족 기준 {threshold}개{' 이하' if inclusive else ' 미만'}")
            with c_out:
                actual = st.number_input(
                    f"{label} 오늘 출고", min_value=0, step=1,
                    key=actual_key, label_visibility="collapsed",
                )
            with c_stock:
                opening = st.number_input(
                    f"{label} 기존 재고", min_value=0, step=1,
                    value=opening_default, key=opening_key, label_visibility="collapsed",
                )
            closing = int(opening) - int(actual)
            low = _is_low(key, closing)
            with c_left:
                color = "#c62828" if low or closing < 0 else "#18794e"
                status = "🔴 부족" if low else "🟢 정상"
                st.markdown(
                    f'<div style="font-size:23px;font-weight:800;color:{color};line-height:1.25">{closing:,}개</div>'
                    f'<div style="font-size:12px;color:{color};margin-top:3px">{status}</div>',
                    unsafe_allow_html=True,
                )
            records.append({
                "inventory_date": as_of.isoformat(), "item_key": key,
                "opening_qty": int(opening), "received_qty": 0,
                "auto_ship_qty": auto[key], "actual_ship_qty": int(actual),
                "closing_qty": closing,
            })

    # 오늘 화면에 표시된 값(저장 전 수정사항 포함)을 한 번 눌러 즉시 복사.
    with copy_all_slot.container():
        render_oneclick_copy_button(
            make_message(as_of, records, compact=False),
            "📋 출고 + 재고 복사", "sikhye-copy-all", accent=True,
        )
    with copy_stock_slot.container():
        render_oneclick_copy_button(
            make_message(as_of, records, compact=True),
            "📋 재고만 복사", "sikhye-copy-stock",
        )
    with preview_slot.container():
        with st.popover("👁 미리보기", use_container_width=True):
            st.caption("출고 + 남은 재고")
            st.code(make_message(as_of, records, compact=False), language=None)
            st.divider()
            st.caption("칠판용 · 남은 재고만")
            st.code(make_message(as_of, records, compact=True), language=None)
            st.caption("※ 복사는 DB 저장과 별개입니다. 확정하려면 아래 최종 저장을 눌러주세요.")

    low_rows = [r for r in records if _is_low(r["item_key"], r["closing_qty"])]
    negative = any(r["closing_qty"] < 0 for r in records)
    if low_rows:
        st.warning("⚠️ 재고 부족 " + str(len(low_rows)) + "종: " + ", ".join(LABELS[r["item_key"]] for r in low_rows))
    else:
        st.success("✅ 모든 품목이 설정한 재고 기준 이상입니다.")
    if negative:
        st.error("출고량이 기존 재고보다 많은 품목이 있습니다. 수량을 확인해야 저장할 수 있습니다.")

    # 기존 스키마는 opening_qty + received_qty - actual_ship_qty = closing_qty를 사용하므로
    # received_qty는 0으로 저장하고, 생산량은 opening_qty에 직접 반영한다.
    note = st.text_input(
        "변경 메모 (선택)", key=_draft_key(as_of, "all", "note_v13"),
        placeholder="예: 생산 후 실물 재고로 수정 / 택배 외 8개 추가 출고",
    )
    if st.button("💾 오늘 재고 최종 저장", type="primary", use_container_width=True,
                 disabled=negative or bool(error)):
        try:
            audit_ok = save_inventory(records, note)
            st.success("오늘 5개 품목의 실출고량과 남은 재고를 날짜별로 확정 저장했습니다. 같은 날 재저장하면 최신 값으로 수정됩니다.")
            if not audit_ok:
                st.warning("최종 재고는 저장됐지만 변경 이력 저장은 실패했습니다.")
            st.rerun()
        except Exception as exc:
            st.error(f"저장 실패: {type(exc).__name__} - {str(exc)[:150]}")

    st.divider()
    render_verified_inventory_history(history_rows, as_of)

    with st.expander("📈 최근 주간 출고 추이 (새 재고 저장 이력)", expanded=False):
        weeks = st.select_slider("조회 기간", options=[4, 8, 12, 26, 52], value=12,
                                 format_func=lambda n: f"최근 {n}주")
        weekly, avg = snapshots_weekly(history_rows, weeks=weeks, as_of=as_of)
        if weekly.empty:
            st.info("아직 저장된 재고 기록이 없습니다. 앞으로 실제 출고량을 저장하면 주간 기록이 쌓입니다.")
        else:
            pivot = weekly.pivot_table(index="주", columns="품목", values="출고수량", aggfunc="sum", fill_value=0)
            st.bar_chart(pivot)
            st.dataframe(weekly, use_container_width=True, hide_index=True)
            if not avg.empty:
                st.caption("월~금 5일 모두 기록한 주만 평균 계산에 포함")
                st.dataframe(avg.round(1), use_container_width=True, hide_index=True)
            else:
                st.caption("월~금 5일 모두 기록된 주가 없어 아직 평균을 표시하지 않습니다.")

    with st.expander("🕒 지난 재고 저장 내역", expanded=False):
        if not history_rows:
            st.info("저장 내역이 없습니다.")
        else:
            history = pd.DataFrame(history_rows)
            history["품목"] = history["item_key"].map(LABELS)
            history["기존재고"] = history["opening_qty"].fillna(0) + history["received_qty"].fillna(0)
            fields = ["inventory_date", "품목", "기존재고", "actual_ship_qty", "closing_qty", "updated_at"]
            st.dataframe(history[[x for x in fields if x in history.columns]].rename(columns={
                "inventory_date": "날짜", "actual_ship_qty": "오늘출고",
                "closing_qty": "남은재고", "updated_at": "저장시각",
            }), use_container_width=True, hide_index=True)


# =========================
# 앱 시작
# =========================
st.title("📦 식혜명가 저장형 고객 CRM")
st.caption("엑셀 업로드 → 오늘 재구매/VIP/블랙 즉시 확인 → DB 누적 저장까지 한 번에 처리합니다.")

if sb is None:
    st.markdown("""
<div class="warn">
<b>Supabase 연결이 아직 안 됐습니다.</b><br>
Streamlit Secrets에 SUPABASE_URL, SUPABASE_KEY를 넣어야 저장형 CRM으로 작동합니다.<br>
설정 전에는 앱 화면만 확인할 수 있습니다.
</div>
""", unsafe_allow_html=True)
    st.stop()

with st.expander("사용법"):
    st.write("""
1. 쿠팡/네이버 엑셀을 업로드합니다.
2. `DB에 저장하기`를 누르면 기존 DB에 누적됩니다.
3. 중복 주문번호는 자동 덮어쓰기 처리됩니다.
4. 블랙리스트 탭에서 고객별 주의/블랙 사유를 저장할 수 있습니다.
    """)

tab_upload, tab_today, tab_inventory, tab_dashboard, tab_customers, tab_detail, tab_vip, tab_ai, tab_black, tab_orders, tab_download = st.tabs([
    "⬆️ 엑셀 업로드", "🔥 오늘 주문 분석", "📦 재고관리", "📊 대시보드", "👤 고객 CRM", "🔎 고객 상세", "⭐ VIP", "🤖 AI CRM 비서", "🚫 블랙리스트", "📦 주문 DB", "⬇️ 다운로드"
])

if "today_order_preview" not in st.session_state:
    st.session_state["today_order_preview"] = pd.DataFrame()
if "today_raw_orders" not in st.session_state:
    st.session_state["today_raw_orders"] = pd.DataFrame()
if "today_customer_analysis" not in st.session_state:
    st.session_state["today_customer_analysis"] = pd.DataFrame()
if "today_detail_analysis" not in st.session_state:
    st.session_state["today_detail_analysis"] = pd.DataFrame()

with tab_upload:
    st.markdown("""
    <div class="upload-guide">
        <div class="upload-title">📂 쿠팡/네이버 엑셀 업로드</div>
        <div class="upload-sub">바로 아래 파일 업로드 박스에 끌어다 놓거나 클릭하세요.</div>
    </div>
    """, unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "➕ 엑셀 파일 추가 업로드",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        help="쿠팡 DeliveryList, 네이버 스마트스토어 엑셀을 여러 개 동시에 올릴 수 있습니다.",
    )

    if uploaded_files:
        frames, errors = [], []

        read_logs = []

        progress = st.progress(0, text="엑셀 읽는 중...")
        for idx, f in enumerate(uploaded_files, start=1):
            try:
                std, market, raw_len = parse_uploaded_file_cached(f.name, f.getvalue())
                frames.append(std)
                read_logs.append({
                    "파일명": f.name,
                    "채널": market,
                    "원본행": raw_len,
                    "정리행": len(std),
                    "상태": "성공",
                })
            except Exception as e:
                errors.append((f.name, str(e)))
                read_logs.append({
                    "파일명": f.name,
                    "채널": "",
                    "원본행": 0,
                    "정리행": 0,
                    "상태": "실패",
                })
            progress.progress(idx / len(uploaded_files), text=f"{idx}/{len(uploaded_files)}개 처리 중")

        progress.empty()

        log_df = pd.DataFrame(read_logs)
        success_count = int((log_df["상태"] == "성공").sum()) if not log_df.empty else 0
        fail_count = int((log_df["상태"] == "실패").sum()) if not log_df.empty else 0
        st.markdown(
            f'<div class="summary-box">✅ 업로드 처리 완료: 성공 <b>{success_count:,}</b>개 / 실패 <b>{fail_count:,}</b>개</div>',
            unsafe_allow_html=True
        )

        with st.expander("파일별 처리 상세 보기", expanded=False):
            if not log_df.empty:
                st.dataframe(log_df, use_container_width=True, hide_index=True)

        for name, msg in errors:
            st.error(f"{name}: {msg}")

        if frames:
            raw_orders = pd.concat(frames, ignore_index=True)
            order_preview = make_order_level(raw_orders, use_strict=False)

            # 기존 DB와 비교한 오늘 주문 분석을 세션에 저장
            orders_db_current = fetch_orders_as_order_level()
            customer_df_current = make_customer_df(orders_db_current) if not orders_db_current.empty else pd.DataFrame()
            black_df_current = fetch_blacklist()
            today_customer_analysis, today_detail_analysis = analyze_today_orders(
                order_preview, orders_db_current, customer_df_current, black_df_current
            )
            st.session_state["today_raw_orders"] = raw_orders
            st.session_state["today_order_preview"] = order_preview
            st.session_state["today_customer_analysis"] = today_customer_analysis
            st.session_state["today_detail_analysis"] = today_detail_analysis

            st.subheader("오늘 업로드 요약")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("원본 상품행", f"{len(raw_orders):,}행")
            c2.metric("실제 주문", f"{len(order_preview):,}건")
            c3.metric("예상 고객", f"{order_preview['analysis_customer_key'].nunique():,}명")
            c4.metric("오늘 재구매", f"{int((today_customer_analysis['기존주문횟수'] >= 1).sum()) if not today_customer_analysis.empty else 0:,}명")
            c5.metric("주의/블랙", f"{int((today_customer_analysis['블랙상태'].isin(['주의','블랙'])).sum()) if not today_customer_analysis.empty else 0:,}명")

            st.success("분석 완료. 위쪽의 `🔥 오늘 주문 분석` 탭에서 재구매/VIP/블랙 고객을 색상으로 확인하세요.")

            with st.expander("오늘 주문 고객 요약 바로 보기", expanded=True):
                if not today_customer_analysis.empty:
                    st.dataframe(style_today_customer_table(today_customer_analysis), use_container_width=True, hide_index=True)
                else:
                    st.info("오늘 주문 분석 데이터가 없습니다.")

            with st.expander("저장 전 주문 단위 상세 보기", expanded=False):
                st.dataframe(order_preview.sort_values("order_date", ascending=False), use_container_width=True, hide_index=True)

            col_save, col_clear = st.columns([1, 1])
            with col_save:
                if st.button("DB에 저장하기", type="primary", use_container_width=True):
                    saved = upsert_orders(order_preview)
                    st.success(f"{saved:,}건 저장 완료. 대량 자료는 1000건씩 시도하고, 실패 시 자동으로 더 작게 나눠 저장했습니다. 기존 주문번호는 자동으로 중복 제거/갱신되었습니다.")
                    st.info("저장 후 대시보드/고객 CRM 탭을 새로고침하면 누적 DB 기준으로 반영됩니다.")
            with col_clear:
                if st.button("화면 분석 결과 초기화", use_container_width=True):
                    st.session_state["today_raw_orders"] = pd.DataFrame()
                    st.session_state["today_order_preview"] = pd.DataFrame()
                    st.session_state["today_customer_analysis"] = pd.DataFrame()
                    st.session_state["today_detail_analysis"] = pd.DataFrame()
                    st.rerun()

# DB 데이터 로드
orders_db = fetch_orders_as_order_level()
black_df = fetch_blacklist()

if orders_db.empty:
    with tab_dashboard:
        st.info("아직 저장된 주문 DB가 없습니다. 먼저 엑셀을 업로드하고 DB에 저장하세요.")
    st.stop()

customer_df = make_customer_df(orders_db)

if not black_df.empty:
    customer_df = customer_df.merge(
        black_df[["customer_key", "status", "reason", "memo", "incident_date", "result"]],
        left_on="analysis_customer_key",
        right_on="customer_key",
        how="left"
    )
else:
    customer_df["status"] = ""
    customer_df["reason"] = ""
    customer_df["memo"] = ""
    customer_df["incident_date"] = ""
    customer_df["result"] = ""

customer_df["black_status"] = customer_df["status"].fillna("정상").replace("", "정상")
customer_df["총주문금액"] = customer_df["total_amount"]
customer_df["건당평균금액"] = customer_df["avg_order_amount"]


with tab_inventory:
    render_inventory(
        raw_orders=st.session_state.get("today_raw_orders", pd.DataFrame()),
        orders_db=orders_db,
        shipping_summary_func=make_shipping_summary,
        infer_shipping_item=infer_shipping_item,
    )


with tab_today:
    st.subheader("🔥 오늘 주문 분석")
    st.caption("엑셀 업로드 후 DB 저장 전에도 기존 DB와 비교해서 오늘 주문 고객이 신규인지 재구매인지 바로 확인합니다.")

    today_customer_analysis = st.session_state.get("today_customer_analysis", pd.DataFrame())
    today_detail_analysis = st.session_state.get("today_detail_analysis", pd.DataFrame())

    if today_customer_analysis is None or today_customer_analysis.empty:
        st.info("먼저 `엑셀 업로드` 탭에서 오늘 쿠팡/네이버 엑셀을 업로드하세요.")
    else:
        total_today_customers = len(today_customer_analysis)
        reorder_count = int((today_customer_analysis["기존주문횟수"] >= 1).sum())
        new_count = int((today_customer_analysis["기존주문횟수"] == 0).sum())
        vip_reorder_count = int(today_customer_analysis["오늘고객상태"].astype(str).str.contains("VIP").sum())
        black_today_count = int(today_customer_analysis["블랙상태"].isin(["주의", "블랙"]).sum())

        a, b, c, d, e = st.columns(5)
        a.metric("오늘 고객", f"{total_today_customers:,}명")
        b.metric("오늘 신규", f"{new_count:,}명")
        c.metric("오늘 재구매", f"{reorder_count:,}명")
        d.metric("VIP 재주문", f"{vip_reorder_count:,}명")
        e.metric("주의/블랙", f"{black_today_count:,}명")

        st.markdown("""
        - ⚪ 신규: 기존 DB에 없던 고객
        - 🟢 재주문: 기존 주문 이력이 있는 고객
        - 🟡 VIP 재주문: 기존 5회 이상 구매 고객
        - 🔵 복귀 재주문: 90일 이상 미구매 후 재주문
        - 🔴 주의/블랙: 블랙리스트 또는 주의 고객
        """)

        st.subheader("📦 오늘 출고 총합")
        today_raw_orders = st.session_state.get("today_raw_orders", pd.DataFrame())
        shipping_summary = make_shipping_summary(today_raw_orders)

        if shipping_summary.empty:
            st.info("오늘 업로드된 주문이 없습니다.")
        else:
            st.dataframe(shipping_summary, use_container_width=True, hide_index=True)

        with st.expander("주별 출고량 / 품목별 주간 평균", expanded=False):
            weekly_table, weekly_avg = make_weekly_shipping_table_from_orders(today_raw_orders)

            st.markdown("**업로드 파일 기준 주별 출고량**")
            if weekly_table.empty:
                st.info("주별 출고량 데이터가 없습니다.")
            else:
                st.dataframe(weekly_table, use_container_width=True, hide_index=True)

            st.markdown("**품목별 주간 평균 출고량**")
            if weekly_avg.empty:
                st.info("품목별 주간 평균 데이터가 없습니다.")
            else:
                st.dataframe(weekly_avg, use_container_width=True, hide_index=True)

        with st.expander("저장 DB 기준 최근 N주 평균 출고량 (기존 주문 단위 추정)", expanded=False):
            st.warning("기존 주문 DB는 원본 상품행이 없어 혼합 주문의 실제 병 수량을 정확히 복원할 수 없습니다. 생산량 판단에는 새 재고관리 탭의 기록을 사용하세요.")
            avg_weeks = st.slider("분석 기간", min_value=2, max_value=26, value=8, step=1)
            weekly_avg_db = make_weekly_shipping_average(orders_db, weeks=avg_weeks)
            if weekly_avg_db.empty:
                st.info("주간 평균 출고량 데이터가 없습니다.")
            else:
                st.dataframe(weekly_avg_db, use_container_width=True, hide_index=True)

        filter_status = st.multiselect(
            "상태 필터",
            options=sorted(today_customer_analysis["오늘고객상태"].unique()),
            default=sorted(today_customer_analysis["오늘고객상태"].unique()),
        )

        view_today = today_customer_analysis[today_customer_analysis["오늘고객상태"].isin(filter_status)]
        st.dataframe(style_today_customer_table(view_today), use_container_width=True, hide_index=True, height=420)

        st.subheader("고객별 역대 주문내역 보기")
        selected_customer = st.selectbox(
            "고객 선택",
            options=view_today["고객키"].tolist(),
            format_func=lambda k: view_today.loc[view_today["고객키"] == k, "오늘고객명"].iloc[0] + " | " + str(view_today.loc[view_today["고객키"] == k, "오늘고객상태"].iloc[0])
        )

        history = orders_db[orders_db["analysis_customer_key"] == selected_customer].sort_values("order_date", ascending=False)
        st.write("기존 DB 저장 주문내역")
        if history.empty:
            st.info("기존 주문내역 없음. 이번 주문이 첫 주문입니다.")
        else:
            st.dataframe(history, use_container_width=True, hide_index=True)

        if today_detail_analysis is not None and not today_detail_analysis.empty:
            st.write("이번 업로드 주문 상세")
            today_detail_customer = today_detail_analysis[today_detail_analysis["analysis_customer_key"] == selected_customer]
            st.dataframe(today_detail_customer, use_container_width=True, hide_index=True)



with tab_dashboard:
    st.subheader("📊 고객·주문 대시보드")
    st.caption("저장된 CRM 데이터 기준 · 고객의 구매횟수는 누적 주문횟수로 계산")

    total_orders = len(orders_db)
    total_customers = len(customer_df)
    repeat_customers = int((customer_df["order_count"] >= 2).sum())
    repeat_rate = repeat_customers / total_customers * 100 if total_customers else 0
    one_time_customers = int((customer_df["order_count"] == 1).sum())
    vip_count = int((customer_df["order_count"] >= 5).sum())
    black_count = int((customer_df["black_status"].isin(["주의", "블랙"])).sum())

    # 큰 카드 여섯 개를 3개씩 두 줄에 배치해 좁은 화면에서도 수치가 명확하게 읽히도록.
    k1, k2, k3 = st.columns(3)
    k1.metric("누적 주문", f"{total_orders:,}건")
    k2.metric("누적 고객", f"{total_customers:,}명")
    k3.metric("재구매율", f"{repeat_rate:.1f}%")
    k4, k5, k6 = st.columns(3)
    k4.metric("1회 구매 고객", f"{one_time_customers:,}명")
    k5.metric("재구매 고객 (2회 이상)", f"{repeat_customers:,}명")
    k6.metric("VIP (5회 이상)", f"{vip_count:,}명")
    if black_count:
        st.caption(f"⚠️ 주의/블랙 지정 고객: {black_count:,}명 · 자세한 내용은 블랙리스트 탭에서 확인")

    st.divider()
    st.markdown("#### 📈 월별 주문 흐름")
    selected_months = st.segmented_control(
        "표시 기간", options=["최근 12개월", "최근 24개월", "전체"],
        default="최근 12개월", key="dashboard_month_window",
    )
    monthly = orders_db[["order_date"]].copy()
    monthly["order_date"] = pd.to_datetime(monthly["order_date"], errors="coerce", utc=True)
    monthly = monthly.dropna(subset=["order_date"])
    monthly["month"] = monthly["order_date"].dt.strftime("%Y-%m")
    counts = monthly.groupby("month").size().rename("orders").reset_index().sort_values("month")
    if not counts.empty:
        # 데이터가 없는 중간 월도 0건으로 표시해 흐름 왜곡 방지
        month_period = pd.period_range(counts["month"].iloc[0], counts["month"].iloc[-1], freq="M")
        counts = (pd.DataFrame({"month": month_period.astype(str)})
                  .merge(counts, on="month", how="left").fillna({"orders": 0}))
        counts["orders"] = counts["orders"].astype(int)
        if selected_months != "전체":
            n = 12 if selected_months == "최근 12개월" else 24
            counts = counts.tail(n)
        counts["3개월 평균"] = counts["orders"].rolling(3, min_periods=1).mean().round(1)
        latest_orders = int(counts["orders"].iloc[-1])
        # 사용자 스크린샷의 현재 달은 아직 진행 중이므로 수치를 확정 비교하지 않음
        st.caption(f"조회 기간: {counts['month'].iloc[0]} ~ {counts['month'].iloc[-1]} · 마지막 달 {latest_orders:,}건 (진행 중인 월일 수 있음)")
        bars = alt.Chart(counts).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("month:N", sort=list(counts["month"]), title=None,
                    axis=alt.Axis(labelAngle=-40, labelOverlap=False, labelFontSize=11)),
            y=alt.Y("orders:Q", title="주문 건수", axis=alt.Axis(tickMinStep=1)),
            tooltip=[alt.Tooltip("month:N", title="월"), alt.Tooltip("orders:Q", title="주문", format=",d"),
                     alt.Tooltip("3개월 평균:Q", title="3개월 이동평균", format=".1f")],
            color=alt.value("#2563eb"),
        )
        st.altair_chart(bars.properties(height=265), use_container_width=True)
    else:
        st.info("월별 주문 날짜를 확인할 수 없습니다.")

    st.divider()
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        st.markdown("#### 👥 구매횟수별 고객")
        st.caption("가로 막대로 표시해 '1회' 등의 글자가 잘리지 않도록 개선")
        cats = ["1회", "2회", "3회", "4회", "5회 이상"]
        oc = pd.to_numeric(customer_df["order_count"], errors="coerce").fillna(0)
        bucket_df = pd.DataFrame({"구매횟수": cats, "고객수": [
            int((oc == 1).sum()), int((oc == 2).sum()), int((oc == 3).sum()),
            int((oc == 4).sum()), int((oc >= 5).sum()),
        ]})
        max_customers = max(1, int(bucket_df["고객수"].max()))
        chart = alt.Chart(bucket_df).mark_bar(cornerRadiusEnd=4, size=24).encode(
            y=alt.Y("구매횟수:N", sort=cats, title=None,
                    axis=alt.Axis(labelAngle=0, labelFontSize=13, labelPadding=10)),
            x=alt.X("고객수:Q", title="고객 수", scale=alt.Scale(domain=[0, max_customers * 1.22]),
                    axis=alt.Axis(format=",d", tickCount=4)),
            color=alt.condition(alt.datum["구매횟수"] == "1회", alt.value("#f59e0b"), alt.value("#2563eb")),
            tooltip=[alt.Tooltip("구매횟수:N"), alt.Tooltip("고객수:Q", format=",d")],
        )
        labels = alt.Chart(bucket_df).mark_text(align="left", baseline="middle", dx=8, fontSize=13, fontWeight="bold").encode(
            y=alt.Y("구매횟수:N", sort=cats), x="고객수:Q", text=alt.Text("고객수:Q", format=",d"))
        st.altair_chart((chart + labels).properties(height=240), use_container_width=True)
    with right:
        st.markdown("#### 🔍 고객 구조 한눈에")
        first_rate = 100 - repeat_rate if total_customers else 0
        st.metric("1회 구매 비중", f"{first_rate:.1f}%")
        st.progress(min(1.0, max(0.0, first_rate / 100)))
        st.caption("재구매 유도 대상 고객의 규모를 파악할 수 있어요.")
        st.metric("VIP 비중", f"{vip_count / total_customers * 100:.1f}%" if total_customers else "0.0%")
        st.caption("VIP = 누적 5회 이상 구매 고객")

    st.divider()
    st.markdown("#### 🤖 CRM AI 분석")
    ai_ready = ai_status_line()
    if st.button("✨ 현재 CRM 자동 분석", type="primary", key="dashboard_ai_run_v19", disabled=not ai_ready):
        with st.spinner("집계 데이터를 바탕으로 분석 중..."):
            st.session_state["dashboard_ai_result_v19"] = auto_ai_crm_analysis(customer_df, orders_db)
    if st.session_state.get("dashboard_ai_result_v19"):
        st.markdown(st.session_state["dashboard_ai_result_v19"])

with tab_customers:
    st.subheader("👤 고객 CRM")
    st.caption("이름/전화번호/주소/상품명으로 검색하고, VIP·재구매·블랙 고객을 색상으로 확인합니다.")

    search = st.text_input("통합 검색", placeholder="예: 고객명, 전화번호, 주소, 상품명")
    grade_options = sorted(customer_df["grade"].dropna().unique())
    selected_grades = st.multiselect("고객등급", grade_options, default=grade_options)

    black_options = sorted(customer_df["black_status"].dropna().unique())
    selected_black = st.multiselect("블랙상태", black_options, default=black_options)

    view = customer_df[
        (customer_df["grade"].isin(selected_grades)) &
        (customer_df["black_status"].isin(selected_black))
    ].copy()

    if search:
        search_mask = (
            view["customer_name"].astype(str).str.contains(search, case=False, na=False)
            | view["phone"].astype(str).str.contains(search, case=False, na=False)
            | view["address"].astype(str).str.contains(search, case=False, na=False)
            | view["products"].astype(str).str.contains(search, case=False, na=False)
        )
        view = view[search_mask]

    sort_col = st.selectbox("정렬", ["order_count", "total_amount", "last_order_date", "avg_order_amount"], index=0)
    view = view.sort_values(sort_col, ascending=False)

    show_cols = [
        "customer_name", "phone", "address", "grade", "black_status",
        "order_count", "total_amount", "avg_order_amount",
        "first_order_date", "last_order_date", "channels", "products"
    ]
    show_cols = [c for c in show_cols if c in view.columns]

    st.dataframe(style_customer_crm_table(view[show_cols]), use_container_width=True, hide_index=True, height=520)

    st.markdown("### 고객 CRM 구매이력 바로 확인")
    if view.empty:
        st.info("검색 결과가 없습니다.")
    else:
        history_options = view.copy()
        history_options["history_label"] = (
            history_options["customer_name"].astype(str)
            + " | "
            + history_options["phone"].astype(str)
            + " | "
            + history_options["order_count"].astype(str)
            + "회"
        )

        selected_history_label = st.selectbox("구매이력 확인할 고객 선택", history_options["history_label"].tolist())
        selected_history = history_options[history_options["history_label"] == selected_history_label].iloc[0]
        selected_key = selected_history["analysis_customer_key"]

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("주문횟수", f"{int(selected_history['order_count']):,}회")
        h2.metric("총 주문금액", f"{int(selected_history.get('total_amount', 0)):,}원")
        h3.metric("건당 평균금액", f"{int(selected_history.get('avg_order_amount', 0)):,}원")
        h4.metric("최근 주문일", str(pd.to_datetime(selected_history["last_order_date"]).date()))

        notes_df = fetch_customer_notes()
        memo_text = ""
        if not notes_df.empty and selected_key in notes_df["customer_key"].astype(str).values:
            memo_text = notes_df[notes_df["customer_key"].astype(str) == str(selected_key)]["memo"].iloc[0]
        if memo_text:
            st.markdown(f"**고객 메모**  \n{memo_text}")

        history_df = orders_db[orders_db["analysis_customer_key"] == selected_key].sort_values("order_date", ascending=False)
        st.dataframe(history_df, use_container_width=True, hide_index=True, height=300)



with tab_detail:
    st.subheader("🔎 고객 상세")
    st.caption("고객을 선택하면 주문횟수, 첫/최근 주문일, 전체 주문내역, 고객 메모를 볼 수 있습니다.")

    customer_view = customer_df.sort_values(["order_count", "last_order_date"], ascending=[False, False]).copy()
    customer_view["label"] = (
        customer_view["customer_name"].astype(str)
        + " | "
        + customer_view["phone"].astype(str)
        + " | "
        + customer_view["order_count"].astype(str)
        + "회"
    )

    keyword = st.text_input("이름/전화번호/주소 검색")
    if keyword:
        mask = (
            customer_view["customer_name"].astype(str).str.contains(keyword, case=False, na=False)
            | customer_view["phone"].astype(str).str.contains(keyword, case=False, na=False)
            | customer_view["address"].astype(str).str.contains(keyword, case=False, na=False)
        )
        customer_view = customer_view[mask]

    if customer_view.empty:
        st.info("검색 결과가 없습니다.")
    else:
        selected_label = st.selectbox("고객 선택", customer_view["label"].tolist())
        selected = customer_view[customer_view["label"] == selected_label].iloc[0]
        key = selected["analysis_customer_key"]

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("주문횟수", f"{int(selected['order_count']):,}회")
        c2.metric("등급", str(selected["grade"]))
        c3.metric("총 주문금액", f"{int(selected.get('total_amount', 0)):,}원")
        c4.metric("건당 평균금액", f"{int(selected.get('avg_order_amount', 0)):,}원")
        c5.metric("첫 주문일", str(pd.to_datetime(selected["first_order_date"]).date()))
        c6.metric("최근 주문일", str(pd.to_datetime(selected["last_order_date"]).date()))

        st.write("고객정보")
        info_df = pd.DataFrame([{
            "고객명": selected["customer_name"],
            "전화번호": selected["phone"],
            "주소": selected["address"],
            "이용채널": selected["channels"],
            "구매상품": selected["products"],
        }])
        st.dataframe(info_df, use_container_width=True, hide_index=True)

        st.write("고객 메모 / 태그")
        notes_df = fetch_customer_notes()
        old_memo = ""
        if not notes_df.empty and key in notes_df["customer_key"].astype(str).values:
            old_memo = notes_df[notes_df["customer_key"].astype(str) == str(key)]["memo"].iloc[0]

        tag_options = [
            "단호박매니아", "식혜매니아", "혼합구매", "대량주문", "소량주문",
            "신규", "재구매", "VIP", "VVIP",
            "쿠폰반응", "행사반응", "선물용", "재구매유도",
            "CS주의", "배송주의", "블랙",
            "회사구매", "학교구매", "단체구매"
        ]
        selected_tags = st.multiselect("고객 태그", tag_options)
        memo_input = st.text_area("메모 입력", value=old_memo, placeholder="예: 단호박 선호 / 행사 대량주문 / CS 주의")
        save_text = "[태그] " + ", ".join(selected_tags) + "\n" + memo_input if selected_tags else memo_input

        if st.button("고객 메모 저장", type="primary"):
            save_customer_note(key, selected["customer_name"], selected["phone"], selected["address"], save_text)
            st.success("고객 메모 저장 완료")

        st.write("전체 주문내역")
        history = orders_db[orders_db["analysis_customer_key"] == key].sort_values("order_date", ascending=False)
        st.dataframe(history, use_container_width=True, hide_index=True)


with tab_vip:
    st.subheader("⭐ VIP 고객")
    st.caption("기본 5회 이상, 필요하면 기준을 바꿔 확인할 수 있습니다.")

    vip_min = st.slider("VIP 기준 주문횟수", min_value=2, max_value=20, value=5, step=1)
    vip_df = customer_df[customer_df["order_count"] >= vip_min].sort_values(["order_count", "last_order_date"], ascending=[False, False])

    a, b = st.columns(2)
    a.metric("VIP 고객수", f"{len(vip_df):,}명")
    b.metric("최고 주문횟수", f"{int(vip_df['order_count'].max()) if not vip_df.empty else 0:,}회")

    st.dataframe(vip_df, use_container_width=True, hide_index=True)



with tab_ai:
    st.subheader("🤖 AI CRM 비서")
    st.caption("고객 개인정보는 보내지 않고 누적 주문·재구매율·구매횟수 등 집계만 전송합니다.")
    ai_ready = ai_status_line()
    if not ai_ready:
        st.code('AI_PROVIDER = "gemini"\nGEMINI_API_KEY = "실제 API 키"\nGEMINI_MODEL = "gemini-3.5-flash-lite"', language="toml")
        st.caption("설정 경로: Streamlit Cloud → 앱 → Settings → Secrets · 비밀키는 채팅에 보내지 마세요.")

    st.markdown("### 🚀 자동 CRM 분석")
    if st.button("✨ 자동 CRM 분석 실행", type="primary", use_container_width=True,
                 key="ai_tab_auto_v19", disabled=not ai_ready):
        with st.spinner("집계 데이터를 분석 중입니다..."):
            st.session_state["ai_tab_auto_result_v19"] = auto_ai_crm_analysis(customer_df, orders_db)
    if st.session_state.get("ai_tab_auto_result_v19"):
        st.markdown(st.session_state["ai_tab_auto_result_v19"])

    st.divider()
    st.markdown("### 💬 직접 질문")
    quick_q = st.selectbox("빠른 질문", [
        "현재 CRM 상태를 짧게 분석해줘",
        "재구매율을 높이려면 뭘 하면 좋을까?",
        "VIP 고객 관리 전략을 추천해줘",
        "오늘 주문 분석 결과에서 주의할 점을 알려줘",
        "마케팅 문자 보낼 고객 기준을 추천해줘",
        "2회 구매 고객을 3회 구매로 전환하는 방법을 알려줘",
        "VIP 고객에게 보낼 문자 문구를 작성해줘",
    ])
    custom_q = st.text_area("직접 질문", placeholder="예: 3회 이상 구매고객에게 어떤 이벤트를 하면 좋을까?")
    question = custom_q.strip() if custom_q.strip() else quick_q
    if st.button("AI에게 질문하기", use_container_width=True,
                 key="ai_tab_question_v19", disabled=not ai_ready):
        with st.spinner("분석 중입니다..."):
            st.session_state["ai_tab_question_result_v19"] = ask_ai_crm(question, customer_df, orders_db)
    if st.session_state.get("ai_tab_question_result_v19"):
        st.markdown(st.session_state["ai_tab_question_result_v19"])

with tab_black:
    st.subheader("블랙리스트 / 주의고객 관리")

    customer_options = customer_df.sort_values(["order_count", "last_order_date"], ascending=[False, False]).copy()
    customer_options["label"] = (
        customer_options["customer_name"].astype(str)
        + " | "
        + customer_options["phone"].astype(str)
        + " | "
        + customer_options["address"].astype(str).str[:40]
    )

    selected_label = st.selectbox("고객 선택", customer_options["label"].tolist())
    selected = customer_options[customer_options["label"] == selected_label].iloc[0]

    with st.form("black_form"):
        status = st.selectbox("상태", ["정상", "주의", "블랙"], index=0)
        reason = st.selectbox("사유", ["", "반복 환불 요구", "허위 클레임", "배송 트집", "폭언/욕설", "고의 반품", "기타"])
        incident_date = st.date_input("발생일", value=date.today())
        result = st.text_input("처리 결과", placeholder="예: 재배송함 / 환불함 / 다음 주문 시 확인")
        memo = st.text_area("상세 기록", placeholder="어떤 문제가 있었는지 기록")
        submitted = st.form_submit_button("저장")

    if submitted:
        row = {
            "customer_key": str(selected["analysis_customer_key"]),
            "customer_name": str(selected["customer_name"]),
            "phone": str(selected["phone"]),
            "address": str(selected["address"]),
            "status": status,
            "reason": reason,
            "memo": memo,
            "incident_date": str(incident_date),
            "result": result,
        }
        save_blacklist(row)
        st.success("블랙리스트 기록 저장 완료. 새로고침하면 반영됩니다.")

    st.subheader("현재 블랙리스트")
    st.dataframe(black_df.sort_values("updated_at", ascending=False) if "updated_at" in black_df.columns else black_df, use_container_width=True, hide_index=True)

    if not black_df.empty:
        delete_key = st.selectbox("삭제할 기록 선택", black_df["customer_key"].tolist())
        if st.button("선택 기록 삭제"):
            delete_blacklist(delete_key)
            st.success("삭제 완료. 새로고침하면 반영됩니다.")

with tab_orders:
    st.subheader("저장된 주문 DB")
    st.dataframe(orders_db.sort_values("order_date", ascending=False), use_container_width=True, hide_index=True)

with tab_download:
    st.subheader("엑셀 다운로드")

    vip = customer_df[customer_df["order_count"] >= 5].copy()
    repeat = customer_df[customer_df["order_count"] >= 2].copy()
    churn_risk = customer_df[customer_df["days_since_last_order"] >= 90].copy()
    black_customers = customer_df[customer_df["black_status"].isin(["주의", "블랙"])].copy()

    summary = pd.DataFrame({
        "항목": ["누적 주문", "누적 고객", "재구매 고객", "재구매율", "VIP", "주의/블랙"],
        "값": [len(orders_db), len(customer_df), len(repeat), f"{repeat_rate:.1f}%", len(vip), len(black_customers)]
    })

    download_sheets = {
        "요약": summary,
        "고객CRM": customer_df.sort_values(["order_count", "last_order_date"], ascending=[False, False]),
        "VIP": vip,
        "재구매": repeat,
        "이탈위험": churn_risk,
        "블랙리스트": black_customers,
        "주문DB": orders_db.sort_values("order_date", ascending=False),
    }

    today_customer_analysis = st.session_state.get("today_customer_analysis", pd.DataFrame())
    today_detail_analysis = st.session_state.get("today_detail_analysis", pd.DataFrame())
    if today_customer_analysis is not None and not today_customer_analysis.empty:
        download_sheets["오늘주문분석"] = today_customer_analysis
    if today_detail_analysis is not None and not today_detail_analysis.empty:
        download_sheets["오늘주문상세"] = today_detail_analysis

    excel_bytes = to_excel_bytes(download_sheets)

    st.download_button(
        "저장형 CRM 엑셀 다운로드",
        data=excel_bytes,
        file_name=f"sikhye_saved_crm_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )