
import re
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="식혜명가 고객 재구매 분석",
    page_icon="📦",
    layout="wide",
)

st.markdown("""
<style>
.main {background-color: #FAFAFA;}
.block-container {padding-top: 2rem;}
.kpi-card {
    background: white;
    border: 1px solid #ECECEC;
    border-radius: 18px;
    padding: 20px 22px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.kpi-title {
    color: #666;
    font-size: 14px;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 30px;
    font-weight: 800;
    color: #111;
}
.small-box {
    background: white;
    border: 1px solid #ECECEC;
    border-radius: 16px;
    padding: 18px;
}
</style>
""", unsafe_allow_html=True)


# =========================
# 기본 설정
# =========================
PASSWORD = ""  # 비밀번호를 쓰려면 예: "1234" 입력. 비워두면 로그인 없음.


def check_password():
    if not PASSWORD:
        return True
    st.title("🔒 고객 재구매 분석")
    pw = st.text_input("비밀번호", type="password")
    if pw == PASSWORD:
        return True
    if pw:
        st.error("비밀번호가 틀렸습니다.")
    return False


if not check_password():
    st.stop()


# =========================
# 유틸 함수
# =========================
def normalize_phone(x):
    if pd.isna(x):
        return ""
    s = str(x)
    s = re.sub(r"[^0-9]", "", s)
    return s


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
    cols_clean = {str(c).strip(): c for c in cols}
    for name in candidates:
        if name in cols_clean:
            return cols_clean[name]
    # 부분 포함 매칭
    for c in cols:
        cstr = str(c).strip()
        for name in candidates:
            if name in cstr:
                return c
    return None


def read_excel_safely(uploaded_file):
    try:
        return pd.read_excel(uploaded_file)
    except Exception:
        uploaded_file.seek(0)
        try:
            return pd.read_excel(uploaded_file, engine="openpyxl")
        except Exception as e:
            raise RuntimeError(
                f"엑셀을 읽지 못했습니다. 파일이 암호화되어 있거나 형식이 다를 수 있습니다. 원인: {e}"
            )


def detect_market(filename, df):
    name = filename.lower()
    if "delivery" in name or "coupang" in name or "쿠팡" in name:
        return "쿠팡"
    if "스마트스토어" in name or "smartstore" in name or "naver" in name or "네이버" in name:
        return "네이버"
    # 컬럼으로 추정
    if "묶음배송번호" in df.columns or "노출상품명(옵션명)" in df.columns:
        return "쿠팡"
    if "상품주문번호" in df.columns or "수취인연락처1" in df.columns or "주문번호" in df.columns:
        return "네이버"
    return "기타"


def standardize(df, market, filename):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    order_date_col = pick_col(df, [
        "주문일", "주문일시", "결제일", "결제일시", "발주확인일", "주문접수일", "등록일"
    ])
    order_no_col = pick_col(df, [
        "주문번호", "상품주문번호", "묶음배송번호", "주문ID", "주문 번호"
    ])
    receiver_col = pick_col(df, [
        "수취인이름", "수취인명", "수령인", "받는분", "수령자명", "수취인"
    ])
    receiver_phone_col = pick_col(df, [
        "수취인전화번호", "수취인연락처1", "수취인연락처", "수령인전화번호",
        "받는분전화번호", "수령자연락처", "배송지연락처"
    ])
    buyer_col = pick_col(df, [
        "구매자", "구매자명", "주문자명", "주문자", "구매자 이름"
    ])
    buyer_phone_col = pick_col(df, [
        "구매자전화번호", "구매자연락처", "주문자연락처", "주문자전화번호"
    ])
    address_col = pick_col(df, [
        "수취인 주소", "배송지", "배송지주소", "수취인주소", "주소", "통합배송지"
    ])
    product_col = pick_col(df, [
        "노출상품명(옵션명)", "상품명", "등록상품명", "상품명/옵션명", "제품명"
    ])
    qty_col = pick_col(df, [
        "구매수(수량)", "수량", "구매수량", "주문수량"
    ])
    amount_col = pick_col(df, [
        "결제액", "결제금액", "총 결제금액", "상품별 총 주문금액", "총주문금액", "정산예정금액"
    ])

    out = pd.DataFrame()
    out["판매채널"] = market
    out["원본파일"] = filename
    out["주문번호"] = df[order_no_col] if order_no_col else ""
    out["주문일"] = pd.to_datetime(df[order_date_col], errors="coerce") if order_date_col else pd.NaT
    out["수취인"] = df[receiver_col].map(normalize_text) if receiver_col else ""
    out["수취인전화"] = df[receiver_phone_col].map(normalize_phone) if receiver_phone_col else ""
    out["구매자"] = df[buyer_col].map(normalize_text) if buyer_col else ""
    out["구매자전화"] = df[buyer_phone_col].map(normalize_phone) if buyer_phone_col else ""
    out["주소"] = df[address_col].map(normalize_address) if address_col else ""
    out["상품명"] = df[product_col].map(normalize_text) if product_col else ""
    out["수량"] = pd.to_numeric(df[qty_col], errors="coerce").fillna(1).astype(int) if qty_col else 1
    out["결제금액"] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0).astype(int) if amount_col else 0

    # 고객 식별키
    # 쿠팡 안심번호는 주문마다 바뀔 수 있어 주소+수취인을 같이 사용.
    name_key = out["수취인"].where(out["수취인"] != "", out["구매자"])
    phone_key = out["수취인전화"].where(out["수취인전화"] != "", out["구매자전화"])
    address_key = out["주소"]

    out["고객키"] = (
        name_key.fillna("").astype(str).str.strip()
        + "|"
        + phone_key.fillna("").astype(str).str.strip()
        + "|"
        + address_key.fillna("").astype(str).str.strip()
    )

    # 전화번호가 없거나 050 안심번호라면 이름+주소 중심 보조키
    out["보조고객키"] = (
        name_key.fillna("").astype(str).str.strip()
        + "|"
        + address_key.fillna("").astype(str).str.strip()
    )

    # 고객키가 너무 빈약하면 제외
    out = out[(name_key != "") | (phone_key != "") | (address_key != "")]
    return out


