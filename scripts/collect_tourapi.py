"""
collect_tourapi.py — 한국관광공사 TourAPI 로 관광지 보강 + 기존 노드와 병합

카카오 카테고리 수집에서 빠진 핵심 앵커(종묘·조계사·탑골공원 등)를 보강한다.
한국관광공사 '국문 관광정보 서비스_GW'(KorService2) areaBasedList2 사용.

입력 : data/processed/pois_capped.parquet   (787 노드)
출력 : data/processed/pois_final.parquet     (787 + 신규 관광지, 중복 제거)

수집 범위
  서울(areaCode=1) × 대상 구(sigunguCode) × contentTypeId {12 관광지, 14 문화시설, 15 축제}
  좌표(mapx=경도, mapy=위도)·이름(title)·종류 확보.

중복 제거
  기존 노드와 '이름(공백 제거) 일치' 또는 'DEDUP_METERS 이내 + 이름 포함관계' 면 동일 장소로 보고 skip.
  (예: 카카오의 '경복궁' 과 TourAPI '경복궁' 중복 방지)

⚠️ TourAPI 키 주의
  - 디코딩 키(일반 문자) → requests params 로 넘기면 자동 인코딩.
  - 인코딩 키(%2B 등 포함) → 그대로 URL 에 붙여야 함(이중 인코딩 방지).
    이 스크립트는 키에 '%' 가 있으면 인코딩 키로 보고 수동 처리.
  - 인증 실패 시 HTTP 본문을 그대로 출력. (방금 발급한 키는 활성화에 시간이 걸려 처음엔 실패 가능)

사용:
    python scripts/collect_tourapi.py
필요:
    .env 의 TOURAPI_SERVICE_KEY,  pip install requests pandas pyarrow python-dotenv pyproj
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _ensure_proj_data() -> None:
    """PROJ 데이터 경로 자동 설정 (pyproj 변환 안정화)."""
    prefix = Path(sys.prefix)
    if not os.environ.get("PROJ_DATA"):
        for cand in (prefix / "Library" / "share" / "proj", prefix / "share" / "proj"):
            if cand.is_dir():
                os.environ["PROJ_DATA"] = str(cand)
                break


_ensure_proj_data()

import requests

try:
    import numpy as np
    import pandas as pd
except ImportError:
    sys.exit("numpy/pandas 가 필요합니다:  pip install numpy pandas pyarrow")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv 가 필요합니다:  pip install python-dotenv")

try:
    from pyproj import Transformer
except ImportError:
    sys.exit("pyproj 가 필요합니다:  pip install pyproj")


# ──────────────────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "data" / "processed" / "pois_capped.parquet"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "pois_final.parquet"

# KorService2 (국문 관광정보 서비스_GW)
BASE_URL = "https://apis.data.go.kr/B551011/KorService2/areaBasedList2"

AREA_CODE_SEOUL = 1
# 서울 자치구 TourAPI sigunguCode (대상 구만)
SIGUNGU_CODES = {
    "종로구": 23,
    "중구": 24,
    "서대문구": 14,
    "성북구": 17,
    "은평구": 22,
}

# contentTypeId → category_main 라벨
# v1: 관광지(12)만 수집 (문화시설 14·축제 15 는 제외 — 노드 증가/노이즈 억제).
CONTENT_TYPES = {
    12: "관광명소",   # 관광지
}

NUM_OF_ROWS = 100
REQUEST_DELAY = 0.2
DEDUP_METERS = 80          # 이 거리 안 + 이름 포함관계면 동일 장소로 간주

CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:5179"

# 누락 여부를 확인할 핵심 앵커
ANCHOR_KEYWORDS = ["종묘", "조계사", "탑골", "보신각", "경복궁", "창덕궁", "운현궁"]


# ──────────────────────────────────────────────────────────────────────────
# TourAPI 호출
# ──────────────────────────────────────────────────────────────────────────

def tour_get(session: requests.Session, params: dict, key: str) -> requests.Response:
    """serviceKey 형태(인코딩/디코딩)에 따라 안전하게 GET."""
    if "%" in key:
        # 이미 인코딩된 키 → URL 에 그대로 붙이고, 나머지 params 만 requests 가 인코딩
        url = f"{BASE_URL}?serviceKey={key}"
        return session.get(url, params=params, timeout=15)
    # 디코딩 키 → params 로 넘겨 requests 가 인코딩
    return session.get(BASE_URL, params={**params, "serviceKey": key}, timeout=15)


def parse_items(resp: requests.Response) -> list:
    """응답 JSON 에서 item 리스트 추출. 오류면 본문 출력 후 예외."""
    try:
        data = resp.json()
    except ValueError:
        # data.go.kr 는 인증 오류 시 XML 을 돌려준다 → 본문 그대로 출력
        sys.exit(f"JSON 파싱 실패 (인증/인코딩 의심). HTTP {resp.status_code}\n  본문: {resp.text[:600]}")

    # 오류 응답은 평면(flat) 형식: {"resultCode":"10","resultMsg":"..."} 일 수 있음
    if "response" not in data:
        code = data.get("resultCode")
        if code not in ("0000", "00"):
            sys.exit(f"TourAPI 오류: resultCode={code} msg={data.get('resultMsg')}\n  본문: {resp.text[:600]}")
        return []  # 평면 성공(이론상 드묾)

    header = data["response"].get("header", {})
    code = header.get("resultCode")
    if code not in ("0000", "00"):
        sys.exit(f"TourAPI 오류: resultCode={code} msg={header.get('resultMsg')}\n  본문: {resp.text[:600]}")

    body = data["response"]["body"]
    items = body.get("items")
    if not items or items in ("", None):
        return []
    item = items["item"]
    return item if isinstance(item, list) else [item]


def collect_tour(key: str) -> pd.DataFrame:
    """대상 구 × contentType 전부 페이지네이션 수집."""
    session = requests.Session()
    rows = []
    for gu, sigungu in SIGUNGU_CODES.items():
        for ctid, label in CONTENT_TYPES.items():
            page = 1
            while True:
                params = {
                    "numOfRows": NUM_OF_ROWS, "pageNo": page,
                    "MobileOS": "ETC", "MobileApp": "jongno-walkcourse",
                    "_type": "json", "arrange": "A",
                    "areaCode": AREA_CODE_SEOUL, "sigunguCode": sigungu,
                    "contentTypeId": ctid,
                }
                resp = tour_get(session, params, key)
                items = parse_items(resp)
                time.sleep(REQUEST_DELAY)
                if not items:
                    break
                for it in items:
                    mapx, mapy = it.get("mapx"), it.get("mapy")
                    if not mapx or not mapy:
                        continue
                    rows.append({
                        "place_id": f"tour_{it.get('contentid')}",
                        "name": (it.get("title") or "").strip(),
                        "gu": gu,
                        "category_main": label,
                        "category_sub": label,
                        "category_group_code": f"TOUR{ctid}",
                        "category_name": label,
                        "phone": it.get("tel", "") or "",
                        "address_name": it.get("addr1", "") or "",
                        "road_address_name": it.get("addr1", "") or "",
                        "lon": float(mapx),
                        "lat": float(mapy),
                        "place_url": "",
                    })
                if len(items) < NUM_OF_ROWS:
                    break
                page += 1
            print(f"  · {gu} / {label}: 누적 {len(rows)}건")
    return pd.DataFrame(rows).drop_duplicates(subset="place_id")


# ──────────────────────────────────────────────────────────────────────────
# 중복 제거 (기존 노드 대비)
# ──────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return "".join(str(s).split())


def dedup_against(existing: pd.DataFrame, tour: pd.DataFrame) -> pd.DataFrame:
    """기존 노드와 이름/근접 기준으로 중복인 tour 행 제거."""
    tr = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    ex_x, ex_y = tr.transform(existing["lon"].to_numpy(), existing["lat"].to_numpy())
    ex_x, ex_y = np.asarray(ex_x), np.asarray(ex_y)
    ex_names = [_norm(n) for n in existing["name"]]
    ex_nameset = set(ex_names)

    keep_mask = []
    for _, row in tour.iterrows():
        nm = _norm(row["name"])
        # (a) 이름 완전 일치 → 중복
        if nm in ex_nameset:
            keep_mask.append(False)
            continue
        # (b) 근접 + 이름 포함관계 → 중복
        tx, ty = tr.transform(row["lon"], row["lat"])
        d = np.hypot(ex_x - tx, ex_y - ty)
        near = np.where(d <= DEDUP_METERS)[0]
        is_dup = any(
            (nm and (nm in ex_names[i] or ex_names[i] in nm)) for i in near
        )
        keep_mask.append(not is_dup)

    return tour[pd.Series(keep_mask, index=tour.index)]


# ──────────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    key = os.getenv("TOURAPI_SERVICE_KEY", "").strip()
    if not key:
        sys.exit(".env 에 TOURAPI_SERVICE_KEY 가 비어 있습니다.")
    if not INPUT_PATH.exists():
        sys.exit(f"입력 파일이 없습니다: {INPUT_PATH}\n  먼저 cap_nodes.py 를 실행하세요.")

    print("=" * 60)
    print("TourAPI 관광지 보강")
    print(f"  대상 구: {list(SIGUNGU_CODES)}")
    print(f"  contentType: {CONTENT_TYPES}")
    print("=" * 60)

    tour = collect_tour(key)
    print(f"\nTourAPI 수집(중복 제거 전): {len(tour):,}건")

    existing = pd.read_parquet(INPUT_PATH)
    existing = existing.copy()
    existing["source"] = "kakao"

    new_tour = dedup_against(existing, tour)
    print(f"기존 노드와 중복 제거 후 신규: {len(new_tour):,}건")

    # 판단3: 신규 노드가 200 초과면 알림 (OD 행렬 크기 영향)
    if len(new_tour) > 200:
        print(f"  ⚠️ 신규 노드 {len(new_tour)}건 > 200 — 노드 증가폭이 큽니다. "
              f"필요하면 캡/필터를 다시 검토하세요.")

    # 스키마 정렬 (기존 컬럼 + source). 피처 컬럼은 NaN.
    new_tour = new_tour.copy()
    new_tour["source"] = "tourapi"
    for col in existing.columns:
        if col not in new_tour.columns:
            new_tour[col] = np.nan
    new_tour = new_tour[existing.columns]

    final = pd.concat([existing, new_tour], ignore_index=True)

    # 판단1: 신규 관광지는 hotspot_score 가 NaN → 중앙값으로 대체.
    # 도달성·추천에서 앵커가 빠지지 않도록(NaN 이면 정렬/필터에서 누락될 수 있음).
    if "hotspot_score" in final.columns:
        med = float(final["hotspot_score"].median())
        n_na = int(final["hotspot_score"].isna().sum())
        final["hotspot_score"] = final["hotspot_score"].fillna(med)
        print(f"\nhotspot_score NaN {n_na}건 → 중앙값({med:.3f})으로 대체")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(OUTPUT_PATH, index=False)
    print(f"저장 완료 → {OUTPUT_PATH.relative_to(REPO_ROOT)}  ({len(final):,} nodes)")

    # 핵심 앵커 확인
    print("\n핵심 앵커 포함 여부 (최종):")
    for kw in ANCHOR_KEYWORDS:
        hit = final[final["name"].str.contains(kw, na=False)]
        if len(hit):
            srcs = hit["source"].value_counts().to_dict()
            print(f"  [O] {kw}: {len(hit)}건  {srcs}")
        else:
            print(f"  [ ] {kw}: 없음")

    # 새로 추가된 관광지 목록(상위 일부)
    print(f"\n추가된 관광지 {len(new_tour)}건 중 일부:")
    for _, r in new_tour.head(20).iterrows():
        print(f"  + {r['name']} ({r['gu']}, {r['category_main']})")


if __name__ == "__main__":
    main()
