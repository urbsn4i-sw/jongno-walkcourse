# 종로 도보 동선 추천 (가칭: Jongno Walk-Course Recommender) — 프로젝트 핸드오프 문서 **v8**

> **이 문서의 목적**
> 채팅(claude.ai 상담 대화)이 길어져 새 창에서 다시 시작할 때, **이 문서 전체를 새 채팅에 붙여넣으면 맥락이 그대로 복원**되도록 만든 단일 진실 소스(single source of truth).
> 새 채팅 첫 메시지 예시: *"아래는 진행 중인 실습 과제의 핸드오프 문서야. 이걸 기준으로 이어가자. 현재 상태는 13번 섹션을 봐줘."* + (이 문서 붙여넣기)
>
> **참고:** Claude Code(데스크톱 Code 탭)는 새 채팅이 불필요 — 기존 `jongno-walkcourse` 세션 그대로. Colab(NN 트랙)도 노트북 다시 열어 "모두 실행"하면 복원(데이터 CSV 재업로드 필요). "새 세션"은 이 claude.ai 상담 대화에만 해당.
>
> **v6 변경 요지:** (1) **출발점 선택(D21) 완료** — 지도클릭 스냅 + GPS "내 위치에서 시작"(경복궁 고정 해제). (2) **표시 정책 확정** — 카운트 컷·거리창 폐기 → "남은 예산 내 도달 후보 전부 + 마커 클러스터링(spiderfy)". 시간예산 단조성 버그 해결. (3) **교보문고 광화문점 OD 편입**(946→**947 노드**, `add_kyobo.py`). (4) **고전 ML(RF·로지스틱·KNN) vs NN 비교 완료** — NN L2가 R@1·NDCG 1위, RF가 R@10 1위, 종합(NDCG) NN 우위. (5) attribution = 🇰🇷 urbsn4i-sw. 다음: L3(선택) · 데이터 확장(B) · 백엔드(D22).
>
> **v7 변경 요지:** NN L3(LSTM 순서 모델) ablation 완료 — L3·L3b 모두 L2에 크게 못 미침 (순서는 무익·유해, 단골 집합이 핵심). 최종 챔피언=L2 확정. GitHub Pages 배포 완료 (urbsn4i-sw.github.io/jongno-walkcourse/). 다음: 데이터 확장(B).
>
> **v8 변경 요지:** 데이터 확장(B) 완료 — 서점·문화시설·쇼핑 34개를 (b)증분 방식으로 OD 편입 (947→981 노드, cat2 7종→10종). add_expansion.py(add_kyobo 일반화, giant component 스냅). 네이버 지역 API 검토: 쿼리당 5건 캡으로 수집 부적합, 카카오 전수가 우수 → 카카오 유지 (네이버는 인기신호 보조만 가능, future work). 영업상태 검증은 범위 밖(카카오·네이버 모두 부정확, 교차검증 신뢰도 표시는 future work). 배포 갱신 완료. 다음: (다) 마무리 / Hugging Face.

---

## 1. 프로젝트 한 줄 정의
**종로구 지도 위에서, 내 출발점으로부터 도보 예산(30분/1h/2h/3h) 안에 닿는 스팟(맛집·관광지·핫스팟)을 우선순위로 추천하고, 하나를 고르면 다음 후보가 다시 떠서 A→B→C 동선이 완성되는 무료 웹앱.**

- 핵심 상호작용: `A 선택 → B-1…B-n 표시 → B 선택 → C-1…C-n …` (예산 소진까지, 가변 깊이) — **React 앱에서 작동 확인됨**
- **학습 목표(중요):** NN을 *직접 짜고 학습시키는* 경험이 이 과제의 중심. 추천·랭킹 = NN/ML, 시간/도달성 = 결정론. → **L1·L2 + 고전 ML 비교 완료(아래 6번).**
- 학술 프레이밍(선택): 보행 접근성(walkability) · 시간지리학의 time-space prism

---