def classify_grade(n, last_date):
    if n >= 5:
        return "VIP"
    if n >= 3:
        return "우수고객"
    if n >= 2:
        return "재구매"
    return "신규"


def to_excel_bytes(order_df, customer_df, summary_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="요약")
        customer_df.to_excel(writer, index=False, sheet_name="고객별분석")
        order_df.to_excel(writer, index=False, sheet_name="주문원본정리")
    output.seek(0)
    return output.getvalue()


# =========================
# 화면
# =========================
st.title("📦 식혜명가 고객 재구매 분석")
st.caption("쿠팡 DeliveryList / 네이버 스마트스토어 발주·발송 엑셀을 올리면 신규·재구매·VIP 고객을 자동 계산합니다.")

with st.expander("사용법", expanded=False):
    st.write("""
1. 쿠팡 엑셀은 `DeliveryList...xlsx` 파일을 올립니다.  
2. 네이버는 `스마트스토어_선택주문발주발송관리...xlsx` 파일을 올립니다.  
3. 여러 파일을 한 번에 올려도 됩니다.  
4. 결과는 화면에서 보고, 엑셀로 다운로드할 수 있습니다.
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
            raw = read_excel_safely(f)

        market = detect_market(f.name, raw)
        std = standardize(raw, market, f.name)
        frames.append(std)

    except Exception as e:
        errors.append((f.name, str(e)))

if errors:
    for name, msg in errors:
        st.error(f"{name}: {msg}")

if not frames:
    st.stop()

orders = pd.concat(frames, ignore_index=True)
orders = orders.dropna(subset=["주문일"])
orders = orders.sort_values("주문일")

# 같은 주문번호가 여러 상품행으로 나뉜 경우 주문 단위로 집계
group_cols = ["판매채널", "주문번호", "고객키", "보조고객키", "수취인", "수취인전화", "구매자", "구매자전화", "주소", "주문일"]
order_level = orders.groupby(group_cols, dropna=False, as_index=False).agg(
    상품명=("상품명", lambda x: " / ".join([v for v in x.astype(str).unique() if v and v != "nan"])[:300]),
    총수량=("수량", "sum"),
    결제금액=("결제금액", "sum"),
)

# 고객키 기준 선택
use_assist_key = st.toggle(
    "쿠팡 안심번호 보정: 이름+주소 기준으로 고객 묶기",
    value=True,
    help="쿠팡 050 안심번호는 주문마다 바뀔 수 있어 이름+주소 기준이 재구매 분석에 더 유리할 수 있습니다.",
)

key_col = "보조고객키" if use_assist_key else "고객키"
order_level["분석고객키"] = order_level[key_col]

customer = order_level.groupby("분석고객키", as_index=False).agg(
    고객명=("수취인", "first"),
    전화번호=("수취인전화", "first"),
    주소=("주소", "first"),
    총주문횟수=("주문번호", "nunique"),
    첫구매일=("주문일", "min"),
    최근구매일=("주문일", "max"),
    누적구매금액=("결제금액", "sum"),
    누적수량=("총수량", "sum"),
    이용채널=("판매채널", lambda x: ", ".join(sorted(set(x.astype(str))))),
)

customer["고객구분"] = customer["총주문횟수"].apply(lambda n: "재구매" if n >= 2 else "신규")
customer["고객등급"] = customer["총주문횟수"].apply(lambda n: classify_grade(n, None))
customer["최근구매일"] = pd.to_datetime(customer["최근구매일"])
customer["첫구매일"] = pd.to_datetime(customer["첫구매일"])
customer["구매간격일"] = (customer["최근구매일"] - customer["첫구매일"]).dt.days

today = pd.Timestamp.today().normalize()
customer["최근구매후경과일"] = (today - customer["최근구매일"].dt.normalize()).dt.days
customer["이탈위험"] = customer["최근구매후경과일"].apply(lambda x: "90일 이상 미구매" if x >= 90 else "")

total_orders = len(order_level)
total_customers = len(customer)
repeat_customers = int((customer["총주문횟수"] >= 2).sum())
new_customers = total_customers - repeat_customers
repeat_rate = repeat_customers / total_customers * 100 if total_customers else 0
avg_orders = customer["총주문횟수"].mean() if total_customers else 0

c1, c2, c3, c4, c5 = st.columns(5)
cards = [
    ("전체 주문", f"{total_orders:,}건"),
    ("전체 고객", f"{total_customers:,}명"),
    ("신규 고객", f"{new_customers:,}명"),
    ("재구매 고객", f"{repeat_customers:,}명"),
    ("재구매율", f"{repeat_rate:.1f}%"),
]
for col, (title, value) in zip([c1, c2, c3, c4, c5], cards):
    with col:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """, unsafe_allow_html=True)

