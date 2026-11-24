# Design: data flow, threading and concurrency (§4–5)

Part of the design ([summary](../design.md)). Section numbers are stable; cite them as §N.

## 4. Data flow

1. **Frames.** The camera delivers 30 or 60 frames/s to the data queue. Late frames are discarded by AVFoundation, never queued.
2. **Motion** (every frame, or every second frame at 60 fps): `MotionEstimator` compares the motion window of this frame with the previous one; `DirectionTracker` updates speed, MD and the line-stopped state.
3. **Shot selection.** `ShotScheduler` decides whether this frame is a shot (due, analysis buffer free, line moving). For a shot, the ROI plus a filter margin is copied out of the camera buffer into a pooled `LumaImage` (about 1 ms for 4 MP) and the camera buffer is released at once. A `FrameContext` value (timestamps, exposure, ISO, lens position, intrinsics, MD, speed, tilt) goes with it.
4. **Analysis.** The analysis queue runs `FrameAnalyzer` on one shot at a time and produces a `FrameResult` value.
5. **Aggregation and outputs.** `RunAggregator` (analysis queue) holds each shot's result for the MD-change delay (§6.8 step 7), then adds it to the run if it is included. The recorder gets rows for the run I/O queue; the main actor gets a coalesced `LiveSnapshot` at most 4 times per second (a single latest-value slot, so a slow UI never builds a backlog); the remote link reads the latest snapshot for its 4 Hz status.
6. **Remote preview.** While a remote has the preview open, every 200–500 ms the data queue downscales the frame and a utility queue encodes a JPEG; the link sends it only when the previous preview has left the connection (one in flight), otherwise the picture is dropped.
7. **Stop.** The scheduler stops taking shots, the analysis queue drains, the held shots are settled (§6.8 step 7), the recorder writes `Histogram.csv`, `Summary.*` and completes `Run.json`, then removes the marker. The run has been in the library since Start (its `Run.json` is written then), marked *Recording*; it now shows as finished. A run that stops with an error skips this step: the recorder closes its files and leaves the marker, and the recovery scan that `RunStore` then starts repairs it and lists it as incomplete (§3.6).

## 5. Threading and concurrency

Swift 5 language mode as Phone LiDAR (§10.9); safety rests on the same written rules: one owner per piece of state, values (not references) crossing queues, `@unchecked Sendable` only for immutable or queue-confined types with a comment.

| Execution context | Owns / runs |
|---|---|
| Main actor | SwiftUI, `ScanModel`, `RunStore`, `RemoteLink`, `AppSettings`; applies `LiveSnapshot`s; starts/stops runs. |
| `flakescanner.capture.session` (serial) | `startRunning` / `stopRunning`, device configuration (format, exposure, focus, white balance, torch), restarts after errors. |
| `flakescanner.capture.data` (serial, `.userInitiated`) | Sample-buffer delegate; `MotionEstimator`, `DirectionTracker`, `ShotScheduler`, `LevelMonitor`; `TargetTracker` in target mode; ROI copy; preview downscale. |
| `flakescanner.analysis` (serial, `.userInitiated`) | `FrameAnalyzer`, `RunAggregator`; one shot at a time from a pool of two buffers. |
| `flakescanner.preview` (serial, `.utility`) | JPEG encoding for the remote; drops work when busy. |
| `flakescanner.run.io` (serial, `.utility`) | `RunRecorder` writes; summaries at Stop. |
| `flakescanner.remote.link` (serial) | All Network framework handlers and `RemoteConnection` state, as Phone LiDAR. |
| Detached tasks | Library loads, chart preparation, run sizes, recovery scan (skips the active run, §3.6). |

Rules for new code: never touch UI or `@Observable` state off the main actor; hand results over as values; check cancellation after `await`; no blocking work on the main actor; camera buffers are never held across queues (copy the ROI); the analysis pool is fixed (no growth with run length).

## 6. Algorithms

