# 어제의 박스오피스 — KOBIS 일별 박스오피스 API
import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="박스오피스 대시보드", page_icon="🎬", layout="wide")

# 인증키는 비밀 금고(secrets)에서 불러온다 — 코드에 직접 쓰지 않는다
API_KEY = st.secrets["KOBIS_KEY"]
URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# '어제'를 한국 시간 기준으로 계산한다 (배포 서버의 시계는 한국 시간이 아니다)
KST = datetime.timezone(datetime.timedelta(hours=9))
today_kst = datetime.datetime.now(KST).date()
yesterday = today_kst - datetime.timedelta(days=1)


@st.cache_data(ttl=3600)  # 같은 날짜는 한 시간 동안 기억해 두고 API를 다시 부르지 않는다
def fetch_boxoffice(date_str):
    """KOBIS API에서 해당 날짜의 일별 박스오피스를 받아 온다."""
    params = {"key": API_KEY, "targetDt": date_str}
    res = requests.get(URL, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


# ================= 사이드바 =================
st.sidebar.header("⚙️ 조회 설정")

selected_date = st.sidebar.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday,
    max_value=yesterday,  # 어제까지만 선택 가능 (오늘/미래는 집계가 안 끝났으므로)
)
target_dt = selected_date.strftime("%Y%m%d")

st.sidebar.divider()

top_n = st.sidebar.slider("그래프에 표시할 영화 개수", min_value=3, max_value=10, value=5)

color_theme = st.sidebar.selectbox(
    "그래프 색상 테마",
    options=["Blues", "Reds", "Greens", "Purples", "Oranges"],
    index=0,
)

st.sidebar.divider()
st.sidebar.caption("데이터 출처: KOBIS 영화진흥위원회 open API")

# ================= 메인 화면 =================
st.title("🎬 박스오피스 대시보드")
st.caption(f"조회 날짜: {selected_date}")

try:
    data = fetch_boxoffice(target_dt)
except requests.RequestException:
    st.error("서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 새로고침해 주세요.")
    st.stop()

# 인증키가 틀리면 상태코드는 200이지만 faultInfo 상자가 온다
if "faultInfo" in data:
    st.error(f"API가 오류를 돌려주었습니다: {data['faultInfo'].get('message', '')}")
    st.info("비밀 금고(secrets)의 KOBIS_KEY 값이 올바른지 확인해 주세요.")
    st.stop()

movies = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

# 영화 목록이 비어서 오면 — 아직 집계 전인 날짜다
if not movies:
    st.warning("영화 목록이 비어 있습니다. 아직 집계 전인 날짜는 아닌지 확인해 주세요.")
    st.stop()

df = pd.DataFrame(movies)

# 숫자가 글자로 오므로 숫자로 바꿔야 정렬과 그래프에 쓸 수 있다
for col in ["rank", "audiCnt", "audiAcc", "scrnCnt", "rankInten"]:
    df[col] = pd.to_numeric(df[col])


# 순위 변동을 화살표 문자열로 바꾸는 함수
def rank_change_text(row):
    """rankOldAndNew, rankInten 값을 보고 순위 변동을 사람이 읽기 좋은 문자열로 바꾼다."""
    if row["rankOldAndNew"] == "NEW":
        return "🆕 신규"
    inten = row["rankInten"]
    if inten > 0:
        return f"🔺 {inten}"
    elif inten < 0:
        return f"🔻 {abs(inten)}"
    else:
        return "➖ 0"

df["순위변동"] = df.apply(rank_change_text, axis=1)

top = df.sort_values("rank").iloc[0]

# ================= 탭 구성 =================
tab_summary, tab_table, tab_chart = st.tabs(["🏆 요약", "📋 순위표", "📊 그래프"])

# ---------- 탭 1: 요약 ----------
with tab_summary:
    st.subheader(f"🥇 1위 — {top['movieNm']} ({top['순위변동']})")
    c1, c2, c3 = st.columns(3)
    c1.metric("관객수", f"{top['audiCnt']:,}명")
    c2.metric("누적 관객수", f"{top['audiAcc']:,}명")
    c3.metric("스크린수", f"{top['scrnCnt']:,}개")

    st.divider()

    # 신규 진입작 강조
    new_movies = df[df["rankOldAndNew"] == "NEW"]
    if not new_movies.empty:
        st.subheader("🆕 오늘의 신규 진입작")
        for _, row in new_movies.sort_values("rank").iterrows():
            st.info(f"**{row['rank']}위 — {row['movieNm']}** (관객수 {row['audiCnt']:,}명)")
    else:
        st.caption("오늘은 신규 진입작이 없습니다.")

# ---------- 탭 2: 순위표 ----------
with tab_table:
    keyword = st.text_input("🔍 영화명으로 검색해 보세요", placeholder="예: 범죄도시")

    table_df = df.sort_values("rank")
    if keyword:
        table_df = table_df[table_df["movieNm"].str.contains(keyword, case=False, na=False)]
        if table_df.empty:
            st.info(f"'{keyword}'와(과) 일치하는 영화가 없습니다.")

    def rank_with_medal(rank):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        return f"{medals.get(rank, '')} {rank}".strip()

    table = table_df.copy()
    table["순위"] = table["rank"].apply(rank_with_medal)
    table = table[["순위", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt", "순위변동"]]
    table.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수", "순위변동"]

    # 순위변동에 따라 글자색을 다르게 칠하는 스타일 함수
    def color_rank_change(val):
        if "🔺" in val:
            return "color: red; font-weight: bold;"
        elif "🔻" in val:
            return "color: blue; font-weight: bold;"
        elif "🆕" in val:
            return "color: green; font-weight: bold;"
        return ""

    styled_table = table.style.map(color_rank_change, subset=["순위변동"])

    st.dataframe(
        styled_table,
        hide_index=True,
        width="stretch",
        column_config={
            "관객수": st.column_config.NumberColumn(format="%d명"),
            "누적관객": st.column_config.ProgressColumn(
                format="%d명",
                min_value=0,
                max_value=int(df["audiAcc"].max()),
            ),
        },
    )

# ---------- 탭 3: 그래프 ----------
with tab_chart:
    st.subheader(f"📊 관객수 상위 {top_n}편")
    top_movies = df.sort_values("audiCnt", ascending=False).head(top_n)

    fig = px.bar(
        top_movies,
        x="movieNm",
        y="audiCnt",
        color="audiCnt",
        color_continuous_scale=color_theme,
        labels={"movieNm": "영화명", "audiCnt": "관객수"},
        text_auto=True,
    )
    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")

    st.divider()

    st.subheader("🎟️ 스크린수 대비 관객수")
    fig2 = px.scatter(
        df,
        x="scrnCnt",
        y="audiCnt",
        size="audiAcc",
        color="rank",
        hover_name="movieNm",
        labels={"scrnCnt": "스크린수", "audiCnt": "관객수", "rank": "순위"},
        color_continuous_scale=color_theme,
    )
    st.plotly_chart(fig2, width="stretch")
