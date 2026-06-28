"""
add_kyobo.py — 교보문고 광화문점 1곳을 OD 행렬에 편입 (전체 재계산 없이 1행/열 추가)

안전: 원본은 미리 .bak 백업됨. 기본 실행은 '쓰기 없이' 좌표·스냅·Dijkstra까지만 하고
교보문고↔경복궁 도보분을 보고한다. 값이 상식적이면 `--write` 로 실제 반영(4·5·6).

  python scripts/add_kyobo.py            # 1·2·3 (드라이런: 검증 + 캐시 저장, 쓰기 없음)
  python scripts/add_kyobo.py --write    # 4·5·6 (od_matrix/pois_final 갱신 + JSON 재생성)

build_graph.py 와 동일: 보행속도 4.5km/h(=75 m/분), travel_time 은 그래프 엣지에 분 단위로
이미 들어있음. 보행망은 force_bidirectional=True 로 만들어져 OD 대칭 → 행=열 동일값.
"""

from __future__ import annotations

import os
import sys
import json
import pickle
import argparse
import subprocess
from pathlib import Path


def _ensure_geo_data() -> None:
    prefix = Path(sys.prefix)
    for env_var, sub in (("GDAL_DATA", "gdal"), ("PROJ_DATA", "proj")):
        if os.environ.get(env_var):
            continue
        for cand in (prefix / "Library" / "share" / sub, prefix / "share" / sub):
            if cand.is_dir():
                os.environ[env_var] = str(cand)
                break


_ensure_geo_data()

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
import networkx as nx
import osmnx as ox

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data" / "processed"
POIS_PATH = DATA / "pois_final.parquet"
OD_PATH = DATA / "od_matrix.parquet"
GRAPH_PATH = DATA / "walk_graph.gpickle"
SNAP_PATH = DATA / "node_snap.parquet"
BOUNDARY_PATH = REPO_ROOT / "frontend" / "public" / "data" / "jongno_boundary.geojson"
CACHE_PATH = DATA / "_kyobo_cache.json"

QUERY = "교보문고 광화문점"
WALK_SPEED_KMH = 4.5
METERS_PER_MIN = WALK_SPEED_KMH * 1000 / 60  # 75 (참고: 그래프 travel_time 은 이미 분)


# ──────────────────────────────────────────────────────────────────────────
# 1·2·3 (드라이런): 좌표 → 스냅 → Dijkstra → od_vec
# ──────────────────────────────────────────────────────────────────────────

def fetch_kyobo():
    load_dotenv(REPO_ROOT / ".env")
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        sys.exit(".env 에 KAKAO_REST_API_KEY 없음")
    r = requests.get(
        "https://dapi.kakao.com/v2/local/search/keyword.json",
        headers={"Authorization": f"KakaoAK {key}"},
        params={"query": QUERY, "size": 5}, timeout=10,
    )
    if r.status_code != 200:
        sys.exit(f"카카오 검색 실패 HTTP {r.status_code}: {r.text[:200]}")
    docs = r.json().get("documents", [])
    if not docs:
        sys.exit("검색 결과 없음")
    d = docs[0]
    return {
        "place_id": str(d["id"]),
        "name": d.get("place_name", QUERY),
        "lon": float(d["x"]),
        "lat": float(d["y"]),
        "category_name_kakao": d.get("category_name", ""),
        "address": d.get("road_address_name") or d.get("address_name", ""),
    }


def check_boundary(lon, lat) -> bool:
    try:
        from shapely.geometry import shape, Point
        gj = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))
        feats = gj.get("features", [])
        poly = shape(feats[0]["geometry"]) if feats else None
        return bool(poly and poly.contains(Point(lon, lat)))
    except Exception as e:
        print(f"  (경계 체크 건너뜀: {e})")
        return True


def compute_od_vector(kyobo):
    print("  보행 그래프 로드 중(140MB)...")
    with open(GRAPH_PATH, "rb") as f:
        G = pickle.load(f)
    if "crs" not in G.graph:
        G.graph["crs"] = "EPSG:4326"
    # ⚠️ retain_all=True 그래프엔 고립 섬(island)이 있어, 그냥 최근접 스냅하면
    #    끊긴 노드에 붙을 수 있음 → 최대 연결 컴포넌트(본 네트워크)로 제한해 스냅.
    comps = (nx.weakly_connected_components(G) if G.is_directed()
             else nx.connected_components(G))
    giant = max(comps, key=len)
    G = G.subgraph(giant).copy()
    print(f"  최대 연결 컴포넌트: 노드 {G.number_of_nodes():,} (전체 중)")
    node = ox.distance.nearest_nodes(G, X=kyobo["lon"], Y=kyobo["lat"])
    # 스냅 거리(m) 참고
    nx_, ny_ = G.nodes[node]["x"], G.nodes[node]["y"]
    snap_m = float(np.hypot(
        (nx_ - kyobo["lon"]) * 111000 * np.cos(np.radians(kyobo["lat"])),
        (ny_ - kyobo["lat"]) * 111000))
    print(f"  스냅 노드 osmid={node}, 스냅거리≈{snap_m:.1f}m")

    lengths = nx.single_source_dijkstra_path_length(G, node, weight="travel_time")  # 분

    snap = pd.read_parquet(SNAP_PATH)  # place_id, osmid, snap_dist_m
    od_vec = {}
    for r in snap.itertuples(index=False):
        v = lengths.get(r.osmid, None)
        od_vec[str(r.place_id)] = (None if v is None else round(float(v), 1))
    n_reach = sum(1 for v in od_vec.values() if v is not None)
    print(f"  도달 가능 {n_reach}/{len(od_vec)} (NaN {len(od_vec) - n_reach})")
    return od_vec, node, snap_m


