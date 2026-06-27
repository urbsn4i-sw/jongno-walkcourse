# notebooks/ — 탐색·실험·벤치마크

재현 가능한 탐색과 ML 벤치마크용 주피터/Colab 노트북.
> ⚠️ 아직 노트북 없음. 무거운 학습은 **Colab 무료 GPU**에서.

## 예정 노트북 (제안)

| 노트북 | 내용 |
|---|---|
| `00_explore_pois.ipynb` | 수집된 POI·보행망 탐색, 분포·커버리지 확인 |
| `01_hotspot_score.ipynb` | 언급량 + DBSCAN 군집으로 핫스팟 점수 프로토타입 |
| `10_foursquare_benchmark.ipynb` | next-POI 랭커 학습·평가, Recall@k / NDCG 보고 |
| `11_representation.ipynb` | PCA/UMAP POI 임베딩 시각화 |

## 규칙

- 출력 캐시(`outputs/`)는 git 추적 안 함(.gitignore).
- 노트북에서 확정된 로직은 `scripts/` 또는 `models/`로 옮겨 모듈화.
- API 키는 노트북에 적지 말고 `.env`/Colab secrets 사용.
