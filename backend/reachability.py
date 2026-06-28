"""
reachability.py — 도달성 엔진 (레이어 B, 결정론적 · NN 아님)

핵심 규칙:
    OD[현재][후보] + 체류시간[후보] ≤ 남은예산  인 후보만 통과.

시간/도달성은 여기서 '정확히' 거른다. 그 안에서의 순위는 지금은 hotspot_score 로
매기지만, 나중에 학습 랭커(NN)가 이 정렬을 대체한다.

입력 데이터:
    data/processed/pois_final.parquet  (피처: name, category_main, gu, lon, lat, hotspot_score ...)
    data/processed/od_matrix.parquet   (도보시간 분, 행/열 = place_id)

사용:
    from backend.reachability import reachable
    cands = reachable(current_place_id, remaining_budget_min=60)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
POIS_PATH = REPO_ROOT / "data" / "processed" / "pois_final.parquet"
OD_PATH = REPO_ROOT / "data" / "processed" / "od_matrix.parquet"

# 카테고리별 기본 체류시간(분) — 조정 가능
STAY_MINUTES = {
    "음식점": 40,
    "카페": 20,
    "관광명소": 30,
}
DEFAULT_STAY = 30  # 미정의 카테고리 fallback

# 사용자 필터 용어 → category_main 라벨
FILTER_MAP = {
    "식사": "음식점",
    "머물": "카페",
    "관광": "관광명소",
}


@lru_cache(maxsize=1)
def _load():
    """POI 피처 + OD 행렬 로드(1회 캐시)."""
    pois = pd.read_parquet(POIS_PATH).set_index("place_id")
    od = pd.read_parquet(OD_PATH).set_index("place_id")
    return pois, od


def reachable(current_place_id: str, remaining_budget_min: float,
              category_filter: str | None = None,
              visited: list | tuple | set | None = None) -> list[dict]:
    """남은예산 안에 도달 가능한 후보를 hotspot_score 내림차순으로 반환.

    Args:
        current_place_id : 현재 위치 place_id
        remaining_budget_min : 남은 도보 예산(분, 이동+체류 누적 기준)
        category_filter : '식사'/'관광'/'머물' 또는 category_main 라벨. None=전체
        visited : 제외할 place_id 목록(이미 방문)

    Returns:
        dict 리스트. 각 항목:
          place_id, name, category_main, gu, lon, lat,
          od_min(이동), stay_min(체류), remaining_min(방문 후 남는 예산), hotspot_score
    """
    pois, od = _load()

    if current_place_id not in od.index:
        raise KeyError(f"current_place_id 가 OD 행렬에 없습니다: {current_place_id}")

    # 현재 위치에서 각 후보까지 도보시간(분)
    row = od.loc[current_place_id]  # index = str(place_id)

    cand = pois.copy()
    cand["od_min"] = [row.get(str(pid), np.nan) for pid in cand.index]
    cand["stay_min"] = cand["category_main"].map(STAY_MINUTES).fillna(DEFAULT_STAY)
    cand["cost"] = cand["od_min"] + cand["stay_min"]

    # 필터: NaN 제외 + 예산 이내 + 자기 자신 제외
    mask = cand["od_min"].notna() & (cand["cost"] <= remaining_budget_min)
    mask &= cand.index != current_place_id

    # 방문 기록 제외
    if visited:
        mask &= ~cand.index.isin(set(visited))

    # 카테고리 필터
    if category_filter:
        label = FILTER_MAP.get(category_filter, category_filter)
        mask &= cand["category_main"] == label

    res = cand[mask].copy()
    res["remaining_min"] = remaining_budget_min - res["cost"]
    res = res.sort_values("hotspot_score", ascending=False)

    out = []
    for pid, r in res.iterrows():
        out.append({
            "place_id": pid,
            "name": r["name"],
            "category_main": r["category_main"],
            "gu": r.get("gu", ""),
            "lon": float(r["lon"]),
            "lat": float(r["lat"]),
            "od_min": round(float(r["od_min"]), 1),
            "stay_min": int(r["stay_min"]),
            "remaining_min": round(float(r["remaining_min"]), 1),
            "hotspot_score": round(float(r["hotspot_score"]), 4),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# 간단 테스트
# ──────────────────────────────────────────────────────────────────────────

def _demo() -> None:
    pois, _ = _load()
    # 출발점: 경복궁(관광명소)
    start = pois[(pois["name"].str.contains("경복궁", na=False)) &
                 (pois["category_main"] == "관광명소")]
    if start.empty:
        start = pois[pois["category_main"] == "관광명소"]
    sid = start.index[0]
    print(f"출발점: {start.loc[sid, 'name']} ({sid}) | 예산 60분\n")

    res = reachable(sid, remaining_budget_min=60)
    print(f"도달 가능 후보: {len(res)}곳, 상위 10:")
    print(f"{'이름':<22}{'카테고리':<8}{'이동':>6}{'체류':>6}{'잔여':>6}{'hotspot':>9}")
    for r in res[:10]:
        print(f"{r['name'][:20]:<22}{r['category_main']:<8}"
              f"{r['od_min']:>6.1f}{r['stay_min']:>6}{r['remaining_min']:>6.1f}"
              f"{r['hotspot_score']:>9.4f}")


if __name__ == "__main__":
    _demo()
