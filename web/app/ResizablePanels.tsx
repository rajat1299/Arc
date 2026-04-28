"use client";

import type { CSSProperties, KeyboardEvent, PointerEvent, ReactNode } from "react";
import { useCallback, useMemo, useRef, useState } from "react";

type Props = {
  runs: ReactNode;
  trace: ReactNode;
  detail: ReactNode;
};

type DragState = {
  handle: "runs" | "detail";
  startX: number;
  startRunsWidth: number;
  startDetailWidth: number;
};

const DEFAULT_RUNS_WIDTH = 380;
const DEFAULT_DETAIL_WIDTH = 372;
const MIN_RUNS_WIDTH = 280;
const MIN_DETAIL_WIDTH = 280;
const MIN_TRACE_WIDTH = 360;
const HANDLE_WIDTH = 9;

export function ResizablePanels({ runs, trace, detail }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [runsWidth, setRunsWidth] = useState(DEFAULT_RUNS_WIDTH);
  const [detailWidth, setDetailWidth] = useState(DEFAULT_DETAIL_WIDTH);
  const [dragging, setDragging] = useState<DragState["handle"] | null>(null);

  const clampWidths = useCallback((nextRunsWidth: number, nextDetailWidth: number) => {
    const availableWidth = containerRef.current?.clientWidth ?? 0;
    const maxSideTotal =
      availableWidth > 0
        ? Math.max(MIN_RUNS_WIDTH + MIN_DETAIL_WIDTH, availableWidth - MIN_TRACE_WIDTH - HANDLE_WIDTH * 2)
        : Number.POSITIVE_INFINITY;

    let clampedRuns = clamp(nextRunsWidth, MIN_RUNS_WIDTH, maxSideTotal - MIN_DETAIL_WIDTH);
    let clampedDetail = clamp(nextDetailWidth, MIN_DETAIL_WIDTH, maxSideTotal - clampedRuns);

    if (clampedRuns + clampedDetail > maxSideTotal) {
      const overflow = clampedRuns + clampedDetail - maxSideTotal;
      if (nextRunsWidth !== runsWidth) {
        clampedRuns = Math.max(MIN_RUNS_WIDTH, clampedRuns - overflow);
      } else {
        clampedDetail = Math.max(MIN_DETAIL_WIDTH, clampedDetail - overflow);
      }
    }

    return { runs: Math.round(clampedRuns), detail: Math.round(clampedDetail) };
  }, [runsWidth]);

  const applyWidths = useCallback(
    (nextRunsWidth: number, nextDetailWidth: number) => {
      const clamped = clampWidths(nextRunsWidth, nextDetailWidth);
      setRunsWidth(clamped.runs);
      setDetailWidth(clamped.detail);
    },
    [clampWidths],
  );

  const onWindowPointerMove = useCallback(
    (event: globalThis.PointerEvent) => {
      const drag = dragRef.current;
      if (drag === null) {
        return;
      }

      const delta = event.clientX - drag.startX;
      if (drag.handle === "runs") {
        applyWidths(drag.startRunsWidth + delta, detailWidth);
      } else {
        applyWidths(runsWidth, drag.startDetailWidth - delta);
      }
    },
    [applyWidths, detailWidth, runsWidth],
  );

  const stopDrag = useCallback(() => {
    dragRef.current = null;
    setDragging(null);
    document.body.classList.remove("is-resizing-panels");
    window.removeEventListener("pointermove", onWindowPointerMove);
    window.removeEventListener("pointerup", stopDrag);
    window.removeEventListener("pointercancel", stopDrag);
  }, [onWindowPointerMove]);

  const beginDrag = useCallback(
    (handle: DragState["handle"], event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      dragRef.current = {
        handle,
        startX: event.clientX,
        startRunsWidth: runsWidth,
        startDetailWidth: detailWidth,
      };
      setDragging(handle);
      document.body.classList.add("is-resizing-panels");
      window.addEventListener("pointermove", onWindowPointerMove);
      window.addEventListener("pointerup", stopDrag);
      window.addEventListener("pointercancel", stopDrag);
    },
    [detailWidth, onWindowPointerMove, runsWidth, stopDrag],
  );

  const onHandleKeyDown = useCallback(
    (handle: DragState["handle"], event: KeyboardEvent<HTMLDivElement>) => {
      const step = event.shiftKey ? 40 : 16;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        if (handle === "runs") {
          applyWidths(runsWidth - step, detailWidth);
        } else {
          applyWidths(runsWidth, detailWidth + step);
        }
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        if (handle === "runs") {
          applyWidths(runsWidth + step, detailWidth);
        } else {
          applyWidths(runsWidth, detailWidth - step);
        }
      }
      if (event.key === "Home") {
        event.preventDefault();
        if (handle === "runs") {
          applyWidths(MIN_RUNS_WIDTH, detailWidth);
        } else {
          applyWidths(runsWidth, MIN_DETAIL_WIDTH);
        }
      }
      if (event.key === "End") {
        event.preventDefault();
        if (handle === "runs") {
          applyWidths(DEFAULT_RUNS_WIDTH, detailWidth);
        } else {
          applyWidths(runsWidth, DEFAULT_DETAIL_WIDTH);
        }
      }
    },
    [applyWidths, detailWidth, runsWidth],
  );

  const style = useMemo(
    () =>
      ({
        "--runs-width": `${runsWidth}px`,
        "--detail-width": `${detailWidth}px`,
      }) as CSSProperties,
    [detailWidth, runsWidth],
  );

  return (
    <div
      className={`content${dragging !== null ? ` is-dragging-${dragging}` : ""}`}
      ref={containerRef}
      style={style}
    >
      {runs}
      <ResizeHandle
        label="Resize runs panel"
        max={640}
        min={MIN_RUNS_WIDTH}
        now={runsWidth}
        onDoubleClick={() => applyWidths(DEFAULT_RUNS_WIDTH, detailWidth)}
        onKeyDown={(event) => onHandleKeyDown("runs", event)}
        onPointerDown={(event) => beginDrag("runs", event)}
      />
      {trace}
      <ResizeHandle
        label="Resize span detail panel"
        max={560}
        min={MIN_DETAIL_WIDTH}
        now={detailWidth}
        onDoubleClick={() => applyWidths(runsWidth, DEFAULT_DETAIL_WIDTH)}
        onKeyDown={(event) => onHandleKeyDown("detail", event)}
        onPointerDown={(event) => beginDrag("detail", event)}
      />
      {detail}
    </div>
  );
}

function ResizeHandle({
  label,
  max,
  min,
  now,
  onDoubleClick,
  onKeyDown,
  onPointerDown,
}: {
  label: string;
  max: number;
  min: number;
  now: number;
  onDoubleClick: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemax={max}
      aria-valuemin={min}
      aria-valuenow={now}
      className="resize-handle"
      onDoubleClick={onDoubleClick}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      role="separator"
      tabIndex={0}
    />
  );
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}