## 2. 절대 제약 (Hard Constraints)
1. **전부 무료.** 유료 API·유료 빌링 금지. 무료 등록(키 발급)은 허용. (Claude Code는 **Claude Max 플랜 포함** → 제약 위반 아님.) ⚠️ "무료 제약"의 실제 대상은 **앱이 의존하는 외부 서비스/호스팅**이지 개발 도구(Claude Max)가 아님.
2. **배움 중심.** 결과물보다 학습 경험·재현 가능성 우선. 특히 **NN을 적극적으로 구축·학습** — L1·L2 + 고전 ML 비교 완료.
3. **지도에 경로와 추천이 반드시 보여야 함.** — ✅ React 앱에서 충족.
4. **경계 침범 허용·안내.** 도보 예산이 크면 종로구를 벗어나 **중구·서대문·성북·은평**으로 넘어갈 수 있음 → 데이터·네트워크가 버퍼 포함, UI는 종로 경계 표시(D20). ※ **공간 범위는 종로구로 확정**(중구 등 주대상 확장은 안 함 — 컨셉·데이터 일치).
5. 식당 폐점 여부 검증은 **사용자가 직접 처리**(앱 범위 밖).

---

## 3. 확정된 설계 결정 (Decision Log)
| # | 결정 | 값 |
|---|---|---|
| D1 | 형태 | 웹앱(앱 아님) |
| D2 | 대상 지역 | **종로구 확정** + 인접 버퍼(중·서대문·성북·은평) |
| D3 | 이동 수단 | 도보 |
| D4 | 시간 예산 | 30분 / 1시간 / 2시간 / 3시간 (사용자 선택) |
| D5 | "1시간"의 정의 | 이동시간 + 체류시간 누적 |
| D6 | 분기 | A→B→C… 예산 소진까지 반복(**가변 깊이**) |
| D7 | 경계 | 인접 구 침범 허용 + 표시 |
| D8 | NN/ML의 역할 | **후보 추천·랭킹(직접 구축·학습)**. 시간/도달성은 결정론. → L1·L2 + 고전 ML 비교 완료 |
| D9 | 핫스팟 정의 | 블로그 언급량 + 군집(밀집). 고평점은 무료 평점 소스 부재로 언급량 대체 |
| D10 | 성·연령 | **인기도 조건화(집계)**만. 학습된 개인화는 future work |
| D11 | 개발 도구 | Claude Code(레포·코드, Max 포함) + Colab(NN 학습) |
| D12 | 프론트엔드 | **React + Leaflet** (Streamlit 제외) — ✅ 구현 완료 |
| D13 | 배포 | **GitHub Pages**(정적) — 데이터 사전계산 → JSON. ⚠️ 백엔드 도입 시 재검토(D22) |
| D14 | 강화학습(RL) | **v2/advanced**로 연기 |
| D15 | 언어 | **v1은 한국어만.** 다국어 UI·README 영어화는 마무리 단계 |
| D16 | 지도 타일 | **VWorld `white` 한글 일반지도**(무료 키). ⚠️ 유효 레이어명 `Base`/`white`/`midnight`/`Hybrid`만(`gray` 무효). **attribution = `🇰🇷 urbsn4i-sw \| © 공간정보 오픈플랫폼(브이월드)`** (Leaflet prefix 제거; VWorld 출처는 약관상 필수 유지). 위성지도(`Satellite` 레이어) 전환은 future work(TileLayer URL 한 줄) |
| D17 | 보행 시간 모델 | travel_time = 거리 ÷ **4.5km/h**(검증 통과). 신호·계단 미반영(가정) |
| D18 | 랜덤포레스트 | 고전 ML 베이스라인(아래 6번에서 실제 비교). NN 트랙 베이스라인=인기순·개인이력 |
| D19 | 카테고리 세분(cat2) | **cat2 10종**: 한식·술집·식당(기타)·카페·명소·유적·거리·자연·기타관광 (+ **서점·문화시설·쇼핑** 데이터 확장 B). `category_name` 매핑(신규 3종은 category_main 자체가 cat2). TourAPI 159개는 평면→"기타관광" |
| D20 | 종로구 경계 표시 | VWorld 2D데이터 API → MultiPolygon `jongno_boundary.geojson` → `<GeoJSON>` 파란 점선 |
| **D21** | **출발점 선택 — ✅ 완료** | **지도클릭** + **GPS "내 위치에서 시작"** → `nearestNode`로 종로 최근접 POI 스냅(직선거리, **2km 초과=권역밖 폴백 alert**). 동선 진행 중(path 2+) 클릭 무시. GPS는 HTTPS/localhost서만 동작(GitHub Pages OK). ⚠️ 직선거리 스냅 — 도보거리 스냅은 백엔드(D22) future work |
| D22 | 백엔드(FastAPI) — 검토 중 | 도보거리 스냅·라우팅·NN 서버추론용. 로컬 우선 제작, 공개 배포는 마지막 결정 |
| D23 | NN 학습 데이터 | 종로엔 선택 로그 없음 → **Foursquare NYC 공개 체크인**(Dingqi Yang 2014)으로 방법 학습·검증, 구조를 종로에 적용 |
| **D24** | **후보 표시 정책 — ✅ 확정** | **"남은 예산 내 도달 후보 전부 + 마커 클러스터링"**. 예산↑ = 화면 후보 superset(단조성 자연 성립). 정렬 = 도보시간 오름차순 → hotspot tiebreak. 클러스터(`react-leaflet-cluster`)로 빽빽함 해소, 클릭 시 확대 없이 펼침(spiderfy). ⚠️ **폐기된 시도:** 카운트 컷(상위 N) → 예산↑ 시 가까운 후보 밀림(버그), 거리창(도보 N분 고정) → 예산 무시돼 1/2/3h 동일. 둘 다 폐기. ※ 현재 정렬은 임시 휴리스틱 — 최종은 C 레이어 NN 랭커 |
| **D25** | **교보문고 광화문점 수동 편입** | 대표 서점 랜드마크라 명시적 큐레이션. `add_kyobo.py`로 보행그래프 single-source Dijkstra 1회 → OD 947번째 행/열 추가(전체 재계산 X). cat2=기타관광(카카오 원분류는 서점 — 데이터 확장 B 때 재분류 검토) |
| **D26** | **데이터 확장 B — ✅ 완료** | 서점·문화시설·쇼핑 (b)증분 편입(947→981, `add_expansion.py`). 쇼핑 핵심상권(광장시장·인사동)은 기존 노드에 이미 포함돼 동대문·동묘 상권만 추가. 네이버 지역 API는 5건 캡으로 수집 부적합(카카오 유지). 정찰 점수(build_hotspot 윈저라이즈+STOPWORD) 후 엄선, giant component 스냅 |

