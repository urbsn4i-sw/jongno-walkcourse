import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// ── Vite 번들에서 기본 마커 아이콘이 깨지는 문제 해결 ──
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

// 출발점: 경복궁 (folium 데모의 A 지점과 동일)
const START = { name: '경복궁', lat: 37.5796, lng: 126.977 }

export default function App() {
  return (
    <MapContainer
      center={[START.lat, START.lng]}
      zoom={15}
      scrollWheelZoom={true}
      style={{ height: '100vh', width: '100vw' }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.vworld.kr/">공간정보 오픈플랫폼(브이월드)</a>'
        url={`https://api.vworld.kr/req/wmts/1.0.0/${import.meta.env.VITE_VWORLD_KEY}/white/{z}/{y}/{x}.png`}
        maxZoom={19}
      />
      <Marker position={[START.lat, START.lng]}>
        <Popup>출발점: {START.name}</Popup>
      </Marker>
    </MapContainer>
  )
}
