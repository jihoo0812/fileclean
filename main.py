"""
파일 사용 현황 분석 & 불필요한 파일 정리 도구
------------------------------------------------
지정한 폴더를 스캔하여 파일 크기/종류/최근 접근일 등을 보여주고,
사용자가 선택한 파일을 삭제(또는 휴지통으로 이동)할 수 있게 해주는 Streamlit 앱.

실행 방법:
    streamlit run main.py
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# --------------------------------------------------------------------------
# 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="파일 사용현황 & 정리 도구",
    page_icon="🗂️",
    layout="wide",
)

TRASH_DIR = Path.home() / ".file_cleaner_trash"


# --------------------------------------------------------------------------
# 유틸 함수
# --------------------------------------------------------------------------
def human_readable_size(num_bytes: float) -> str:
    """바이트를 사람이 읽기 좋은 단위로 변환"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


@st.cache_data(show_spinner=False)
def scan_directory(root_path: str, max_files: int = 200_000):
    """지정한 폴더 이하를 재귀적으로 스캔해서 파일 정보 목록을 반환"""
    records = []
    errors = []
    root = Path(root_path)

    if not root.exists():
        return pd.DataFrame(), [f"경로가 존재하지 않습니다: {root_path}"]

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # 숨김 폴더/시스템 폴더는 건너뛰기 (원하면 옵션으로 뺄 수 있음)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for fname in filenames:
            if len(records) >= max_files:
                errors.append(
                    f"파일 수가 너무 많아 {max_files:,}개까지만 스캔했습니다."
                )
                return pd.DataFrame(records), errors

            fpath = Path(dirpath) / fname
            try:
                stat = fpath.stat()
                records.append(
                    {
                        "경로": str(fpath),
                        "파일명": fname,
                        "확장자": fpath.suffix.lower() or "(없음)",
                        "폴더": os.path.relpath(dirpath, root) if dirpath != str(root) else ".",
                        "크기(bytes)": stat.st_size,
                        "수정일": datetime.fromtimestamp(stat.st_mtime),
                        "최근접근일": datetime.fromtimestamp(stat.st_atime),
                    }
                )
            except (OSError, PermissionError) as e:
                errors.append(f"{fpath}: {e}")

    return pd.DataFrame(records), errors


def delete_files(paths, to_trash: bool = True):
    """파일들을 삭제하거나 휴지통 폴더로 이동"""
    results = []
    if to_trash:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)

    for p in paths:
        src = Path(p)
        try:
            if to_trash:
                dest = TRASH_DIR / f"{int(time.time())}_{src.name}"
                shutil.move(str(src), str(dest))
            else:
                src.unlink()
            results.append((p, True, ""))
        except Exception as e:
            results.append((p, False, str(e)))
    return results


# --------------------------------------------------------------------------
# 사이드바 - 스캔 설정
# --------------------------------------------------------------------------
st.sidebar.header("⚙️ 스캔 설정")

default_path = str(Path.home())
target_path = st.sidebar.text_input("스캔할 폴더 경로", value=default_path)

