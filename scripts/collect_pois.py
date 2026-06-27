"""
collect_pois.py — 종로구 POI 수집 (카카오 로컬 '카테고리 검색' API)

카카오 카테고리 검색은 한 번의 검색(rect)당 최대 45건(15건 × 3페이지)만 돌려준다.
따라서 종로구 bbox를 격자로 나눠 검색하고, 어떤 셀의 실제 결과(total_count)가
45를 넘으면 그 셀을 다시 4등분해 재귀적으로 파고든다 → 누락 최소화.

수집 결과는 place_id로 중복 제거 후 data/raw/jongno_pois.parquet 로 저장.

사용:
    python scripts/collect_pois.py
필요:
    .env 의 KAKAO_REST_API_KEY  (pip install requests pandas pyarrow python-dotenv)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas 가 필요합니다:  pip install pandas pyarrow")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv 가 필요합니다:  pip install python-dotenv")


# ──────────────────────────────────────────────────────────────────────────
# 설정 (필요하면 여기만 고치면 됨)
# ──────────────────────────────────────────────────────────────────────────

# 종로구를 감싸는 대략적 bbox (min_lon, min_lat, max_lon, max_lat).
# 카카오 rect 검색은 이 사각형 안의 좌표만 돌려준다. 정확한 '구 경계 클리핑'은
# 후처리 단계(geopandas)에서 별도로 한다 — 여기서는 envelope 로 충분.
JONGNO_BBOX = (126.955, 37.566, 127.025, 37.645)

# 검색할 카테고리 그룹 코드 → 사람이 읽을 이름
CATEGORIES = {
    "FD6": "음식점",
    "CE7": "카페",
    "AT4": "관광명소",
}

# 시작 격자 분할 수 (bbox 를 가로 NX × 세로 NY 로 1차 분할 후, 셀마다 재귀)
GRID_NX = 4
GRID_NY = 4

# 한 셀의 결과가 45건을 넘으면 4분할 재귀. 너무 깊어지지 않도록 한계.
MAX_DEPTH = 6

# 카카오 API 한 페이지 크기(최대 15), 페이지 한계(45건 = 3페이지)
PAGE_SIZE = 15
MAX_PAGE = 3
# 카카오가 한 검색에서 돌려주는 최대 건수 → 이걸 넘으면 셀을 4분할
CATEGORIES_CAP = PAGE_SIZE * MAX_PAGE  # = 45

# API 호출 사이 딜레이(초) — rate limit 대비
REQUEST_DELAY = 0.2
# 429(요청 과다) 응답 시 대기 후 재시도
RETRY_WAIT = 2.0
MAX_RETRIES = 3

KAKAO_URL = "https://dapi.kakao.com/v2/local/search/category.json"

# 저장 경로 (이 스크립트는 scripts/ 안에 있음 → 레포 루트 = 부모의 부모)
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "raw" / "jongno_pois.parquet"


# ──────────────────────────────────────────────────────────────────────────
# 카카오 호출
# ──────────────────────────────────────────────────────────────────────────

def _rect_param(cell: tuple[float, float, float, float]) -> str:
    """(min_lon, min_lat, max_lon, max_lat) → 카카오 rect 문자열."""
    min_lon, min_lat, max_lon, max_lat = cell
    return f"{min_lon},{min_lat},{max_lon},{max_lat}"


def fetch_page(session: requests.Session, headers: dict,
               code: str, cell: tuple, page: int) -> dict:
    """한 페이지 호출. 429 면 잠시 쉬었다 재시도. JSON(dict) 반환."""
    params = {
        "category_group_code": code,
        "rect": _rect_param(cell),
        "page": page,
        "size": PAGE_SIZE,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.get(KAKAO_URL, headers=headers, params=params, timeout=10)
        if resp.status_code == 429:
            print(f"    · 429 rate limit — {RETRY_WAIT}s 대기 후 재시도 ({attempt}/{MAX_RETRIES})")
            time.sleep(RETRY_WAIT)
            continue
        if resp.status_code == 401:
            sys.exit(f"카카오 인증 실패(401): KAKAO_REST_API_KEY 값을 확인하세요.\n  본문: {resp.text}")
        if resp.status_code == 403:
            sys.exit("카카오 권한 오류(403): 앱에서 '카카오맵' 서비스가 꺼져 있을 수 있습니다.\n"
                     "  → developers.kakao.com 콘솔 > 제품 설정 > 카카오맵 활성화(ON) 후 다시 실행.\n"
                     f"  본문: {resp.text}")
        if not resp.ok:
            # 그 밖의 4xx/5xx 도 카카오 에러 본문을 그대로 보여줌
            print(f"    · HTTP {resp.status_code} | {resp.text[:300]}")
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.json()
    raise RuntimeError(f"재시도 초과: code={code} cell={cell} page={page}")


def search_cell(session, headers, code: str, cell: tuple, depth: int,
                results: dict, stats: dict) -> None:
    """한 셀을 검색해 results(dict: id→record)에 누적. 45건 초과면 4분할 재귀."""
    first = fetch_page(session, headers, code, cell, 1)
    stats["requests"] += 1
    meta = first["meta"]
    total = meta["total_count"]

    if total == 0:
        return

    # 1페이지 문서 적재
    _absorb(first["documents"], code, results)

    # 2~3페이지 (pageable 범위 안에서만)
    page = 1
    is_end = meta["is_end"]
    while not is_end and page < MAX_PAGE:
        page += 1
        data = fetch_page(session, headers, code, cell, page)
        stats["requests"] += 1
        _absorb(data["documents"], code, results)
        is_end = data["meta"]["is_end"]

    # 실제 결과가 45건(=페이지 한계)을 넘으면 이 셀은 일부만 본 것 → 4분할 재귀
    if total > CATEGORIES_CAP and depth < MAX_DEPTH:
        stats["splits"] += 1
        for sub in _quad_split(cell):
            search_cell(session, headers, code, sub, depth + 1, results, stats)


def _absorb(documents: list, code: str, results: dict) -> None:
    """카카오 문서 리스트를 표준 레코드로 변환해 id 기준 중복 제거 누적."""
    for d in documents:
        pid = d["id"]
        if pid in results:
            continue  # place_id 중복 제거
        results[pid] = {
            "place_id": pid,
            "name": d.get("place_name", ""),
            "category_group_code": code,
            "category_main": CATEGORIES.get(code, code),
            "category_name": d.get("category_name", ""),
            "phone": d.get("phone", ""),
            "address_name": d.get("address_name", ""),
            "road_address_name": d.get("road_address_name", ""),
            "lon": float(d["x"]),
            "lat": float(d["y"]),
            "place_url": d.get("place_url", ""),
        }


def _quad_split(cell: tuple) -> list[tuple]:
    """사각형을 4등분."""
    min_lon, min_lat, max_lon, max_lat = cell
    mid_lon = (min_lon + max_lon) / 2
    mid_lat = (min_lat + max_lat) / 2
    return [
        (min_lon, min_lat, mid_lon, mid_lat),
        (mid_lon, min_lat, max_lon, mid_lat),
        (min_lon, mid_lat, mid_lon, max_lat),
        (mid_lon, mid_lat, max_lon, max_lat),
    ]


def _initial_grid(bbox: tuple, nx: int, ny: int) -> list[tuple]:
    """bbox 를 nx × ny 격자로 1차 분할."""
    min_lon, min_lat, max_lon, max_lat = bbox
    dx = (max_lon - min_lon) / nx
    dy = (max_lat - min_lat) / ny
    cells = []
    for i in range(nx):
        for j in range(ny):
            cells.append((
                min_lon + i * dx,
                min_lat + j * dy,
                min_lon + (i + 1) * dx,
                min_lat + (j + 1) * dy,
            ))
    return cells


# ──────────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        sys.exit(".env 에 KAKAO_REST_API_KEY 가 비어 있습니다.")

    headers = {"Authorization": f"KakaoAK {key}"}
    session = requests.Session()

    results: dict = {}
    grid = _initial_grid(JONGNO_BBOX, GRID_NX, GRID_NY)

    print("=" * 60)
    print("종로구 POI 수집 시작")
    print(f"  bbox        : {JONGNO_BBOX}")
    print(f"  카테고리     : {', '.join(f'{c}({n})' for c, n in CATEGORIES.items())}")
    print(f"  시작 격자    : {GRID_NX}×{GRID_NY} = {len(grid)}셀, 최대 재귀깊이 {MAX_DEPTH}")
    print("=" * 60)

    for code, name in CATEGORIES.items():
        stats = {"requests": 0, "splits": 0}
        before = len(results)
        print(f"\n[{code}] {name} 수집 중...")
        for idx, cell in enumerate(grid, 1):
            search_cell(session, headers, code, cell, 0, results, stats)
            print(f"  · 격자 {idx}/{len(grid)} 완료 | 누적 POI {len(results)} "
                  f"| 호출 {stats['requests']} | 분할 {stats['splits']}", end="\r")
        added = len(results) - before
        print(f"\n  → {name}: 신규 {added}건 (API 호출 {stats['requests']}, 셀 분할 {stats['splits']})")

    print(f"\n총 수집(중복 제거 후): {len(results)} POI")

    # 저장
    df = pd.DataFrame(list(results.values()))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"저장 완료 → {OUTPUT_PATH.relative_to(REPO_ROOT)}  ({len(df)} rows)")

    # 카테고리별 요약
    if not df.empty:
        print("\n카테고리별 집계:")
        for name, cnt in df["category_main"].value_counts().items():
            print(f"  - {name}: {cnt}")


if __name__ == "__main__":
    main()