---

## 4. 아키텍처 (4 레이어)
```
(A) 데이터 레이어   : 종로 POI 테이블 + 도보 OD행렬   [완성, 947 노드]
(B) 도달성 엔진     : OD[현재][후보]+체류[후보] ≤ 남은예산 인 후보만 통과  [완성, 결정론적]
(C) 점수·추천 레이어 : 통과 후보 정렬  ← ★ NN/ML이 사는 곳
                      (앱은 도보시간순 임시 / NN·고전ML 랭커는 Colab에서 비교 완료, 앱 연결은 future work)
(D) 화면(웹)        : 지도 + 컨트롤 + 클러스터 마커 + 동선 + 클릭 루프 + 출발점 선택  [완성]
```
**원칙:** 하드 제약(시간 예산)은 (B)가 정확히 거르고, 그 안에서 (C)의 NN/ML이 순위만 매긴다.
**현 상태:** A·B·D 완성. C는 앱에선 도보시간순 정렬(임시, D24), NN·고전ML 랭커는 Colab 트랙에서 비교 완료 — 앱 연결은 future work(모델 export 또는 백엔드 추론 D22).

---

## 5. ★ 앱 UX 요구사항 — ✅ 구현 완료
1. **지도:** VWorld `white` 한글 일반지도. ✅
2. **상단 컨트롤:** 시간 버튼(30분/1h/2h/3h) + 카테고리 필터(cat2 10종) + 뒤로가기. ✅
3. **시간 선택 시:** 출발점 기준 도달 후보 → 선택 → 다음 후보 → 예산 소진까지(가변 깊이). ✅
4. **뒤로 가기(undo):** 예산 복구 + 후보 재표시(스택 패턴). ✅
5. **카테고리 필터(cat2 10종):** 각 단계에서 필터 (서점=파랑/문화시설=분홍/쇼핑=갈색 추가). ✅
6. **마우스 호버 툴팁:** 이름·cat2·도보분. ✅
7. **종로구 경계 표시.** ✅
8. **출발점 선택 (D21):** 지도클릭 + GPS "내 위치에서 시작" → 최근접 POI 스냅. ✅ (경복궁 고정 해제)
9. **후보 표시 (D24):** 남은 예산 내 도달 후보 전부 + 마커 클러스터링(클릭 시 확대 없이 펼침). ✅