scan_btn = st.sidebar.button("🔍 스캔 시작", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption(
    "⚠️ 삭제는 되돌리기 어렵습니다. 기본값은 '휴지통 폴더로 이동'이며, "
    f"`{TRASH_DIR}` 에 보관됩니다. 완전 삭제 옵션도 선택할 수 있습니다."
)

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.errors = []

if scan_btn:
    with st.spinner("파일을 스캔하는 중입니다..."):
        df, errors = scan_directory(target_path)
        st.session_state.df = df
        st.session_state.errors = errors

df = st.session_state.df

# --------------------------------------------------------------------------
# 메인 화면
# --------------------------------------------------------------------------
st.title("🗂️ 파일 사용현황 & 정리 도구")

if df.empty:
    st.info("왼쪽 사이드바에서 폴더 경로를 입력하고 **스캔 시작**을 눌러주세요.")
    st.stop()

if st.session_state.errors:
    with st.expander(f"⚠️ 스캔 중 경고/오류 {len(st.session_state.errors)}건"):
        for e in st.session_state.errors[:100]:
            st.write(e)

# ---- 요약 지표 ----
total_size = df["크기(bytes)"].sum()
total_files = len(df)
col1, col2, col3 = st.columns(3)
col1.metric("총 파일 수", f"{total_files:,} 개")
col2.metric("총 용량", human_readable_size(total_size))
col3.metric("스캔 경로", target_path)

st.markdown("---")

# ---- 필터 ----
st.subheader("🔎 필터")
f1, f2, f3 = st.columns(3)

with f1:
    ext_options = sorted(df["확장자"].unique().tolist())
    selected_ext = st.multiselect("확장자 선택 (미선택 시 전체)", ext_options)

with f2:
    min_size_mb = st.number_input("최소 파일 크기 (MB)", min_value=0.0, value=0.0, step=1.0)

with f3:
    days_unused = st.number_input(
        "최근 N일 이상 접근 안 한 파일만 보기 (0 = 전체)",
        min_value=0, value=0, step=1,
    )

filtered = df.copy()
if selected_ext:
    filtered = filtered[filtered["확장자"].isin(selected_ext)]
if min_size_mb > 0:
    filtered = filtered[filtered["크기(bytes)"] >= min_size_mb * 1024 * 1024]
if days_unused > 0:
    cutoff = datetime.now().timestamp() - days_unused * 86400
    filtered = filtered[filtered["최근접근일"].apply(lambda d: d.timestamp()) < cutoff]

st.caption(f"필터 결과: {len(filtered):,} 개 파일 / {human_readable_size(filtered['크기(bytes)'].sum())}")

st.markdown("---")

# ---- 시각화 ----
st.subheader("📊 용량 분석")

vcol1, vcol2 = st.columns(2)

with vcol1:
    by_ext = (
        df.groupby("확장자")["크기(bytes)"].sum().sort_values(ascending=False).head(15).reset_index()
    )
    fig1 = px.bar(
        by_ext, x="확장자", y="크기(bytes)",
        title="확장자별 용량 (상위 15개)",
        labels={"크기(bytes)": "용량 (bytes)"},
    )
    st.plotly_chart(fig1, use_container_width=True)

with vcol2:
    by_folder = (
        df.groupby("폴더")["크기(bytes)"].sum().sort_values(ascending=False).head(15).reset_index()
    )
    fig2 = px.bar(
        by_folder, x="폴더", y="크기(bytes)",
        title="폴더별 용량 (상위 15개)",
        labels={"크기(bytes)": "용량 (bytes)"},
    )
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ---- 파일 목록 & 삭제 ----
st.subheader("🗑️ 파일 선택 및 삭제")

sort_by = st.selectbox("정렬 기준", ["크기(bytes)", "최근접근일", "수정일"], index=0)
show_df = filtered.sort_values(sort_by, ascending=False).reset_index(drop=True)
show_df.insert(0, "삭제선택", False)

edited = st.data_editor(
    show_df,
    column_config={
        "삭제선택": st.column_config.CheckboxColumn("삭제선택"),
        "크기(bytes)": st.column_config.NumberColumn("크기", format="%d bytes"),
    },
    disabled=[c for c in show_df.columns if c != "삭제선택"],
    use_container_width=True,
    height=420,
)

to_delete = edited[edited["삭제선택"]]

st.write(
    f"선택된 파일: **{len(to_delete)}개** "
    f"(총 {human_readable_size(to_delete['크기(bytes)'].sum())})"
)

del_mode = st.radio(
    "삭제 방식",
    ["휴지통 폴더로 이동 (안전, 권장)", "완전 삭제 (복구 불가)"],
    horizontal=True,
)

if len(to_delete) > 0:
    confirm = st.checkbox("선택한 파일을 정말 삭제하겠습니다.")
    if st.button("🗑️ 선택한 파일 삭제 실행", type="primary", disabled=not confirm):
        to_trash = del_mode.startswith("휴지통")
        results = delete_files(to_delete["경로"].tolist(), to_trash=to_trash)
        success = [r for r in results if r[1]]
        failed = [r for r in results if not r[1]]

        st.success(f"{len(success)}개 파일 처리 완료.")
        if failed:
            st.error(f"{len(failed)}개 파일 처리 실패:")
            for path, _, err in failed:
                st.write(f"- {path}: {err}")

        # 재스캔해서 화면 갱신
        with st.spinner("목록을 갱신하는 중..."):
            new_df, new_errors = scan_directory(target_path)
            st.session_state.df = new_df
            st.session_state.errors = new_errors
        st.rerun()
else:
    st.caption("삭제할 파일을 표에서 체크박스로 선택하세요.")
