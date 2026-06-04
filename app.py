
import re
import io
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    import msoffcrypto
except Exception:
    msoffcrypto = None


st.set_page_config(
    page_title="식혜명가 고객 재구매 분석",
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
.kpi-value {font-size:30px;font-weight:800;color:#111;}
.note {
    background:#f6f8fa;
    border:1px solid #e5e7eb;
    padding:14px 16px;
    border-radius:12px;
    color:#333;
}
</style>
""", unsafe_allow_html=True)

SMARTSTORE_PASSWORD = "1111"


# =========================
# 기본 함수
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


def read_excel_file(uploaded_file):
    raw = uploaded_file.getvalue()

    try:
        return pd.read_excel(io.BytesIO(raw))
    except Exception as first_error:
        if msoffcrypto is None:
            raise RuntimeError(
                "암호화된 엑셀을 읽으려면 msoffcrypto-tool이 필요합니다. requirements.txt를 최신 파일로 교체하세요."
            )

        try:
            office = msoffcrypto.OfficeFile(io.BytesIO(raw))
            office.load_key(password=SMARTSTORE_PASSWORD)
            decrypted = io.BytesIO()
            office.decrypt(decrypted)
            decrypted.seek(0)
            return pd.read_excel(decrypted)
        except Exception as second_error:
            raise RuntimeError(
                f"엑셀을 읽지 못했습니다. 첫 오류: {first_error} / 암호해제 오류: {second_error}"
            )


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


def safe_series(df, col, default=""):
    if col and col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


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
        # 쿠팡은 같은 배송 묶음 안의 여러 상품행을 1주문으로 계산
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
    out["판매채널"] = market
    out["원본파일"] = filename

    order_unit = safe_series(df, order_unit_col, "")
    product_order = safe_series(df, product_order_col, "")

    out["주문단위번호"] = order_unit.astype(str).str.replace(".0", "", regex=False)
    out["상품주문번호"] = product_order.astype(str).str.replace(".0", "", regex=False)

    # 주문단위번호가 비어있으면 상품주문번호로 대체하되, 이 경우만 예외
    out["주문단위번호"] = out["주문단위번호"].where(out["주문단위번호"].str.strip() != "", out["상품주문번호"])

    out["주문일"] = pd.to_datetime(safe_series(df, order_date_col, pd.NaT), errors="coerce")
    out["수취인"] = safe_series(df, receiver_col, "").map(normalize_text)
    out["수취인전화"] = safe_series(df, receiver_phone_col, "").map(normalize_phone)
    out["구매자"] = safe_series(df, buyer_col, "").map(normalize_text)
    out["구매자전화"] = safe_series(df, buyer_phone_col, "").map(normalize_phone)
    out["주소"] = safe_series(df, address_col, "").map(normalize_address)
    out["상품명"] = safe_series(df, product_col, "").map(normalize_text)
    out["수량"] = pd.to_numeric(safe_series(df, qty_col, 1), errors="coerce").fillna(1).astype(int)
    out["결제금액"] = pd.to_numeric(safe_series(df, amount_col, 0), errors="coerce").fillna(0).astype(int)

    name_key = out["수취인"].where(out["수취인"] != "", out["구매자"])
    phone_key = out["수취인전화"].where(out["수취인전화"] != "", out["구매자전화"])

    # 기본 고객키: 이름+주소
    # 쿠팡 050 안심번호가 주문마다 바뀌는 문제 방지
    out["고객키"] = (
        name_key.fillna("").astype(str).str.strip()
        + "|"
        + out["주소"].fillna("").astype(str).str.strip()
    )

    # 더 엄격한 고객키: 이름+전화+주소
    out["전화포함고객키"] = (
        name_key.fillna("").astype(str).str.strip()
        + "|"
        + phone_key.fillna("").astype(str).str.strip()
        + "|"
        + out["주소"].fillna("").astype(str).str.strip()
    )

    # 채널까지 포함한 주문 단위키
    out["주문단위키"] = out["판매채널"] + "|" + out["주문단위번호"].astype(str)

    out = out[(name_key != "") | (out["주소"] != "") | (phone_key != "")]
    return out


def join_unique(series):
    vals = []
    for v in series:
        v = str(v).strip()
        if v and v.lower() != "nan" and v not in vals:
            vals.append(v)
    return ", ".join(vals)


def to_excel_bytes(order_df, customer_df, raw_df, summary_df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="요약")
        customer_df.to_excel(writer, index=False, sheet_name="고객별분석")
        order_df.to_excel(writer, index=False, sheet_name="주문단위정리")
        raw_df.to_excel(writer, index=False, sheet_name="원본행정리")
    output.seek(0)
    return output.getvalue()


# =========================
# 화면
# =========================
st.title("📦 식혜명가 고객 재구매 분석")
st.caption("쿠팡 DeliveryList / 네이버 스마트스토어 엑셀을 올리면 신규·재구매·VIP 고객을 자동 계산합니다.")

with st.expander("사용법"):
    st.write("""
- 쿠팡: `DeliveryList...xlsx`
- 네이버 스마트스토어: `스마트스토어_선택주문발주발송관리...xlsx`
- 네이버 파일 비밀번호는 자동으로 `1111`을 사용합니다.
- **네이버는 주문번호 기준**, **쿠팡은 묶음배송번호 기준**으로 1주문을 계산합니다.
- 즉, 네이버에서 1L/500ml가 상품주문번호 2개로 나뉘어도 주문번호가 같으면 주문 1건으로 처리합니다.
    """)

uploaded_files = st.file_uploader(
    "엑셀 파일 업로드",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("쿠팡/네이버 송장 엑셀을 업로드하세요.")
    st.stop()

frames = []
errors = []

for f in uploaded_files:
    try:
        if f.name.lower().endswith(".csv"):
            raw = pd.read_csv(f)
        else:
            raw = read_excel_file(f)

        market = detect_market(f.name, raw)
        std = standardize(raw, market, f.name)
        frames.append(std)
        st.success(f"{f.name} 읽기 성공: {market} / 원본 {len(raw):,}행 → 정리 {len(std):,}행")

    except Exception as e:
        errors.append((f.name, str(e)))

if errors:
    for name, msg in errors:
        st.error(f"{name}: {msg}")

if not frames:
    st.stop()

raw_orders = pd.concat(frames, ignore_index=True)
raw_orders = raw_orders.dropna(subset=["주문일"]).sort_values("주문일")

if raw_orders.empty:
    st.error("주문일을 찾지 못했습니다. 엑셀 컬럼 구조를 확인해야 합니다.")
    st.stop()

use_phone = st.toggle(
    "전화번호까지 포함해서 더 엄격하게 고객 구분",
    value=False,
    help="기본은 이름+주소 기준입니다. 050 안심번호 때문에 쿠팡 재구매가 분리되는 것을 막기 위함입니다.",
)

customer_key_col = "전화포함고객키" if use_phone else "고객키"

# 핵심 수정:
# 네이버 상품주문번호가 여러 개여도 주문번호가 같으면 주문 1건
# 쿠팡 상품행이 여러 개여도 묶음배송번호가 같으면 주문 1건
group_cols = [
    "판매채널", "주문단위번호", "주문단위키",
    customer_key_col,
    "수취인", "수취인전화", "구매자", "구매자전화", "주소"
]

order_level = (
    raw_orders.groupby(group_cols, dropna=False)
    .agg(
        주문일=("주문일", "min"),
        상품주문번호목록=("상품주문번호", join_unique),
        상품명=("상품명", join_unique),
        총수량=("수량", "sum"),
        결제금액=("결제금액", "sum"),
        원본행수=("상품주문번호", "count"),
    )
    .reset_index()
)

order_level = order_level.rename(columns={customer_key_col: "분석고객키"})

customer = (
    order_level.groupby("분석고객키", dropna=False)
    .agg(
        고객명=("수취인", "first"),
        전화번호=("수취인전화", "first"),
        주소=("주소", "first"),
        총주문횟수=("주문단위키", pd.Series.nunique),
        첫구매일=("주문일", "min"),
        최근구매일=("주문일", "max"),
        누적구매금액=("결제금액", "sum"),
        누적수량=("총수량", "sum"),
        이용채널=("판매채널", join_unique),
        구매상품=("상품명", join_unique),
    )
    .reset_index(drop=True)
)

customer["고객구분"] = customer["총주문횟수"].apply(lambda x: "재구매" if x >= 2 else "신규")
customer["고객등급"] = customer["총주문횟수"].apply(
    lambda x: "VIP" if x >= 5 else "우수고객" if x >= 3 else "재구매" if x >= 2 else "신규"
)

today = pd.Timestamp.today().normalize()
customer["최근구매후경과일"] = (today - pd.to_datetime(customer["최근구매일"]).dt.normalize()).dt.days
customer["이탈위험"] = customer["최근구매후경과일"].apply(lambda x: "90일 이상 미구매" if x >= 90 else "")

total_raw_rows = len(raw_orders)
total_orders = len(order_level)
total_customers = len(customer)
repeat_customers = int((customer["총주문횟수"] >= 2).sum())
new_customers = total_customers - repeat_customers
repeat_rate = repeat_customers / total_customers * 100 if total_customers else 0
avg_orders = customer["총주문횟수"].mean() if total_customers else 0

cols = st.columns(6)
kpis = [
    ("원본 상품행", f"{total_raw_rows:,}행"),
    ("실제 주문", f"{total_orders:,}건"),
    ("전체 고객", f"{total_customers:,}명"),
    ("신규 고객", f"{new_customers:,}명"),
    ("재구매 고객", f"{repeat_customers:,}명"),
    ("재구매율", f"{repeat_rate:.1f}%"),
]

for col, (title, val) in zip(cols, kpis):
    with col:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{val}</div>
        </div>
        """, unsafe_allow_html=True)

st.write("")
st.markdown(
    '<div class="note">네이버 상품주문번호 여러 개가 같은 주문번호로 묶이면 실제 주문 1건으로 계산됩니다. 재구매는 고객별 실제 주문번호가 2개 이상일 때만 잡힙니다.</div>',
    unsafe_allow_html=True
)

st.write("")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 대시보드", "👤 고객별 분석", "📦 주문 단위 정리", "🧾 원본행 정리", "⬇️ 다운로드"])

with tab1:
    left, right = st.columns(2)

    with left:
        st.subheader("월별 실제 주문 추이")
        monthly = order_level.copy()
        monthly["월"] = pd.to_datetime(monthly["주문일"]).dt.to_period("M").astype(str)
        st.bar_chart(monthly.groupby("월").size())

    with right:
        st.subheader("구매횟수별 고객 수")
        repeat_bucket = customer["총주문횟수"].apply(
            lambda x: "1회" if x == 1 else "2회" if x == 2 else "3회" if x == 3 else "4회 이상"
        )
        st.bar_chart(repeat_bucket.value_counts().reindex(["1회", "2회", "3회", "4회 이상"]).fillna(0))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("채널별 실제 주문 수")
        st.dataframe(
            order_level.groupby("판매채널").size().reset_index(name="실제주문수"),
            use_container_width=True,
            hide_index=True
        )

    with c2:
        st.subheader("고객 등급")
        grade_df = customer["고객등급"].value_counts().rename_axis("등급").reset_index(name="고객수")
        st.dataframe(grade_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("고객별 구매 분석")
    grade_filter = st.multiselect(
        "고객등급 필터",
        options=sorted(customer["고객등급"].unique()),
        default=sorted(customer["고객등급"].unique()),
    )

    view = customer[customer["고객등급"].isin(grade_filter)].sort_values(
        ["총주문횟수", "최근구매일"],
        ascending=[False, False]
    )
    st.dataframe(view, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("주문 단위 정리")
    st.caption("여기서는 네이버 상품주문번호가 여러 개여도 같은 주문번호면 1행으로 묶입니다.")
    st.dataframe(
        order_level.sort_values("주문일", ascending=False),
        use_container_width=True,
        hide_index=True
    )

with tab4:
    st.subheader("원본행 정리")
    st.caption("엑셀 원본 상품행 기준입니다. 네이버 1L/500ml처럼 한 주문이 여러 행으로 나뉜 경우 여기서는 여러 행으로 보입니다.")
    st.dataframe(raw_orders.sort_values("주문일", ascending=False), use_container_width=True, hide_index=True)

with tab5:
    summary = pd.DataFrame({
        "항목": ["원본 상품행", "실제 주문", "전체 고객", "신규 고객", "재구매 고객", "재구매율", "평균 주문횟수"],
        "값": [total_raw_rows, total_orders, total_customers, new_customers, repeat_customers, f"{repeat_rate:.1f}%", f"{avg_orders:.2f}회"]
    })

    excel_bytes = to_excel_bytes(order_level, customer, raw_orders, summary)
    st.download_button(
        "분석 결과 엑셀 다운로드",
        data=excel_bytes,
        file_name=f"customer_repurchase_result_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.caption("앱은 업로드 파일을 따로 저장하지 않습니다.")
