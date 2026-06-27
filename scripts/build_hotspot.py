"""
build_hotspot.py — 핫스팟 점수 피처 생성 (언급량 z-score + DBSCAN 군집 밀집도)

핸드오프 D9 / 6번 섹션의 정의:
    hotspot_score = z(블로그/검색 언급량) + DBSCAN 군집 밀집도  → 0~1 정규화 → 노드 피처

입력 : data/processed/pois_clean.parquet     (전처리 결과)
       data/processed/pois_mentions.parquet  (언급량 수집 결과)
출력 : data/processed/pois_features.parquet  (기존 컬럼 + 아래 피처)

추가 피처
    mention_count   : 네이버 블로그 검색 total (언급량 원값)
    mention_capped  : mention_count 를 상위 분위수(WINSOR_PCT)로 윈저라이즈한 값
    mention_z       : log1p(mention_capped) 의 z-score (극단값 캡 + 롱테일 완화)
    mention_norm    : mention_z 를 0~1 로 정규화 (점수 합산용)
    cluster_id      : DBSCAN 군집 id (-1 = noise) — 핫스팟 권역 표시용
    neighbor_count  : eps 반경 내 이웃 POI 수 (자기 제외) = 국소 밀도
    density_norm    : 국소 밀도를 0~1 로 정규화
    hotspot_score   : W_MENTION*mention_norm + W_DENSITY*density_norm  (0~1)

⚠️ 노드 캡(500~800)은 여기서 하지 않는다 — 점수 분포를 먼저 보고 다음 단계에서 결정.

사용:
    python scripts/build_hotspot.py
필요:
    pip install geopandas shapely scikit-learn pandas pyarrow numpy
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_gdal_data() -> None:
    """GDAL_DATA/PROJ 데이터 경로를 conda 환경에서 자동 탐지 (geopandas 임포트 전)."""
    prefix = Path(sys.prefix)
    for env_var, sub in (("GDAL_DATA", "gdal"), ("PROJ_DATA", "proj")):
        if os.environ.get(env_var):
            continue
        for cand in (prefix / "Library" / "share" / sub, prefix / "share" / sub):
            if cand.is_dir():
                os.environ[env_var] = str(cand)
                break


_ensure_gdal_data()

try:
    import numpy as np
    import pandas as pd
except ImportError:
    sys.exit("numpy/pandas 가 필요합니다:  pip install numpy pandas pyarrow")

try:
    import geopandas as gpd
except ImportError:
    sys.exit("geopandas 가 필요합니다:  pip install geopandas shapely")

try:
    from sklearn.cluster import DBSCAN
    from sklearn.neighbors import NearestNeighbors
except ImportError:
    sys.exit("scikit-learn 이 필요합니다:  pip install scikit-learn")


# ──────────────────────────────────────────────────────────────────────────
# 설정 (조정 포인트)
# ──────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
CLEAN_PATH = REPO_ROOT / "data" / "processed" / "pois_clean.parquet"
MENTIONS_PATH = REPO_ROOT / "data" / "processed" / "pois_mentions.parquet"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "pois_features.parquet"

# 좌표를 미터 단위로 다루기 위한 투영 CRS (한국 통합좌표계 EPSG:5179)
# → DBSCAN eps 를 '미터'로 직관적으로 지정할 수 있음.
CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:5179"

# 언급량 윈저라이즈: 이 분위수를 초과하는 mention_count 를 캡으로 누름.
# '집'·'안녕' 같은 1~2글자 일반어 상호가 ③ 검색으로도 남기는 극단값 방어.
WINSOR_PCT = 0.99

# 일반어 가드: 아래 이름인 POI 는 언급량 신호(mention_norm)를 중앙값으로 대체(페널티).
# 윈저라이즈로도 캡 상단에 몰리는 '일반명사 상호'를 직접 무력화.
# ※ 이름 '길이'로 자르지 않는다 — 정당한 짧은 상호가 억울하게 깎이지 않도록 명시 리스트만.
STOPWORD_NAMES = {
    "안녕", "집", "공간", "천국", "낙원", "가을", "여름", "나무", "하루", "오후",
    "식사", "바로", "조금", "섬", "한", "파크", "옥상", "식물", "포차",
}

# DBSCAN 파라미터 (미터 기준)
EPS_METERS = 100      # 이웃으로 볼 거리(m)
MIN_SAMPLES = 5       # 코어 포인트가 되기 위한 최소 이웃 수

# hotspot_score = 두 신호의 가중합 (가중치 합 = 1 → 결과가 자연히 0~1)
# 밀집을 좀 더 신뢰하도록 density 가중을 높임.
W_MENTION = 0.4
W_DENSITY = 0.6


# ──────────────────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────────────────

def minmax(s: pd.Series) -> pd.Series:
    """0~1 정규화. 분산이 0이면 전부 0."""
    lo, hi = s.min(), s.max()
    if hi - lo == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def zscore(s: pd.Series) -> pd.Series:
    """z-정규화. std=0이면 전부 0."""
    std = s.std(ddof=0)
    if std == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / std


# ──────────────────────────────────────────────────────────────────────────
# 단계
# ──────────────────────────────────────────────────────────────────────────

def load_and_merge() -> pd.DataFrame:
    """pois_clean + pois_mentions 를 place_id 로 머지."""
    clean = pd.read_parquet(CLEAN_PATH)
    mentions = pd.read_parquet(MENTIONS_PATH)[["place_id", "mention_count"]]

    df = clean.merge(mentions, on="place_id", how="left")

    missing = df["mention_count"].isna().sum()
    if missing:
        print(f"  ⚠️ 언급량 없는 POI {missing:,}건 → mention_count=0 으로 채움 "
              f"(수집이 아직 안 끝났을 수 있음)")
        df["mention_count"] = df["mention_count"].fillna(0)
    df["mention_count"] = df["mention_count"].astype(int)
    return df


def add_mention_signal(df: pd.DataFrame) -> pd.DataFrame:
    """언급량 → 윈저라이즈(상위 WINSOR_PCT 캡) → log1p → z-score → 0~1 정규화.
    그 뒤 일반어 가드: STOPWORD_NAMES 이름은 mention_norm 을 중앙값으로 대체.
    """
    df = df.copy()
    raw = df["mention_count"]

    cap = raw.quantile(WINSOR_PCT)
    # numpy.minimum 으로 캡 (pandas clip 의 downcasting FutureWarning 회피) + 명시 int 캐스팅
    capped = pd.Series(np.rint(np.minimum(raw.to_numpy(), cap)).astype(int), index=df.index)
    df["mention_capped"] = capped

    log_mention = np.log1p(capped)
    df["mention_z"] = zscore(log_mention)
    df["mention_norm"] = minmax(df["mention_z"])

    # 캡 적용 전/후 비교 로그
    n_capped = int((raw > cap).sum())
    print(f"  윈저라이즈: 상위 {(1 - WINSOR_PCT) * 100:.0f}% 캡 = {cap:,.0f}  "
          f"→ {n_capped:,}건({n_capped / len(raw) * 100:.1f}%) 눌림")
    print(f"    캡 전 : max={raw.max():,.0f}  mean={raw.mean():,.1f}  median={raw.median():,.0f}")
    print(f"    캡 후 : max={capped.max():,.0f}  mean={capped.mean():,.1f}  median={capped.median():,.0f}")

    # 일반어 가드: 불용어 이름 → mention_norm 을 중앙값으로 (페널티)
    med = float(df["mention_norm"].median())
    mask = df["name"].isin(STOPWORD_NAMES)
    df.loc[mask, "mention_norm"] = med
    print(f"  일반어 가드: STOPWORD {len(STOPWORD_NAMES)}개 매칭 {int(mask.sum()):,}건 "
          f"→ mention_norm=중앙값({med:.3f}) 대체")
    return df


def add_density_signal(df: pd.DataFrame) -> pd.DataFrame:
    """밀집도 = eps 반경 내 이웃 수(NearestNeighbors), DBSCAN cluster_id 는 유지.

    밀집도 환산 방식(설계 선택):
      각 POI 의 밀집도 = 반경 EPS_METERS 안에 있는 다른 POI 수 (자기 자신 제외).
      → '넓고 큰 군집'과 '좁고 빽빽한 군집'을 구분하는 진짜 국소 밀도.
      cluster_id 는 핫스팟 '권역' 표시용으로 DBSCAN 결과를 그대로 남겨 둠.
    """
    df = df.copy()

    # 위경도 → 미터 투영 후 (x, y) 좌표 배열
    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_WGS84
    ).to_crs(CRS_METRIC)
    coords = np.c_[gdf.geometry.x.values, gdf.geometry.y.values]

    # 핫스팟 권역 라벨 (표시용으로 유지)
    df["cluster_id"] = DBSCAN(eps=EPS_METERS, min_samples=MIN_SAMPLES).fit_predict(coords)

    # eps 반경 내 이웃 수 = 국소 밀도. radius_neighbors 는 자기 자신(거리 0)을 포함하므로 -1.
    nn = NearestNeighbors(radius=EPS_METERS).fit(coords)
    neigh_idx = nn.radius_neighbors(coords, return_distance=False)
    df["neighbor_count"] = np.array([len(ix) - 1 for ix in neigh_idx], dtype=int)

    # 롱테일 완화 위해 log1p 후 0~1
    df["density_norm"] = minmax(np.log1p(df["neighbor_count"]))
    return df


def add_hotspot_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hotspot_score"] = (
        W_MENTION * df["mention_norm"] + W_DENSITY * df["density_norm"]
    )
    return df


# ──────────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    for p in (CLEAN_PATH, MENTIONS_PATH):
        if not p.exists():
            sys.exit(f"입력 파일이 없습니다: {p}")

    print("=" * 60)
    print("핫스팟 점수 생성")
    print(f"  DBSCAN: eps={EPS_METERS}m, min_samples={MIN_SAMPLES}  (CRS {CRS_METRIC})")
    print(f"  가중치: mention={W_MENTION}, density={W_DENSITY}")
    print("=" * 60)

    df = load_and_merge()
    print(f"머지 결과: {len(df):,} POI")

    df = add_mention_signal(df)
    df = add_density_signal(df)
    df = add_hotspot_score(df)

    # 저장
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n저장 완료 → {OUTPUT_PATH.relative_to(REPO_ROOT)}  ({len(df):,} rows)")

    # 분포 리포트 (노드 캡 결정 전 참고용)
    n_clusters = df.loc[df["cluster_id"] != -1, "cluster_id"].nunique()
    n_noise = int((df["cluster_id"] == -1).sum())
    print(f"\nDBSCAN: 군집 {n_clusters}개, noise {n_noise:,}건")
    print("\nhotspot_score 분포:")
    print(df["hotspot_score"].describe().round(4).to_string())
    print("\n상위 10 (hotspot_score):")
    cols = ["name", "gu", "category_main", "mention_count", "neighbor_count", "hotspot_score"]
    top = df.sort_values("hotspot_score", ascending=False).head(10)
    print(top[cols].to_string(index=False))


if __name__ == "__main__":
    main()
