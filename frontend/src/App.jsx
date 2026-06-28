import { useState, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, CircleMarker, Polyline, Tooltip, GeoJSON, useMapEvents } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({ iconRetinaUrl: markerIcon2x, iconUrl: markerIcon, shadowUrl: markerShadow })

const TIME_OPTIONS = [
  { label: '30분', minutes: 30 }, { label: '1시간', minutes: 60 },
  { label: '2시간', minutes: 120 }, { label: '3시간', minutes: 180 },
]
// cat2 7종 + 전체
const CAT2 = [
  { label: '전체', value: null }, { label: '한식', value: '한식' },
  { label: '술집', value: '술집' }, { label: '식당', value: '식당(기타)' },
  { label: '카페', value: '카페' }, { label: '명소·유적', value: '명소·유적' },
  { label: '거리·자연', value: '거리·자연' }, { label: '기타관광', value: '기타관광' },
]
const CAT2_COLOR = {
  '한식': '#e53e3e', '술집': '#dd6b20', '식당(기타)': '#d69e2e', '카페': '#805ad5',
  '명소·유적': '#38a169', '거리·자연': '#319795', '기타관광': '#718096',
}
// 표시 정책: 남은 예산 내 도달 가능한 모든 후보를 표시(컷·거리창 없음).
// 예산↑ = 도달후보 superset → 단조성 자연 성립. 빽빽함은 클러스터링으로 해소.
const SNAP_MAX_KM = 2  // 최근접 노드가 이보다 멀면 종로 권역 밖으로 간주

// 하버사인 직선거리(km)
function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

// 임의 좌표 → 가장 가까운 POI 노드 인덱스. 2km 초과면 null(권역 밖)
function nearestNode(lat, lon, pois) {
  let best = -1, bestD = Infinity
  for (let i = 0; i < pois.length; i++) {
    const d = haversineKm(lat, lon, pois[i].lat, pois[i].lon)
    if (d < bestD) { bestD = d; best = i }
  }
  return bestD > SNAP_MAX_KM ? null : best
}

// 지도 클릭 → onPick(lat, lng)
function ClickHandler({ onPick }) {
  useMapEvents({ click(e) { onPick(e.latlng.lat, e.latlng.lng) } })
  return null
}

function reachable(currentIdx, budget, pois, times, visited, catFilter) {
  const row = times[currentIdx]
  if (!row) return []
  const out = []
  for (let j = 0; j < pois.length; j++) {
    if (j === currentIdx || visited.has(j)) continue
    const p = pois[j]
    if (catFilter && p.cat2 !== catFilter) continue
    const t = row[j]
    if (t === null || t === undefined) continue
    const cost = t + p.stay
    if (cost <= budget) out.push({ idx: j, ...p, od: t, remaining: Math.round((budget - cost) * 10) / 10 })
  }
  // 도보시간 오름차순(가까운 곳 우선) → 동률은 hotspot 내림차순.
  // 가까운 후보가 상위에 와서, 예산을 키워도 30분 후보가 상위에 유지됨(단조성).
  out.sort((a, b) => a.od - b.od || b.score - a.score)
  return out
}

