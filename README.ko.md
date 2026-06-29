# 종로 도보 동선 추천 (Jongno Walk-Course Recommender)

> 출발점과 도보 시간 예산을 고르면, 종로구 안에서 그 시간 안에 걸어서 닿는 스팟들 — 맛집·카페·관광지·서점·문화시설·쇼핑 — 을 우선순위로 추천하고, 하나를 고르면 다음 후보가 다시 떠서 A → B → C 동선이 완성되는 무료 웹앱.

**[🇬🇧 English README](./README.md)**

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://urbsn4i-sw.github.io/jongno-walkcourse/)
[![HF Space](https://img.shields.io/badge/🤗_HF_Space-NN_Demo-yellow)](https://huggingface.co/spaces/urban4isw/jongno-nn-ranker)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?logo=leaflet&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-NN-EE4C2C?logo=pytorch&logoColor=white)

**🔗 라이브 데모: https://urbsn4i-sw.github.io/jongno-walkcourse/**

<!-- 스크린샷: 라이브 데모에서 캡처해 docs/ 에 넣으면 여기 렌더링됩니다 -->
<!--
![동선이 그려진 지도](docs/demo-route.png)
![위성 보기](docs/demo-satellite.png)
![카테고리 필터](docs/demo-filters.png)
-->

---

## 무엇을 하는가

종로구 지도 위에서 출발점과 도보 시간 예산(30분 / 1시간 / 2시간 / 3시간)을 고릅니다. 그 예산 안에 걸어서 닿는 스팟을 전부 우선순위로 표시하고, 하나를 고르면 남은 예산이 차감되며 다음 후보가 다시 떠서 A → B → C 동선이 예산 소진까지 이어집니다(가변 깊이).

- **도달성은 결정론**: `이동시간 + 체류시간 ≤ 남은 예산` 인 후보만 통과.
- **랭킹이 ML이 사는 곳**: 예산을 통과한 후보를 학습된 랭커가 정렬 ([NN/ML](#nnml-실험) 참조).
- 이동시간은 실제 보행 네트워크 기반(거리 ÷ 4.5km/h).

## 주요 기능

- **순차 동선 구성** — A → B → C 가변 깊이 체이닝 + 뒤로가기(예산 복구).
- **유연한 출발점** — 지도 클릭 또는 GPS로 지정, 최근접 노드로 스냅.
- **10종 카테고리 필터** — 한식·술집·식당(기타)·카페·명소유적·거리/자연·기타관광·**서점·문화시설·쇼핑**.
- **마커 클러스터링**(spiderfy) — 한 건물에 여러 스팟이 몰려도 펼쳐서 개별 선택 가능.
- **일반 ↔ 위성** 지도 전환.
- **종로구 경계** 표시. 예산이 크면 인접 구로 동선이 넘어갈 수 있음.

## 아키텍처

```
(A) 데이터 레이어   종로 POI 테이블(피처) + 도보 OD행렬          [완성, 981 노드]
(B) 도달성 엔진     OD[현재][후보] + 체류[후보] ≤ 남은 예산        [완성, 결정론]
(C) 점수·추천       (B)를 통과한 후보를 정렬  ← NN/ML이 사는 곳
(D) 화면(웹)        지도 + 컨트롤 + 우선순위 마커 + 동선 + 클릭 루프  [완성]
```

하드 제약(시간 예산)은 (B)가 정확히 거르고, 그 안에서 (C)의 랭커가 순위만 매깁니다.

## 데이터 파이프라인

종로구 981 노드, 전 과정 스크립트화·재현 가능:

- **POI**: 카카오 로컬 API + TourAPI 관광 앵커(종묘·조계사 등).
- **인기도**: 네이버 블로그 언급량으로 근사(정확구 `"이름" 구` 검색으로 오매칭 방지).
- **핫스팟 점수**: 윈저라이즈된 언급량 + DBSCAN 밀집도, 카테고리별 쿼터 + 일반어 폭증 방지 가드.
- **도보 OD행렬**(981 × 981 분): 로컬 Geofabrik PBF에서 pyrosm + NetworkX 최단경로로 계산, 각 노드를 **최대 연결 컴포넌트**에 스냅(고립 섬 노드는 도달 불가가 되므로).
- 이후 서점·문화시설·쇼핑 랜드마크를 증분 방식으로 추가(교보문고·박물관·시장 등, 전체 재계산 없이).

## NN/ML 실험

**라이브 NN 데모:** [Hugging Face Spaces](https://huggingface.co/spaces/urban4isw/jongno-nn-ranker)에서 L2 랭커를 직접 써볼 수 있습니다.

추천 문제를 next-POI 랭킹으로 정의하고, 공개 Foursquare NYC 체크인 데이터(체크인 22.7만, 사용자 1,083명)로 검증했습니다. leave-one-out 방식, 동일 403개 test 집합에서 Recall@k·NDCG@k로 평가하고, 구조를 종로에 데모로 적용했습니다.

| 모델 | R@1 | R@10 | NDCG@10 |
|---|---|---|---|
| 인기순 | 0.003 | 0.025 | 0.014 |
| 개인 이력 | 0.273 | 0.635 | 0.464 |
| 랜덤포레스트 | 0.184 | **0.705** | 0.421 |
| 로지스틱 회귀 | 0.184 | 0.618 | 0.395 |
| KNN | 0.057 | 0.591 | 0.273 |
| NN L1 (MLP) | 0.442 | 0.529 | 0.489 |
| **NN L2 (MLP + 이력 임베딩)** | **0.529** | 0.650 | **0.593** |
| NN L3 (LSTM, 순서) | 0.169 | 0.360 | 0.266 |

**결론.** NN L2가 정밀 지표(Recall@1, NDCG)에서 1위 — 추천 품질에 가장 중요한 지표입니다. 랜덤포레스트는 Recall@10 커버리지가 가장 넓고요. 시퀀스 모델(L3, LSTM)은 크게 부진했는데, 방문 *순서*가 무익할 뿐 아니라 오히려 해로웠습니다 — 핵심 신호는 순서가 아니라 사용자가 자주 가는 *집합*이기 때문입니다. 챔피언은 **NN L2**이며, "더 복잡한 모델이 항상 낫지는 않다"를 보여줍니다. 상세는 [`notebooks/`](./notebooks).

## 기술 스택

- **프론트엔드**: React 19, Vite 8, react-leaflet 5, Leaflet 1.9, react-leaflet-cluster 4.1
- **지도 타일**: VWorld(한글 라벨) — 일반 + 위성
- **데이터·공간**: Python 3.12, pyrosm, NetworkX, pandas, GeoPandas
- **ML**: PyTorch, scikit-learn (Google Colab에서 학습)
- **배포**: GitHub Pages (정적, 사전계산 JSON)

## 로컬 실행

```bash
# 프론트엔드
cd frontend
npm install
npm run dev          # http://localhost:5173

# 빌드 & 배포 (GitHub Pages)
npm run deploy
```

데이터 파이프라인 스크립트는 [`scripts/`](./scripts)에 있고, 각 단계가 다음 단계의 입력을 만듭니다. 원본 데이터와 API 키는 git-ignore 처리됩니다.

## 데이터 출처 & 라이선스

POI는 카카오 로컬 API·TourAPI, 언급량은 네이버 블로그 검색 API, 지도 타일은 VWorld(공간정보 오픈플랫폼), 보행 네트워크는 OpenStreetMap(Geofabrik). NN 방법론은 Foursquare NYC 체크인 데이터(Yang et al., 2014)로 검증했습니다.

[MIT License](./LICENSE)로 배포됩니다.