---

## 6. ★ NN/ML 사다리 — ✅ L1·L2 + 고전 ML 비교 완료
> **방침(D23):** Foursquare NYC 공개 체크인으로 next-POI 추천을 학습·검증(정량지표), 구조를 종로에 적용(데모). 모델 정의→학습 루프→loss 관찰→평가를 직접 손으로 — **완료.**

**데이터:** Foursquare NYC 체크인 227,428건 / 사용자 1,083명(방문 5회+) / venue ~38,000. userId별 시간순 시퀀스 → train 225,262 샘플, test = leave-one-out. 후보 POI 상위 5,000개 제한, **공정 비교는 동일 test 403개 집합**.

**최종 비교(동일 403 집합) — Recall@k / NDCG@k:**
| 모델 | R@1 | R@5 | R@10 | NDCG@10 |
|---|---|---|---|---|
| 인기순(most-popular) | 0.003 | 0.022 | 0.025 | 0.014 |
| 개인 이력(personal history) | 0.273 | 0.593 | 0.635 | 0.464 |
| RF (랜덤포레스트) | 0.184 | 0.536 | **0.705** | 0.421 |
| 로지스틱 회귀 | 0.184 | 0.543 | 0.618 | 0.395 |
| KNN | 0.057 | 0.325 | 0.591 | 0.273 |
| NN L1 (MLP) | 0.442 | 0.511 | 0.529 | 0.489 |
| **NN L2 (MLP + 사용자 이력 임베딩)** | **0.521** | **0.633** | 0.668 | **0.590** |

> ※ 수치는 **고전 ML과 동일 실행의 재현값** 기준으로 통일(학습 무작위성으로 v5의 L2 R@1 0.524와 소수 둘째자리 차이 — 결론 동일).

**핵심 결론 (입체적):**
- **NN L2가 R@1·NDCG에서 1위** — "정답을 1순위로 맞히고 상위에 올리는" 추천 품질이 최고.
- **RF가 R@10에서 1위(0.705)** — 넓은 커버리지는 RF지만, R@1이 0.184로 정밀도는 NN의 1/3.
- **종합 순위품질(NDCG)은 NN L2(0.590)가 RF(0.421)를 크게 앞섬** → **"학습된 표현(NN) > 수작업 피처(고전 ML)"** in 추천 품질.
- 서사: 인기순 → 개인이력 → 고전 ML 3종 → NN 2종으로 단계적 향상 + "기법마다 강점이 다르나 종합은 NN 우위".

**L3 결과:** L3(순수 LSTM) R@1 0.169 / L3b(LSTM+이력) R@1 0.137 — 둘 다 L2(0.529)에 크게 못 미침. 순서 모델링이 단골 신호를 교란·과적합. 챔피언=L2. 상세는 notebooks/README.

**고전 ML 방식:** (맥락,후보) 쌍을 **8개 수작업 피처**(전역인기도/사용자방문횟수/방문여부/후보카테고리/직전카테고리/카테고리일치/이력길이/시간대)로 만들고 negative sampling(1:4) 이진분류 학습 → 후보 5,000개에 정답확률 점수 → 랭킹. (= pointwise learning-to-rank)

