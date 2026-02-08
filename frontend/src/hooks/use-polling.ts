import { useEffect, useRef } from 'react';

// 通用轮询：回调返回 true 时停止
export function usePolling(
  callback: () => Promise<boolean>,
  interval: number,
  enabled: boolean,
) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (stopped || inFlight) return;
      inFlight = true;
      try {
        const shouldStop = await savedCallback.current();
        if (!stopped && !shouldStop) {
          timer = setTimeout(tick, interval);
        }
      } finally {
        inFlight = false;
      }
    };
    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [interval, enabled]);
}