def gyeongbok_place_id(pois):
    m = pois[(pois["name"].str.contains("경복궁", na=False)) & (pois["category_main"] == "관광명소")]
    return str(m.iloc[0]["place_id"]) if len(m) else None


def dry_run():
    kyobo = fetch_kyobo()
    print("=" * 56)
    print(f"교보문고: {kyobo['name']} | ({kyobo['lon']}, {kyobo['lat']})")
    print(f"  place_id={kyobo['place_id']} | 카카오분류={kyobo['category_name_kakao']}")
    print(f"  주소={kyobo['address']}")
    inside = check_boundary(kyobo["lon"], kyobo["lat"])
    print(f"  종로구 경계 안? {inside}" + ("" if inside else "  ⚠️ 경계 밖!"))

    od_vec, node, snap_m = compute_od_vector(kyobo)

    pois = pd.read_parquet(POIS_PATH)
    gid = gyeongbok_place_id(pois)
    gb_min = od_vec.get(gid)
    print("\n--- 중간 검증 ---")
    print(f"교보문고 → 경복궁({gid}) 도보: {gb_min} 분  (광화문 교보↔경복궁 ~10분 안팎 기대)")

    # 캐시 저장(쓰기 단계에서 그래프 재로드 없이 재사용)
    CACHE_PATH.write_text(json.dumps(
        {"kyobo": kyobo, "od_vec": od_vec, "snap_node": int(node), "snap_m": snap_m},
        ensure_ascii=False), encoding="utf-8")
    print(f"\n캐시 저장 → {CACHE_PATH.relative_to(REPO_ROOT)}")
    print("값이 상식적이면:  python scripts/add_kyobo.py --write")


# ──────────────────────────────────────────────────────────────────────────
# 4·5·6 (--write): od_matrix / pois_final 갱신 + JSON 재생성
# ──────────────────────────────────────────────────────────────────────────

def write_run():
    if not CACHE_PATH.exists():
        sys.exit("캐시 없음 — 먼저 드라이런(python scripts/add_kyobo.py) 실행")
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    kyobo, od_vec = cache["kyobo"], cache["od_vec"]
    kid = kyobo["place_id"]

    # 4) OD 행렬: 947번째 행/열 추가 (대칭)
    od = pd.read_parquet(OD_PATH).set_index("place_id")
    od.index = od.index.astype(str)
    od.columns = od.columns.astype(str)
    if kid in od.index:
        sys.exit(f"이미 존재하는 place_id={kid} — 중단")
    od[kid] = [od_vec.get(idx) for idx in od.index]          # 기존행 → 교보 (열)
    new_row = {col: od_vec.get(col) for col in od.columns}   # 교보 → 기존열 (행)
    new_row[kid] = 0.0                                        # 자기자신
    od.loc[kid] = pd.Series(new_row)
    od.index.name = "place_id"
    od.reset_index().to_parquet(OD_PATH, index=False)
    print(f"OD 갱신 → {od.shape[0]}×{od.shape[1] - 0}  (행/열에 교보 추가)")

    # 5) pois_final: 1행 추가 (cat2='기타관광' 되도록 category_name 평면 '관광명소')
    pois = pd.read_parquet(POIS_PATH)
    med = float(pois["hotspot_score"].median())
    row = {c: np.nan for c in pois.columns}
    row.update({
        "place_id": kid, "name": kyobo["name"], "gu": "종로구",
        "category_main": "관광명소", "category_sub": "관광명소",
        "category_group_code": "KYOBO", "category_name": "관광명소",
        "phone": "", "address_name": kyobo["address"], "road_address_name": kyobo["address"],
        "lon": kyobo["lon"], "lat": kyobo["lat"], "place_url": "",
        "mention_count": 0, "hotspot_score": round(med, 4), "source": "manual",
    })
    pois = pd.concat([pois, pd.DataFrame([row])[pois.columns]], ignore_index=True)
    pois.to_parquet(POIS_PATH, index=False)
    print(f"pois_final 갱신 → {len(pois)} 행 (hotspot_score={round(med, 4)} 중앙값 부여)")

    # 6) JSON 재생성
    print("export_frontend_data.py 재실행...")
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "export_frontend_data.py")],
                   check=True, cwd=str(REPO_ROOT))
    print("완료. (검증은 별도 단계)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="실제 데이터 반영(4·5·6)")
    args = ap.parse_args()
    write_run() if args.write else dry_run()