| Level | 모델 | 상태 |
|---|---|---|
| 베이스라인 | 인기순·개인이력 | ✅ |
| 고전 ML | RF·로지스틱·KNN | ✅ (NN과 비교 완료) |
| L1 | MLP 랭커 | ✅ |
| L2 | MLP + 사용자 이력 임베딩 평균 | ✅ (R@1·NDCG 1위) |
| L3 | 시퀀스 모델 (LSTM / 소형 Transformer) | ✅ 완료(L2 못 넘음, 순서 무익) |
| L4 *(선택)* | GNN | future work |
| v2 *(연기)* | 강화학습 / 확산 | future work |

**환경:** Colab(CPU로 L1·L2 학습 가능, 15 epoch loss 7.62→1.80). 노트북 `notebooks/jongno_walkcourse.ipynb`(출력 비워 ~28KB 커밋), 결과 `notebooks/README.md`(L1·L2 + 고전ML 두 섹션). 모델 `.pt` 미저장(재학습 복원: 노트북 "모두 실행" + CSV 재업로드).

---

## 7. 무료 기술 스택 (FREE)
| 용도 | 도구 | 비고 |
|---|---|---|
| 지도 표시 | Leaflet + VWorld `white` 타일 + **react-leaflet-cluster** | 무료 키. 한글 라벨. 마커 클러스터(D24) |
| 행정경계 | VWorld 2D데이터 API | 종로구 폴리곤 GeoJSON (D20) |
| 보행망·OD행렬 | pyrosm + 로컬 PBF + NetworkX | |
| POI(노드) | 카카오 로컬 + TourAPI | 무료 키 |
| 언급량 | 네이버 블로그 검색 API | 검색어 `"이름" 구` |
| NN 학습 데이터 | **Foursquare NYC 공개 체크인** | next-POI 벤치마크 (D23) |
| NN·ML | **PyTorch / scikit-learn** + Colab | L1·L2 + RF·로지스틱·KNN |
| 프론트엔드 | Vite 8 + React 19 + react-leaflet 5 + leaflet 1.9 + react-leaflet-cluster 4.1.3 | Node v24 |
| 배포 | GitHub Pages / HF Spaces | (백엔드 시 재검토 D22) |
| 백엔드(검토 중) | FastAPI | 도보거리 스냅·라우팅 (D22) |
| 개발 | Claude Code(Max) + Colab | |

---

## 8. 데이터 파이프라인 — ✅ 완성 (981 노드)
**스크립트(13), 커밋·푸시 완료. 원본 데이터는 `.gitignore`.**
```
collect_pois.py / preprocess_pois.py / collect_mentions.py / build_hotspot.py /
cap_nodes.py / collect_tourapi.py / build_graph.py /
export_frontend_data.py → pois.json + od.json (cat2 10종) /
fetch_boundary.py → 종로 경계 GeoJSON / make_map.py → folium 검증 /
add_kyobo.py → 교보문고 1곳 OD 편입(947 노드, --write 안전장치) /
add_expansion.py → 데이터 확장 B: 서점·문화시설·쇼핑 34개 일괄 OD 편입(981 노드, --write 안전장치)
```
**원본 산출물 (data/processed/, gitignore):** `pois_final.parquet`(**981 POI**), `od_matrix.parquet`(**981×981** 도보분 — ⚠️ place_id를 컬럼 저장 → 읽을 때 `set_index("place_id")` 필요), `walk_graph.gpickle`(~140MB, pyrosm 보행그래프 16.5만 노드), `node_snap.parquet`. **백업:** `*.parquet.bak`(교보문고 편입 전) / `*.parquet.bak2`(데이터 확장 B 편입 전), 모두 gitignore.
**프론트 배포 산출물 (frontend/public/data/, 커밋됨):** `pois.json`(981개), `od.json`(~5.71MB; `{ids,times}`, null=도달불가/180분초과), `jongno_boundary.geojson`(~94KB).
**cat2 분포(981):** 카페200 / 한식169 / 기타관광160 / 거리·자연150 / 식당기타125 / 술집106 / 명소·유적37 / 문화시설20 / 서점10 / 쇼핑4.

> ⚠️ **보행그래프 스냅 함정(교훈):** pyrosm 보행망(`retain_all=True`)에 **끊긴 섬(island) 노드**가 존재 → 신규 노드를 단순 최근접 스냅하면 고립 컴포넌트에 붙어 도달 0/946 NaN. **최대 연결 컴포넌트(giant component)로 제한 스냅** 필수. (교보문고 첫 드라이런서 발견·수정. 검증: 교보↔경복궁 12.3분, NaN 2.1%)

