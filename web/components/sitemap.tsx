"use client";

import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Map as MaplibreMap, Marker as MaplibreMarker } from "maplibre-gl";

export type MapSite = { id: string; name: string; lat: number; lon: number; status: string };

const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

/**
 * MapLibre GL JS site map (no API key required with the demotiles style).
 * Streams with lat/lon are drawn as markers; the worker URL is pinned through a
 * bundler-resolved asset URL so production builds do not 404 the worker script.
 */
export default function SiteMap({ sites, center, styleUrl }: { sites: MapSite[]; center: [number, number] | null; styleUrl: string | null }) {
  const holder = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MaplibreMap | null>(null);
  const libRef = useRef<typeof import("maplibre-gl") | null>(null);
  const markerRefs = useRef<MaplibreMarker[]>([]);
  const fittedRef = useRef(false);
  const [mapReady, setMapReady] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!holder.current) return;
    let disposed = false;
    import("maplibre-gl")
      .then((lib) => {
        if (disposed || !holder.current) return;
        try {
          const workerUrl = new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url);
          lib.setWorkerUrl?.(workerUrl.href);
        } catch { /* bundler did not rewrite the URL; maplibre falls back to its own resolution */ }
        const map = new lib.Map({
          container: holder.current,
          style: styleUrl || DEFAULT_STYLE,
          center: [center?.[1] ?? 12.4, center?.[0] ?? 41.9],
          zoom: 2,
          attributionControl: { compact: true },
        });
        map.on("error", (event) => {
          const message = (event as unknown as { error?: { message?: string } }).error?.message;
          if (message && !disposed) setNote(message.includes("Failed to fetch worker") ? `Worker failed: ${message}` : message);
        });
        map.on("load", () => { if (!disposed) { setNote(""); setMapReady(true); } });
        libRef.current = lib;
        mapRef.current = map;
      })
      .catch((error: unknown) => { if (!disposed) setNote(`Map could not start: ${error instanceof Error ? error.message : String(error)}`); });
    return () => {
      disposed = true;
      markerRefs.current.forEach((marker) => marker.remove());
      markerRefs.current = [];
      mapRef.current?.remove();
      mapRef.current = null;
      libRef.current = null;
    };
    // Map instance is created once per mount; site markers are synced by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const lib = libRef.current;
    const map = mapRef.current;
    if (!mapReady || !lib || !map) return;
    markerRefs.current.forEach((marker) => marker.remove());
    markerRefs.current = [];
    const placed = sites.filter((site) => Number.isFinite(site.lat) && Number.isFinite(site.lon));
    for (const site of placed) {
      const el = document.createElement("div");
      el.className = `map-marker ${site.status === "live" ? "live" : ""}`;
      el.title = `${site.name} (${site.status})`;
      const marker = new lib.Marker({ element: el, anchor: "bottom" })
        .setLngLat([site.lon, site.lat])
        .setPopup(new lib.Popup({ offset: 24 }).setHTML(`<strong>${site.name}</strong><br>${site.status}`))
        .addTo(map);
      markerRefs.current.push(marker);
    }
    if (placed.length && !fittedRef.current) {
      fittedRef.current = true;
      const bounds = new lib.LngLatBounds();
      placed.forEach((site) => bounds.extend([site.lon, site.lat]));
      if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 56, maxZoom: 12, duration: 0 });
    }
  }, [sites, mapReady]);

  return (
    <div className="map-holder">
      <div className="map-frame" ref={holder} aria-label="Map of configured stream locations" />
      {note && <div className="map-note">{note} · the panel still lists every configured stream below.</div>}
    </div>
  );
}
