# data/ — 데이터 레이어 (A)

종로구 + 인접 버퍼(중·서대문·성북·은평)의 POI 테이블과 도보 OD행렬이 들어가는 곳.
**대용량 파일은 커밋하지 않는다** (`.gitignore`). `scripts/`의 수집 코드로 재생성한다.

## 폴더

- `raw/` — 수집 원본 (OSM 덤프, API 응답 캐시 등). git 추적 안 함.
- `processed/` — 가공 산출물. git 추적 안 함.

## v1.0 예정 산출물 (processed/)

| 파일 | 내용 | 생성 스크립트 |
|---|---|---|
| `pois.parquet` | POI 노드 테이블 (id, name, lat, lon, category, 구, 언급량, 핫스팟점수, 체류시간 등) | `scripts/` 수집·전처리 |
| `walk_graph.graphml` | OSMnx 보행망 그래프 | `scripts/` 보행망 다운로드 |
| `od_matrix.parquet` | 노드 간 도보 travel_time OD행렬 | `scripts/` OD행렬 생성 |

## 메모

- 공간 범위: 종로구 경계 + 약 2~4km 버퍼 (3시간 도보 ≈ 13km 대비).
- 노드 캡: v1은 ~500~800개 (카테고리별 기초 relevance 상위).
- API 키는 `.env`로 관리, 절대 데이터/코드에 하드코딩 금지.
