
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

    today = pd.Timestamp.today().normalize()
    customer["grade"] = customer["order_count"].apply(grade)
    customer["customer_type"] = customer["order_count"].apply(lambda x: "재구매" if x >= 2 else "신규")
    customer["days_since_last_order"] = (today - pd.to_datetime(customer["last_order_date"]).dt.normalize()).dt.days
    customer["churn_status"] = customer["days_since_last_order"].apply(churn)
    customer["avg_order_amount"] = (customer["total_amount"] / customer["order_count"]).round(0).astype(int)
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
            "order_date": pd.to_datetime(r["order_date"]).isoformat(),
            "product_order_nos": str(r["product_order_nos"]),
            "product_names": str(r["product_names"]),
            "total_quantity": int(r["total_quantity"]),
            "total_amount": int(r["total_amount"]),
            "source_files": str(r["source_files"]),
            "raw_rows": int(r["raw_rows"]),
            "updated_at": now,
        })

    sb.table("orders").upsert(records, on_conflict="order_key").execute()
    return len(records)


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
            df.to_excel(writer, index=False, sheet_name=name[:31])
    output.seek(0)
    return output.getvalue()


# =========================
# 앱 시작
# =========================
st.title("📦 식혜명가 저장형 고객 CRM")
st.caption("엑셀을 올리면 DB에 누적 저장되고, 다음 접속 때도 고객 데이터가 유지됩니다.")

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

tab_upload, tab_dashboard, tab_customers, tab_black, tab_orders, tab_download = st.tabs([
    "⬆️ 엑셀 업로드", "📊 대시보드", "👤 고객 CRM", "🚫 블랙리스트", "📦 주문 DB", "⬇️ 다운로드"
])

with tab_upload:
    uploaded_files = st.file_uploader(
        "쿠팡/네이버 엑셀 여러 개 업로드",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        frames, errors = [], []

        for f in uploaded_files:
            try:
                raw = pd.read_csv(f) if f.name.lower().endswith(".csv") else read_excel_file(f)
                market = detect_market(f.name, raw)
                std = standardize(raw, market, f.name)
                frames.append(std)
                st.success(f"{f.name} 읽기 성공: {market} / 원본 {len(raw):,}행 → 정리 {len(std):,}행")
            except Exception as e:
                errors.append((f.name, str(e)))

        for name, msg in errors:
            st.error(f"{name}: {msg}")

        if frames:
            raw_orders = pd.concat(frames, ignore_index=True)
            order_preview = make_order_level(raw_orders, use_strict=False)

            st.subheader("저장 전 미리보기")
            c1, c2, c3 = st.columns(3)
            c1.metric("원본 상품행", f"{len(raw_orders):,}행")
            c2.metric("실제 주문", f"{len(order_preview):,}건")
            c3.metric("예상 고객", f"{order_preview['analysis_customer_key'].nunique():,}명")

            st.dataframe(order_preview.sort_values("order_date", ascending=False), use_container_width=True, hide_index=True)

            if st.button("DB에 저장하기", type="primary"):
                saved = upsert_orders(order_preview)
                st.success(f"{saved:,}건 저장 완료. 기존 주문번호는 자동으로 중복 제거/갱신되었습니다.")

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

    excel_bytes = to_excel_bytes({
        "요약": summary,
        "고객CRM": customer_df.sort_values(["order_count", "last_order_date"], ascending=[False, False]),
        "VIP": vip,
        "재구매": repeat,
        "이탈위험": churn_risk,
        "블랙리스트": black_customers,
        "주문DB": orders_db.sort_values("order_date", ascending=False),
    })

    st.download_button(
        "저장형 CRM 엑셀 다운로드",
        data=excel_bytes,
        file_name=f"sikhye_saved_crm_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