export default function App() {
  const [pois, setPois] = useState(null)
  const [times, setTimes] = useState(null)
  const [boundary, setBoundary] = useState(null)
  const [startIdx, setStartIdx] = useState(null)
  const [initialBudget, setInitialBudget] = useState(null)
  const [catFilter, setCatFilter] = useState(null)
  const [path, setPath] = useState([])
  const [err, setErr] = useState(null)
  const [locating, setLocating] = useState(false)

  useEffect(() => {
    const base = import.meta.env.BASE_URL
    Promise.all([
      fetch(`${base}data/pois.json`).then((r) => r.json()),
      fetch(`${base}data/od.json`).then((r) => r.json()),
      fetch(`${base}data/jongno_boundary.geojson`).then((r) => r.json()).catch(() => null),
    ]).then(([poisData, odData, geo]) => {
      setPois(poisData); setTimes(odData.times); setBoundary(geo)
      const gi = poisData.findIndex((p) => p.name.includes('경복궁'))
      setStartIdx(gi >= 0 ? gi : 0)
    }).catch((e) => setErr(String(e)))
  }, [])

  function selectBudget(min) {
    if (!pois || startIdx === null) return
    setInitialBudget(min)
    setPath([{ idx: startIdx, name: pois[startIdx].name, budgetBefore: min }])
  }

  // 지도 클릭 → 최근접 노드로 출발점 변경 (D21, 직선거리 스냅)
  function handlePickStart(lat, lng) {
    if (!pois) return
    if (path.length >= 2) return  // 동선 진행 중이면 실수 방지 위해 무시
    const idx = nearestNode(lat, lng, pois)
    if (idx === null) { alert('종로 권역 밖입니다. 종로 근처를 클릭하세요'); return }
    setStartIdx(idx)
    // 출발점 변경 → 동선 초기화 (예산 선택 상태면 새 출발점으로 재설정)
    if (initialBudget !== null) {
      setPath([{ idx, name: pois[idx].name, budgetBefore: initialBudget }])
    }
  }

  // GPS "내 위치에서 시작" — 좌표만 획득 후 동일한 handlePickStart(스냅) 경로 사용
  function handleUseMyLocation() {
    if (!navigator.geolocation) {
      alert('위치를 가져올 수 없어요. 지도를 클릭해 출발점을 정해주세요'); return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        handlePickStart(pos.coords.latitude, pos.coords.longitude)  // 스냅·권역밖·동선잠금 가드 동일 적용
      },
      () => {
        setLocating(false)
        alert('위치를 가져올 수 없어요. 지도를 클릭해 출발점을 정해주세요')
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  const current = path.length ? path[path.length - 1] : null
  const remaining = current ? current.budgetBefore : null

  const candidates = useMemo(() => {
    if (!pois || !times || !current || remaining === null) return []
    const visited = new Set(path.map((s) => s.idx))
    return reachable(current.idx, remaining, pois, times, visited, catFilter)
  }, [pois, times, path, remaining, catFilter, current])

  function pickCandidate(c) {
    setPath((prev) => [...prev, { idx: c.idx, name: c.name, budgetBefore: c.remaining }])
  }
  function undo() { setPath((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev)) }

  const start = pois && startIdx !== null ? pois[startIdx] : null
  const center = start ? [start.lat, start.lon] : [37.5796, 126.977]
  const pathLatLng = path.map((s) => [pois[s.idx].lat, pois[s.idx].lon])

  return (
    <div style={{ position: 'relative', height: '100vh', width: '100vw' }}>
      <div style={barStyle}
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}>
        <span style={{ fontSize: 13, color: '#444', whiteSpace: 'nowrap' }}>
          출발: <b>{start ? start.name : '—'}</b>
        </span>
        <span style={{ width: 1, height: 24, background: '#ddd' }} />
        <div style={{ display: 'flex', gap: 6 }}>
          {TIME_OPTIONS.map((o) => (
            <button key={o.minutes} disabled={!pois} onClick={() => selectBudget(o.minutes)}
              style={initialBudget === o.minutes ? selBtn : btn}>{o.label}</button>
          ))}
        </div>
        <button disabled={!pois || locating} onClick={handleUseMyLocation}
          style={{ ...btn, opacity: (!pois || locating) ? 0.6 : 1 }}>
          {locating ? '위치 확인 중…' : '📍 내 위치에서 시작'}
        </button>
        {initialBudget !== null && (
          <>
            <span style={{ width: 1, height: 24, background: '#ddd' }} />
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', maxWidth: 460 }}>
              {CAT2.map((c) => (
                <button key={c.label} onClick={() => setCatFilter(c.value)}
                  style={catFilter === c.value ? selBtnSm : btnSm}>{c.label}</button>
              ))}
            </div>
            <button onClick={undo} disabled={path.length <= 1}
              style={{ ...btnSm, opacity: path.length <= 1 ? 0.4 : 1 }}>← 뒤로</button>
          </>
        )}
      </div>

      {initialBudget !== null && (
        <div style={panelStyle}>
          <b>동선</b> (남은 예산 {remaining}분)
          <div style={{ marginTop: 6 }}>
            {path.map((s, i) => (<div key={i}>{String.fromCharCode(65 + i)}. {s.name}</div>))}
          </div>
          <div style={{ marginTop: 6, color: '#777' }}>
            {candidates.length > 0 ? `다음 후보 ${candidates.length}곳` : '더 갈 곳 없음 — 동선 완성'}
          </div>
          <div style={{ marginTop: 6, color: '#999', fontSize: 12 }}>
            {path.length >= 2
              ? '※ 동선 진행 중 — 출발점 변경 잠금(뒤로 가기로 해제)'
              : '※ 지도를 클릭해 출발점을 바꿀 수 있어요'}
          </div>
        </div>
      )}

      {!pois && !err && <div style={overlayMsg}>데이터 불러오는 중…</div>}
      {err && <div style={overlayMsg}>로드 실패: {err}</div>}
      {pois && initialBudget === null && (
        <div style={overlayMsg}>지도를 클릭해 출발점을 정하고, 위에서 시간을 선택하세요</div>
      )}

      <MapContainer center={center} zoom={15} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.vworld.kr/">공간정보 오픈플랫폼(브이월드)</a>'
          url={`https://api.vworld.kr/req/wmts/1.0.0/${import.meta.env.VITE_VWORLD_KEY}/white/{z}/{y}/{x}.png`}
          maxZoom={19} />

        <ClickHandler onPick={handlePickStart} />

        {boundary && (
          <GeoJSON data={boundary} style={{ color: '#2b6cb0', weight: 2, fill: true, fillColor: '#2b6cb0', fillOpacity: 0.04, dashArray: '5,5' }} />
        )}

        {path.map((s, i) => (
          <Marker key={`p${i}`} position={[pois[s.idx].lat, pois[s.idx].lon]}>
            <Popup>{String.fromCharCode(65 + i)}. {pois[s.idx].name}</Popup>
          </Marker>
        ))}
        {pathLatLng.length > 1 && <Polyline positions={pathLatLng} pathOptions={{ color: '#2b6cb0', weight: 4 }} />}

        {/* 후보 = 남은 예산 내 도달 가능한 전부. 빽빽함은 클러스터로 묶음(확대 시 펼쳐짐).
            key 에 출발점·잔여예산 포함 → 예산/출발점 변경 시 클러스터 깨끗이 remount. */}
        <MarkerClusterGroup
          key={`cl-${current?.idx}-${remaining}`}
          chunkedLoading
          zoomToBoundsOnClick={false}
          spiderfyOnMaxZoom={true}
          spiderfyOnEveryZoom={true}
          showCoverageOnHover={false}
        >
          {candidates.map((c) => (
            <CircleMarker key={c.idx} center={[c.lat, c.lon]} radius={8}
              eventHandlers={{ click: () => pickCandidate(c) }}
              pathOptions={{ color: CAT2_COLOR[c.cat2] || '#888', fillColor: CAT2_COLOR[c.cat2] || '#888', fillOpacity: 0.85, weight: 1 }}>
              <Tooltip>{c.name} · {c.cat2} · 도보 {c.od}분</Tooltip>
              <Popup>
                <b>{c.name}</b><br />{c.cat2} · {c.gu}<br />
                도보 {c.od}분 · 체류 {c.stay}분 · 방문 후 잔여 {c.remaining}분<br />
                <i>클릭하면 동선에 추가</i>
              </Popup>
            </CircleMarker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>
    </div>
  )
}

const barStyle = { position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'rgba(255,255,255,0.96)', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }
const panelStyle = { position: 'absolute', top: 78, left: 12, zIndex: 1000, minWidth: 180, padding: '10px 12px', background: 'rgba(255,255,255,0.96)', borderRadius: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.15)', fontSize: 14 }
const btn = { padding: '7px 12px', border: '1px solid #d0d0d0', borderRadius: 8, background: '#fff', color: '#333', cursor: 'pointer', fontSize: 14 }
const selBtn = { ...btn, background: '#2b6cb0', color: '#fff', border: '1px solid #2b6cb0', fontWeight: 600 }
const btnSm = { ...btn, padding: '5px 9px', fontSize: 13 }
const selBtnSm = { ...btnSm, background: '#2b6cb0', color: '#fff', border: '1px solid #2b6cb0', fontWeight: 600 }
const overlayMsg = { position: 'absolute', top: 78, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, background: 'rgba(255,255,255,0.96)', padding: '6px 12px', borderRadius: 8, fontSize: 14 }
