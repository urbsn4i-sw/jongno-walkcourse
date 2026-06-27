# scripts/ — 수집·전처리·OD행렬 생성 파이프라인

데이터 레이어(A)를 만드는 오프라인 파이프라인. **이 파이프라인 자체가 핵심 GitHub 산출물.**
> ⚠️ 아직 코드 미작성 — v1.0에서 구현 예정. 여기서는 의도된 단계만 기록.

## 파이프라인 단계 (예정)

```
1. bbox / 구경계 설정        종로 + 2~4km 버퍼 (중·서대문·성북·은평 포함)
2. POI 수집 (중복제거)       OSM 기본 + (선택) 카카오/네이버/TourAPI
3. 피처 보강                 언급량(네이버) · 생활인구(열린데이터광장) · 핫스팟 점수
4. POI 테이블 저장           data/processed/pois.parquet
5. 보행망 다운로드           OSMnx → data/processed/walk_graph.graphml
6. OD행렬 사전계산           노드 간 도보 travel_time → data/processed/od_matrix.parquet
```

## 핫스팟 점수 (전처리, NN 아님)

```
hotspot_score = z(블로그/검색 언급량) + DBSCAN 군집 밀집도
              → 0~1 정규화 후 노드 피처로 추가
```

## 예정 파일 (제안)

| 파일 | 역할 |
|---|---|
| `01_collect_pois.py` | POI 수집·중복제거 → raw |
| `02_enrich_features.py` | 언급량·생활인구·핫스팟 점수 보강 → pois.parquet |
| `03_build_walk_graph.py` | OSMnx 보행망 다운로드 → graphml |
| `04_build_od_matrix.py` | 노드 간 OD행렬 사전계산 → parquet |
| `config.py` | bbox·버퍼·노드 캡·카테고리 등 파라미터 |