st.write("")

tab1, tab2, tab3, tab4 = st.tabs(["📊 대시보드", "👤 고객별 분석", "📦 주문 정리", "⬇️ 다운로드"])

with tab1:
    left, right = st.columns(2)

    with left:
        st.subheader("월별 주문 추이")
        monthly = order_level.copy()
        monthly["월"] = monthly["주문일"].dt.to_period("M").astype(str)
        chart_monthly = monthly.groupby("월").size().reset_index(name="주문수")
        st.bar_chart(chart_monthly.set_index("월"))

    with right:
        st.subheader("구매횟수별 고객 수")
        bins = customer["총주문횟수"].apply(lambda x: "1회" if x == 1 else "2회" if x == 2 else "3회" if x == 3 else "4회 이상")
        count_by_repeat = bins.value_counts().reindex(["1회", "2회", "3회", "4회 이상"]).fillna(0).astype(int)
        st.bar_chart(count_by_repeat)

    left2, right2 = st.columns(2)

    with left2:
        st.subheader("채널별 주문 수")
        channel = order_level.groupby("판매채널").size().reset_index(name="주문수")
        st.dataframe(channel, use_container_width=True, hide_index=True)

    with right2:
        st.subheader("고객 등급")
        grade = customer["고객등급"].value_counts().reset_index()
        grade.columns = ["등급", "고객수"]
        st.dataframe(grade, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("고객별 구매 분석")
    grade_filter = st.multiselect(
        "고객등급 필터",
        options=sorted(customer["고객등급"].unique()),
        default=sorted(customer["고객등급"].unique()),
    )
    view = customer[customer["고객등급"].isin(grade_filter)].sort_values(
        ["총주문횟수", "최근구매일"], ascending=[False, False]
    )
    st.dataframe(
        view[[
            "고객명", "전화번호", "총주문횟수", "고객구분", "고객등급",
            "첫구매일", "최근구매일", "최근구매후경과일",
            "누적구매금액", "누적수량", "이용채널", "주소", "이탈위험"
        ]],
        use_container_width=True,
        hide_index=True,
    )

with tab3:
    st.subheader("주문 단위 정리")
    st.dataframe(
        order_level.sort_values("주문일", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with tab4:
    summary = pd.DataFrame({
        "항목": ["전체 주문", "전체 고객", "신규 고객", "재구매 고객", "재구매율", "평균 주문횟수"],
        "값": [total_orders, total_customers, new_customers, repeat_customers, f"{repeat_rate:.1f}%", f"{avg_orders:.2f}회"]
    })

    excel_bytes = to_excel_bytes(order_level, customer, summary)
    st.download_button(
        label="분석 결과 엑셀 다운로드",
        data=excel_bytes,
        file_name=f"customer_repurchase_result_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.caption("개인정보 보호를 위해 앱 코드는 업로드 파일을 따로 저장하지 않습니다.")
