"""
test_reachability.py — 도달성 엔진 견고성 점검 (수동 실행 데모)

확인 항목:
  1) 카테고리 필터(식사/관광/머물)가 해당 카테고리만 반환하는지
  2) A→B→C… 체이닝: 누적예산 차감 + 방문기록(visited) 제외가 맞는지
  3) 엣지 케이스: 아주 작은 예산이면 빈 결과가 깔끔히 나오는지

사용:
    python backend/test_reachability.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.reachability import _load, reachable  # noqa: E402


def _start_id():
    pois, _ = _load()
    start = pois[(pois["name"].str.contains("경복궁", na=False)) &
                 (pois["category_main"] == "관광명소")]
    if start.empty:
        start = pois[pois["category_main"] == "관광명소"]
    sid = start.index[0]
    return sid, start.loc[sid, "name"]


def test_category_filter():
    sid, sname = _start_id()
    print(f"\n[1] 카테고리 필터 ({sname} 60분, 각 상위 5)")
    for f in ["식사", "관광", "머물"]:
        res = reachable(sid, 60, category_filter=f)
        cats = {r["category_main"] for r in res}
        print(f"\n  · '{f}' → {len(res)}곳 (카테고리 집합={cats}), 상위 5:")
        for r in res[:5]:
            print(f"      {r['name'][:18]:<20}{r['category_main']:<8}"
                  f"이동{r['od_min']:>5.1f} 체류{r['stay_min']:>3} 잔여{r['remaining_min']:>5.1f}")


def test_chaining(budget: float = 120.0):
    sid, sname = _start_id()
    print("\n[2] 체이닝 (경복궁 {:.0f}분, 매 단계 상위 1곳)".format(budget))
    current, visited, path = sid, [sid], [sname]
    print(f"  [A] {sname} | 시작 예산 {budget:.1f}분 | visited={len(visited)}곳")
    for nxt in "BCDEFGHIJ":
        res = reachable(current, budget, visited=visited)
        if not res:
            print(f"  [{nxt}] 후보 없음 → 예산 소진(잔여 {budget:.1f}분). 종료.")
            break
        pick = res[0]
        print(f"  [{nxt}] {pick['name'][:18]} ({pick['category_main']}) "
              f"| 이동 {pick['od_min']:.1f} + 체류 {pick['stay_min']} "
              f"| 남은예산 {pick['remaining_min']:.1f}분 | visited={len(visited)}곳")
        current, budget = pick["place_id"], pick["remaining_min"]
        visited.append(pick["place_id"])
        path.append(pick["name"])
    print(f"\n  최종 동선: {' → '.join(p[:12] for p in path)}")
    print(f"  visited 중복 없음? {len(visited) == len(set(visited))}")


def test_edge_small_budget():
    sid, _ = _start_id()
    print("\n[3] 엣지 케이스: 작은 예산")
    for b in [10, 5, 0]:
        res = reachable(sid, b)
        print(f"  예산 {b}분 → 후보 {len(res)}곳" +
              (f" (예: {res[0]['name']})" if res else " (빈 결과)"))


if __name__ == "__main__":
    test_category_filter()
    test_chaining()
    test_edge_small_budget()