---

## 9. 도달성 엔진 (레이어 B) — ✅ 완성 (Python + JS 포팅)
`backend/reachability.py`: `reachable(current, budget, category_filter, visited)` — OD+체류 ≤ 예산, STAY={음식점40,카페20,관광명소30}/기본30, NaN·자기·visited 제외, 정렬, remaining 반환.
**JS 포팅** (`frontend/src/App.jsx`): cat2 필터. ⚠️ POI 좌표 필드명 `lon`(`lng` 아님 — `.lng` 쓰면 흰화면 크래시). 단 Leaflet 이벤트 `e.latlng.lng`는 표준 속성이라 그대로 사용(POI `.lon`과 무관).
**예산별 그리디 체인 길이(참고):** 30분=1곳 / 60분=2 / 120분=3 / 180분=5. 체류시간이 체인 길이 지배. 도보순 그리디는 도보 0분 후보를 계속 골라 "제자리 맴돎" 경향(→ NN 랭커가 최종 해결, future work).

---

## 10~11. v1.0 folium / v1.1 React — ✅ 완성
- folium: `scripts/make_map.py` → `outputs/reachability_map.html`(`.gitattributes` linguist-generated).
- React: `frontend/src/App.jsx` — VWorld 타일, 시간버튼, cat2 7색, 호버 툴팁, A→B→C 체이닝+undo, 종로 경계, **출발점 선택(클릭+GPS, D21), 마커 클러스터링(D24)**.

---

## 12. 레포 구조 / 환경
**레포:** `github.com/urbsn4i-sw/jongno-walkcourse` (공개). **커밋 신원 = Dorothy / urban4i.sw@gmail.com**. 초기 커밋은 옛 `wonlab144` 유지.
**구조:** `scripts/`(12, add_kyobo 포함) / `backend/` / `outputs/` / `frontend/` / `notebooks/`(README.md + jongno_walkcourse.ipynb) / `models/`(비어있음) / `archive/`(Foursquare CSV 102MB, gitignore) / `cache/`.
`.gitignore`: 원본 parquet·`.bak`·`.env`·`archive/`·`_kyobo_cache.json`·`PROJECT_HANDOFF_v*.md`·`/jongno_walkcourse.ipynb`(루트 사본 한정) 무시. 핸드오프 본체는 **`PROJECT_HANDOFF.md` 하나**만 추적.
**환경:** Windows / Anaconda Python 3.12 / Node v24.17.0 / Claude Code(데스크톱, Max) / Colab.
**API 키(.env, gitignore):** KAKAO✅ NAVER✅ TOURAPI✅ VITE_VWORLD_KEY✅.
**HF Space:** `urban4isw/jongno-nn-ranker` (Gradio, CPU). 모델 `nn_l2_ranker.pt` + `nn_l2_meta.json`(poi2idx·poi_to_cat·poi_catname) + `app.py` 업로드.

---

## 13. 현재 상태 / 다음 행동  ← **새 채팅에서 여기부터 확인**
**완료:**
- **v1.0:** 데이터 파이프라인 + 도달성 엔진 + folium.
- **v1.1 (앱):** React 앱 — VWorld 한글 지도, 시간버튼, A→B→C 체이닝+undo, cat2 7색, 호버 툴팁, 종로 경계, **출발점 선택(클릭+GPS, D21)**, **마커 클러스터링(D24)**, attribution(🇰🇷 urbsn4i-sw).
- **데이터:** **교보문고 광화문점 OD 편입(947 노드, D25)**.
- **NN/ML:** L1·L2 + **고전 ML(RF·로지스틱·KNN) 비교 완료** — NN L2 R@1·NDCG 1위, 종합 NN 우위(6번).
- **NN L3 ablation:** 순서 모델(LSTM) 무익 입증, 챔피언 L2 확정.
- **데이터 확장 B (D26):** 서점10·문화시설20·쇼핑4 = 34개 (b)증분 OD 편입 → **981 노드, cat2 10종**. 배포 갱신 완료.
- **GitHub Pages 배포 완료:** urbsn4i-sw.github.io/jongno-walkcourse/ (Claude Code 무관 상시 접속).
- **Hugging Face NN 데모 배포:** L2 랭커 Gradio 데모 라이브 (huggingface.co/spaces/urban4isw/jongno-nn-ranker). 모델 .pt 저장 → HF Space.
- 전부 GitHub push·동기화. (최신 커밋: `28cbbbf`)

