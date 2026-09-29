"use client";

import L from "leaflet";
import { Fragment, useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { Day, LatLon, Poi } from "@/lib/api";

import { DAY_COLORS } from "@/lib/colors";

function numberIcon(n: number, color: string, bad: boolean) {
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<div style="width:28px;height:28px;border-radius:50%;background:${color};color:#fff;display:flex;align-items:center;justify-content:center;font:600 13px system-ui;border:2px solid ${bad ? "#fde047" : "#fff"};box-shadow:0 1px 4px rgba(0,0,0,.4)">${n}</div>`,
  });
}

const startIcon = L.divIcon({
  className: "",
  iconSize: [30, 30],
  iconAnchor: [15, 28],
  html: `<div style="font-size:26px;line-height:30px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">📍</div>`,
});

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join(";");
  useEffect(() => {
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 15 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

function ClickToSetStart({ onPick }: { onPick?: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onPick?.(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

interface Props {
  pois: Poi[];
  days: Day[];
  start: LatLon;
  mustVisit?: Set<number>;
  onStartChange?: (lat: number, lon: number) => void;
  onPoiClick?: (poi: Poi) => void;
}

export default function RouteMap({ pois, days, start, mustVisit, onStartChange, onPoiClick }: Props) {
  const onRoute = useMemo(() => new Set(days.flatMap((d) => d.stops.map((s) => s.poi.id))), [days]);
  const fitPoints = useMemo<[number, number][]>(() => {
    const pts: [number, number][] = [[start.lat, start.lon]];
    for (const d of days) for (const s of d.stops) pts.push([s.poi.lat, s.poi.lon]);
    if (pts.length === 1) for (const p of pois) pts.push([p.lat, p.lon]);
    return pts;
  }, [days, pois, start]);

  return (
    <MapContainer center={[start.lat, start.lon]} zoom={12} className="h-full w-full rounded-xl" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds points={fitPoints} />
      {onStartChange && <ClickToSetStart onPick={onStartChange} />}

      {pois
        .filter((p) => !onRoute.has(p.id))
        .map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lon]}
            radius={mustVisit?.has(p.id) ? 7 : 5}
            pathOptions={{ color: mustVisit?.has(p.id) ? "#c2410c" : "#8a8178", weight: 1.5, fillOpacity: 0.5 }}
            eventHandlers={onPoiClick ? { click: () => onPoiClick(p) } : undefined}
          >
            <Tooltip>{p.name}{mustVisit?.has(p.id) ? " (must-visit)" : ""}</Tooltip>
          </CircleMarker>
        ))}

      {days.map((d) => {
        const color = DAY_COLORS[d.day % DAY_COLORS.length];
        return (
          <Fragment key={d.day}>
            {d.geometry.length > 1 && <Polyline positions={d.geometry} pathOptions={{ color, weight: 4, opacity: 0.8 }} />}
            {d.stops.map((s, i) => (
              <Marker key={s.poi.id} position={[s.poi.lat, s.poi.lon]} icon={numberIcon(i + 1, color, !!s.violation)}>
                <Popup>
                  <strong>{s.poi.name}</strong>
                  <br />
                  {s.start}–{s.end}
                  {s.violation && <div style={{ color: "#b91c1c" }}>⚠ {s.violation}</div>}
                </Popup>
              </Marker>
            ))}
          </Fragment>
        );
      })}

      <Marker
        position={[start.lat, start.lon]}
        icon={startIcon}
        draggable={!!onStartChange}
        eventHandlers={{
          dragend: (e) => {
            const ll = (e.target as L.Marker).getLatLng();
            onStartChange?.(ll.lat, ll.lng);
          },
        }}
      >
        <Tooltip>{start.label}{onStartChange ? " — drag or click the map to move" : ""}</Tooltip>
      </Marker>
    </MapContainer>
  );
}
