"use client";
/**
 * DisasterStateContext.tsx
 *
 * React context that maintains the live DisasterState from the autonomous loop.
 * Connects to the backend WebSocket (/alerts/ws) and parses DISASTER_STATE_UPDATE
 * and LOOP_HEARTBEAT messages.
 *
 * On page load, hydrates from GET /simulate/current-state before the WS connects.
 * On WS disconnect, shows a "Reconnecting..." badge and retries automatically.
 */

import React, {
  createContext, useContext, useEffect, useRef, useState, useCallback
} from "react";
import {
  DisasterStateUpdate, LoopHeartbeat, WsDisasterMessage,
  getCurrentDisasterState,
} from "@/lib/api";

const WS_URL =
  typeof window !== "undefined"
    ? `ws://${window.location.hostname === "localhost" ? "127.0.0.1" : window.location.hostname}:8000/alerts/ws`
    : "ws://127.0.0.1:8000/alerts/ws";

const RECONNECT_DELAY_MS = 3000;

interface DisasterStateCtx {
  state: DisasterStateUpdate | null;
  lastHeartbeat: LoopHeartbeat | null;
  wsStatus: "connected" | "disconnected" | "reconnecting";
  loopSeq: number;
  lastUpdated: string | null;
}

const DisasterStateContext = createContext<DisasterStateCtx>({
  state: null,
  lastHeartbeat: null,
  wsStatus: "disconnected",
  loopSeq: 0,
  lastUpdated: null,
});

export function DisasterStateProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<DisasterStateUpdate | null>(null);
  const [lastHeartbeat, setLastHeartbeat] = useState<LoopHeartbeat | null>(null);
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected" | "reconnecting">("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Hydrate from REST on mount (before WS connects)
  useEffect(() => {
    getCurrentDisasterState().then((data) => {
      if ("type" in data && data.type === "DISASTER_STATE_UPDATE") {
        setState(data as DisasterStateUpdate);
      }
    }).catch(() => {/* backend not ready yet — WS will deliver state soon */});
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus("connected");
      if (retryRef.current) clearTimeout(retryRef.current);
    };

    ws.onmessage = (evt) => {
      try {
        const msg: WsDisasterMessage = JSON.parse(evt.data);
        if (msg.type === "DISASTER_STATE_UPDATE") {
          setState(msg as DisasterStateUpdate);
        } else if (msg.type === "LOOP_HEARTBEAT") {
          setLastHeartbeat(msg as LoopHeartbeat);
        }
      } catch {
        // Non-JSON message from existing alert system — ignore
      }
    };

    ws.onclose = () => {
      setWsStatus("reconnecting");
      retryRef.current = setTimeout(() => {
        setWsStatus("reconnecting");
        connect();
      }, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const loopSeq = state?.sequence_no ?? lastHeartbeat?.sequence_no ?? 0;
  const lastUpdated = state?.observed_at ?? lastHeartbeat?.observed_at ?? null;

  return (
    <DisasterStateContext.Provider value={{ state, lastHeartbeat, wsStatus, loopSeq, lastUpdated }}>
      {children}
    </DisasterStateContext.Provider>
  );
}

export function useDisasterState() {
  return useContext(DisasterStateContext);
}