**미구현 / 다음 후보:**
1. **(다) 마무리 / Hugging Face** — OD 경량화(od.json 5.71MB) · README 영어화 · 라이선스(MIT) · 위성지도 토글 · (선택) Hugging Face Spaces 배포.
2. **백엔드 FastAPI (D22)** — 도보거리 스냅·라우팅.
3. **NN 랭커 앱 연결 (C 레이어)** — Foursquare 검증 모델/신호를 앱 추천에 연결.

> ⚠️ **Claude Code는 새 채팅 불필요.** Colab은 "모두 실행" + CSV 재업로드로 복원.
> **작업 방식:** claude.ai(상담/설계)=결정·지시(붙여넣기용 코드블록) / Claude Code(실행)=명령·파일편집 / Colab(NN)=셀 단위. 모든 답변 한국어, 끝에 "2.지금까지 / 3.다음으로" 두 섹션 고정.

---

## 14. Future Work (명시적 보류)
- 다국어 UI / README 영어화 · 보행시간 정밀화(신호·계단) · 출발점 도보거리 스냅(백엔드) · OD 경량화 · 관광 세분 정밀화 · 교보문고 서점 재분류 · RL·확산 모델 · 성·연령 학습 개인화 · 단계별 카테고리 다양성 · 후보 정렬 "제자리 맴돎" 개선(NN 랭커로) · **위성지도 토글(VWorld Satellite)** · 백엔드 공개 호스팅(D22) · NN L4 · **NN·고전ML 랭커를 종로 앱에 실제 연결**(현재 Foursquare로 방법 검증까지) · **네이버 플레이스 인기신호 보조**(지역 API 5건 캡 → 인기순 top5를 가중치로만) · **영업상태 교차검증 신뢰도 표시**(카카오·네이버 모두 부정확 → 신뢰도 배지).

---

## 15. 변경 이력
- **v1~v3:** 초기~v1.0 완성(데이터 파이프라인·도달성 엔진·folium).
- **v4:** v1.1 React(A안) — VWorld 한글 지도, 체이닝+undo, cat2 7종, 종로 경계, 툴팁.
- **v5:** NN 트랙 1차(L1·L2) — Foursquare NYC next-POI(D23), L2 전 지표 베이스라인 초과. username `urbsn4i-sw` 확정.
- **v6:** **출발점 선택(D21) 완료**(클릭+GPS) · **표시 정책 확정(D24)**(예산기반 도달후보 + 클러스터링; 카운트컷·거리창 폐기, 단조성 버그 해결) · **교보문고 OD 편입(D25, 947 노드)** · **고전 ML(RF·로지스틱·KNN) vs NN 비교 완료**(6번; NN L2 R@1·NDCG 1위, RF R@10 1위) · attribution(🇰🇷 urbsn4i-sw, D16) · 보행그래프 고립노드 스냅 함정(8번) · 예산별 체인 길이(9번). 다음=L3(선택)·데이터확장B·백엔드.
- **v7:** NN L3 ablation 완료(순서 무익, 챔피언 L2) · GitHub Pages 배포 완료. 다음=데이터확장 B.
- **v8:** 데이터 확장(B) 완료(D26) — 서점·문화시설·쇼핑 34개 (b)증분 OD 편입(947→981, cat2 7→10종, add_expansion.py). 네이버 지역 API 5건 캡으로 수집 부적합(카카오 유지, 인기신호 보조는 future work). 영업상태 교차검증 신뢰도=future work. 배포 갱신. 다음=(다)마무리/Hugging Face.
- 이후 변경은 여기에 한 줄씩 추가.
