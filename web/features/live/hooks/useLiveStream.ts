"use client";

import { useEffect, useRef, useState } from "react";
import type { LiveFrame } from "@/lib/data";
import { getApiKey } from "@/lib/auth";

type Status = "idle" | "connecting" | "live" | "error" | "closed";

export function useLiveStream(streamId: string | null) {
  const [status, setStatus] = useState<Status>(streamId ? "connecting" : "idle");
  const [telemetry, setTelemetry] = useState<LiveFrame | null>(null);
  const frameRef = useRef<LiveFrame | null>(null);
  const subscribers = useRef<Set<(f: LiveFrame) => void>>(new Set());

  useEffect(() => {
    if (!streamId) return;

    let ws: WebSocket | null = null;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;

    const connect = async () => {
      setStatus("connecting");
      try {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = window.location.host;
        let wsUrl = `${protocol}//${host}/api/ws/streams/${streamId}`;

        // Mint ticket if auth is configured
        const apiKey = getApiKey();
        if (apiKey) {
          try {
            const ticketRes = await fetch(`/api/streams/${streamId}/ws-ticket`, {
              method: "POST",
              headers: { "X-API-Key": apiKey },
            });
            if (ticketRes.ok) {
              const ticketData = await ticketRes.json();
              if (ticketData.ticket) {
                wsUrl += `?ticket=${encodeURIComponent(ticketData.ticket)}`;
              }
            }
          } catch {
            // fallback to direct attempt
          }
        }

        if (cancelled) return;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          attempt = 0;
          setStatus("live");
        };

        ws.onmessage = (event) => {
          try {
            const frame = JSON.parse(event.data) as LiveFrame;
            frameRef.current = frame;
            // Imperative canvas notify (zero React re-renders)
            subscribers.current.forEach((fn) => fn(frame));
            // Throttled telemetry state update for metric chips
            if (frame.seq % 5 === 0) {
              setTelemetry(frame);
            }
          } catch {
            // Ignore corrupted frame parse
          }
        };

        ws.onerror = () => {
          setStatus("error");
        };

        ws.onclose = () => {
          if (cancelled) return;
          setStatus("error");
          const delay = Math.min(1000 * 2 ** attempt++, 15000) + Math.random() * 250;
          timer = setTimeout(connect, delay);
        };
      } catch {
        setStatus("error");
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt++, 15000));
      }
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      ws?.close();
      setStatus("closed");
    };
  }, [streamId]);

  return {
    status,
    telemetry,
    subscribe: (fn: (f: LiveFrame) => void) => {
      subscribers.current.add(fn);
      return () => {
        subscribers.current.delete(fn);
      };
    },
  };
}
