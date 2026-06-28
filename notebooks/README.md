# notebooks/ — 탐색·실험·벤치마크

재현 가능한 탐색과 ML 벤치마크용 주피터/Colab 노트북. 무거운 학습은 **Colab 무료 GPU**에서.

---

## NN 1차 벤치마크 결과 (L1·L2 랭커) — next-POI 추천

### 데이터
- **Foursquare NYC 체크인**: 227,428건, 사용자 1,083명
- 분할: **train 22.5만 / test = leave-one-out**(사용자별 마지막 방문 1건을 테스트로)
- 후보 POI는 **상위 5,000개**로 제한, **동일한 403개 test 집합**에서 모든 모델 공정 비교

### 결과표 (next-POI 랭킹)
| 모델 | Recall@1 | Recall@5 | Recall@10 | NDCG@1 | NDCG@5 | NDCG@10 |
|---|---|---|---|---|---|---|
| 인기순 (popularity) | 0.003 | — | 0.025 | — | — | 0.014 |
| 개인 이력 (personal history) | 0.273 | — | 0.635 | — | — | 0.464 |
| **NN L1 (MLP)** | 0.442 | — | 0.541 | — | — | 0.493 |
| **NN L2 (MLP + 이력)** | **0.524** | — | **0.648** | — | — | **0.590** |

> Recall@5/NDCG@1/NDCG@5 칸은 이번 기록에 수치 미포함(추후 노트북 산출 시 채움).

### 결론
- **L2 (MLP + 사용자 이력 임베딩 평균)** 가 **전 지표에서 베이스라인(인기순·개인 이력)을 초과**.
- L1(MLP)은 Recall@1에서 개인 이력을 크게 앞서나(0.442 vs 0.273), Recall@10에서는 개인 이력(0.635)에 약간 못 미침(0.541) → 이력 신호 결합(L2)이 두 약점을 모두 보완.
- "고전 대비 NN 우위"의 정량 물증 1차 확보 (핸드오프 D8/D18 서사).

### 다음
- **L3 (LSTM / 소형 Transformer)** 로 방문 **순서(sequence)** 를 모델링 → A→B→C 체이닝과 직접 대응.

---

## 예정 노트북 (제안)

| 노트북 | 내용 |
|---|---|
| `00_explore_pois.ipynb` | 수집된 POI·보행망 탐색, 분포·커버리지 확인 |
| `01_hotspot_score.ipynb` | 언급량 + DBSCAN 군집으로 핫스팟 점수 프로토타입 |
| `10_foursquare_benchmark.ipynb` | next-POI 랭커 학습·평가, Recall@k / NDCG 보고 (위 결과 산출) |
| `11_representation.ipynb` | PCA/UMAP POI 임베딩 시각화 |

## 규칙

- 출력 캐시(`outputs/`)는 git 추적 안 함(.gitignore).
- 노트북에서 확정된 로직은 `scripts/` 또는 `models/`로 옮겨 모듈화.
- API 키는 노트북에 적지 말고 `.env`/Colab secrets 사용.
