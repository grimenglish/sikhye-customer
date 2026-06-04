
import io
import re
from datetime import datetime, date

import pandas as pd
import streamlit as st

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

</style>
""", unsafe_allow_html=True)

SMARTSTORE_PASSWORD = "1111"


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
    out["product_name"] = safe_series(df, product_col, "").map(normalize_text)
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

    # 대량 저장 시 Supabase/PostgREST 요청 크기 제한에 걸리지 않도록 나눠서 저장
    chunk_size = 700
    saved_count = 0

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        sb.table("orders").upsert(chunk, on_conflict="order_key").execute()
        saved_count += len(chunk)

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


def delete_blacklist(customer_key):
    if sb is None:
        return
    sb.table("blacklist").delete().eq("customer_key", customer_key).execute()


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


def style_today_customer_table(df):
    """오늘 주문 분석 표 색상"""
    if df is None or df.empty:
        return df

    def row_style(row):
        status = str(row.get("오늘고객상태", ""))
        black = str(row.get("블랙상태", ""))

        if "🔴" in status or black in ["주의", "블랙"]:
            return ["background-color: #fee2e2"] * len(row)
        if "🟡" in status:
            return ["background-color: #fef3c7"] * len(row)
        if "🔵" in status:
            return ["background-color: #dbeafe"] * len(row)
        if "🟢" in status:
            return ["background-color: #dcfce7"] * len(row)
        return [""] * len(row)

    return df.style.apply(row_style, axis=1)

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

tab_upload, tab_today, tab_dashboard, tab_customers, tab_black, tab_orders, tab_download = st.tabs([
    "⬆️ 엑셀 업로드", "🔥 오늘 주문 분석", "📊 대시보드", "👤 고객 CRM", "🚫 블랙리스트", "📦 주문 DB", "⬇️ 다운로드"
])

if "today_order_preview" not in st.session_state:
    st.session_state["today_order_preview"] = pd.DataFrame()
if "today_customer_analysis" not in st.session_state:
    st.session_state["today_customer_analysis"] = pd.DataFrame()
if "today_detail_analysis" not in st.session_state:
    st.session_state["today_detail_analysis"] = pd.DataFrame()

with tab_upload:
    st.markdown("""
    <div class="upload-guide">
        <div class="upload-title">📂 쿠팡/네이버 엑셀을 여기에 끌어다 놓기</div>
        <div class="upload-sub">파일 여러 개를 한 번에 드래그하거나, 아래 큰 버튼을 눌러 추가 업로드하세요.</div>
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
                raw = pd.read_csv(f) if f.name.lower().endswith(".csv") else read_excel_file(f)
                market = detect_market(f.name, raw)
                std = standardize(raw, market, f.name)
                frames.append(std)
                read_logs.append({
                    "파일명": f.name,
                    "채널": market,
                    "원본행": len(raw),
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
                    st.success(f"{saved:,}건 저장 완료. 대량 자료는 700건씩 나눠 안전하게 저장했습니다. 기존 주문번호는 자동으로 중복 제거/갱신되었습니다.")
                    st.info("저장 후 대시보드/고객 CRM 탭을 새로고침하면 누적 DB 기준으로 반영됩니다.")
            with col_clear:
                if st.button("화면 분석 결과 초기화", use_container_width=True):
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
    total_orders = len(orders_db)
    total_customers = len(customer_df)
    repeat_customers = int((customer_df["order_count"] >= 2).sum())
    repeat_rate = repeat_customers / total_customers * 100 if total_customers else 0
    vip_count = int((customer_df["order_count"] >= 5).sum())
    black_count = int((customer_df["black_status"].isin(["주의", "블랙"])).sum())

    cols = st.columns(6)
    for col, (title, val) in zip(cols, [
        ("누적 주문", f"{total_orders:,}건"),
        ("누적 고객", f"{total_customers:,}명"),
        ("재구매 고객", f"{repeat_customers:,}명"),
        ("재구매율", f"{repeat_rate:.1f}%"),
        ("VIP", f"{vip_count:,}명"),
        ("주의/블랙", f"{black_count:,}명"),
    ]):
        with col:
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">{title}</div><div class="kpi-value">{val}</div></div>', unsafe_allow_html=True)

    st.write("")
    left, right = st.columns(2)

    with left:
        st.subheader("월별 누적 주문")
        monthly = orders_db.copy()
        monthly["월"] = pd.to_datetime(monthly["order_date"]).dt.to_period("M").astype(str)
        st.bar_chart(monthly.groupby("월").size())

    with right:
        st.subheader("구매횟수별 고객")
        bucket = customer_df["order_count"].apply(lambda x: "1회" if x == 1 else "2회" if x == 2 else "3회" if x == 3 else "4회 이상")
        st.bar_chart(bucket.value_counts().reindex(["1회", "2회", "3회", "4회 이상"]).fillna(0))

with tab_customers:
    st.subheader("고객 CRM")
    grades = st.multiselect("고객등급", sorted(customer_df["grade"].unique()), default=sorted(customer_df["grade"].unique()))
    black_statuses = st.multiselect("블랙상태", sorted(customer_df["black_status"].unique()), default=sorted(customer_df["black_status"].unique()))

    view = customer_df[(customer_df["grade"].isin(grades)) & (customer_df["black_status"].isin(black_statuses))]
    view = view.sort_values(["order_count", "last_order_date"], ascending=[False, False])
    st.dataframe(view, use_container_width=True, hide_index=True)

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
