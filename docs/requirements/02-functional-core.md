# Requirements: functional, app, capture, ROI, rate, direction, methods (§5.1–5.6)

Part of the requirements ([summary](../requirements.md)). Section numbers are stable; cite them as §N.

## 5. Functional requirements

### 5.1 App shell (FR-APP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-APP-01 | Home offers **Scan** (scanner), **Connect to the other phone** (remote link), **Runs** (library) and **Settings / About** (version, build number, documentation links). | P0, P4 | Planned |
| FR-APP-02 | Portrait layout. The scan screen matches a phone mounted screen-up above the line, like Phone LiDAR's Line scan screen. | P4 | Planned |
| FR-APP-03 | The screen stays awake while the scan screen is open and while the scanner role is on. | P4, P6 | Planned |
| FR-APP-04 | Camera permission: a clear explanation before the system prompt, and a message with a link to Settings when it was denied. | P3 | Planned |
| FR-APP-05 | Settings persist between launches and can be reset to defaults; every run records the settings it used (FR-RUN-02). | P4 | Planned |
| FR-APP-06 | **Diagnostics** (Settings › Diagnostics), because there is no Xcode console: (a) camera report: every back camera's formats with size, frame-rate range, binning, video HDR, distortion-correction and intrinsics-delivery support, exposure and ISO ranges, and the LiDAR depth camera's formats with depth delivery; (b) sample capture: a short burst at a chosen format with locked short exposure, saved as ROI-sized PNGs plus per-frame camera data (timestamps, exposure, ISO, lens position, intrinsics, gravity); (c) light check (flicker index, 50 or 60 Hz mains), readout-time test (two bursts, the second with the phone turned 180°, with plausibility checks, design §6.16) and the LiDAR distance reading (design §6.17); (d) self-test: the built-in synthetic fixture images run through the analysis and are compared with their stored results; (e) everything shared as one zip. Diagnostics files stay on the phone until shared and are never committed. | P0, P2 | Planned |

### 5.2 Capture (FR-CAP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-CAP-01 | Capture uses one fixed physical back camera: the 1× main (wide) camera by default, the telephoto as an option. Virtual multi-camera devices are never used, so the lens cannot switch during a run. | P3 | Planned |
| FR-CAP-02 | The capture format is chosen for accuracy by ranking, not by hard filters: the highest resolution that runs at ≥ 30 fps, preferring formats that are not binned and have the highest maximum frame rate at that resolution (shortest sensor readout, design §6.12). A binned format is used only when no other meets the rate, and is flagged. The user can pick 1080p, 4K or 4:3 12 MP where the camera offers them. | P0, P2, P3 | Planned |
| FR-CAP-03 | Image processing is fixed for the whole run: video stabilization off; video HDR off (no automatic HDR); low-light boost off; a fixed frame duration (no automatic frame-rate changes); geometric distortion correction on where supported; per-frame camera intrinsics delivered where supported (the device probe confirms which image they describe, P0.8). Every applied state is recorded (NFR-REL-04). | P0, P3 | Planned |
| FR-CAP-04 | Exposure modes: **Auto, shutter-limited** (default; the longest allowed shutter follows the motion-blur budget, FR-QUAL-03) and **Manual** (shutter and ISO). Exposure is locked at Start for the whole run (default on). | P3 | Planned |
| FR-CAP-05 | Focus: autofocus on the ROI, then locked (default); tap to refocus; manual lens position. Focus stays locked during a run. | P3 | Planned |
| FR-CAP-06 | White balance is locked at Start. | P3 | Planned |
| FR-CAP-07 | Optional torch with a level setting (off by default), with a heat warning. | P3 | Planned |
| FR-CAP-08 | Live picture with overlays: ROI box, MD arrow and "+" arc, and the last analysis (detected edges coloured by angle, or orientation-field marks) refreshed at ≤ 5 fps. | P4 | Planned |
| FR-CAP-09 | Frames are processed in the sensor's native orientation; the mapping between the screen, the remote preview and the frame is exact (ROI kept in normalized frame coordinates). | P3 | Planned |
| FR-CAP-10 | Interruptions (app in background, call, camera error, system pressure) stop and save a running run; the camera restarts when possible; the screen says what happened. | P3, P5 | Planned |

### 5.3 Region of interest (FR-ROI)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-ROI-01 | The user defines the field of interest by dragging a box on the live picture, on the scanner and on the remote: drag on empty picture to draw a new box, drag inside to move it, drag the corner and edge handles to resize it. | P4, P6 | Planned |
| FR-ROI-02 | Only the ROI is analyzed. The ROI is stored in normalized frame coordinates, persisted with the settings and recorded in every run. | P1, P4 | Planned |
| FR-ROI-03 | The ROI stays inside the frame with a margin for the filters, and has a minimum size (default 256 × 256 px, and at least 2 × the expected flake length when known). The screen shows its size in px (and mm when the scale is known) and the expected number of samples per frame. | P4 | Planned |
| FR-ROI-04 | The ROI is locked while a run is active; a change is applied at the next Start. | P4 | Planned |
| FR-ROI-05 | Default ROI: the central 60 % × 60 % of the frame. | P4 | Planned |
| FR-ROI-06 | Exclusion masks (for belt edges, side walls, fixed objects). | P11 | Planned (backlog) |

### 5.4 Analysis rate (FR-RATE)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-RATE-01 | The user sets the analysis rate in shots per second: 0.1–10 /s in steps of 0.1 below 1 /s and 1 above, capped at the camera frame rate; default 2 /s. | P3, P4 | Planned |
| FR-RATE-02 | Accuracy before speed: frames are picked by timestamp at the set rate; analysis never lowers resolution or quality to keep up. When the analysis of a frame takes longer than the interval, the shots that fall due meanwhile are skipped (never queued, no catch-up burst); a busy analysis never shifts the schedule, so the mean time between shots is at most the longer of the interval and the analysis time, plus one frame interval; the due shots not taken are counted (not the time while the line is stopped) and the achieved rate (per second of moving time) is shown next to the requested rate (design §6.9). | P2, P3 | Planned |
| FR-RATE-03 | Coverage: from the measured speed and the ROI length along MD the screen shows the share of passing material that is analyzed and the overlap between consecutive shots, and suggests the rate without overlap. | P2, P4 | Planned |
| FR-RATE-04 | Analysis pauses while the line is stopped (no movement detected), so standing material is not counted again (on by default). | P2, P3 | Planned |
| FR-RATE-05 | **Snapshot**: one analysis on demand that also saves the frame and its overlay picture: inside the run's `Frames/` (flagged as a snapshot) during a run, otherwise in `Snapshots/` (design §7.2). | P4, P5 | Planned |

### 5.5 Machine direction and speed (FR-DIR)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-DIR-01 | **Auto** (default): MD is measured from the frame-to-frame movement of the material (two-dimensional image registration) and averaged; the screen shows the MD angle relative to the picture axis, its uncertainty and *Detected* when it is stable. | P2, P3 | Planned |
| FR-DIR-02 | **Manual**: the user draws a line along the travel (for example along a side wall) or types the angle. Angles of drawn lines and boxes are computed in pixel coordinates, never in normalized coordinates (which stretch differently along x and y). | P4 | Planned |
| FR-DIR-03 | A run cannot start until MD is detected (Auto) or set (Manual); the remote gets the same reason. | P4, P6 | Planned |
| FR-DIR-04 | MD is fixed for a run and recorded with it. During the run the movement direction is still measured. A confirmed change of more than 0.5° (camera bumped; 0.5° for ≥ 3 s, configurable) excludes the frames from the start of the change with the reason *MD changed* until the direction returns (shots enter the run statistics and files after a delay that covers the confirmation, design §6.8); if it has not returned after 10 s the run stops and saves with that reason, because every later angle would be offset. The event is recorded. | P2, P3, P5, P8 | Planned |
| FR-DIR-05 | Speed in px/s per frame and live; in mm/s (and m/min, ft/min) when the scale is known (FR-CAL-02). | P2, P3 | Planned |

### 5.6 Measurement methods (FR-MEAS)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-MEAS-01 | **Flake edges** (default): straight flake edges are detected with sub-pixel orientation; each edge at least the minimum length long (default 1.5 × the flake width of FR-CAL-07) is one sample with angle, length, centre and contrast. Collinear pieces of one edge interrupted by crossing flakes are merged before counting; edges cut by the ROI border are clipped to the ROI before the minimum length applies (design §6.5). Statistics are count-based (one sample per edge) or, by choice, length-weighted. | P2 | Planned |
| FR-MEAS-02 | **Edge orientation**: a structure-tensor orientation field is sampled on a grid over the ROI; samples are weighted by coherence × edge strength. Reported as the orientation distribution of flake edges and grain (its spread is not a per-flake spread, design §6.4). | P1 | Planned |
| FR-MEAS-03 | **Both**: both methods on the same frame for comparison; the headline numbers use the method chosen as primary. Files keep the methods apart: `Frames.csv` has one row per frame and method with a `method` column, `Samples.csv` holds the *Flake edges* samples and `FrameHistograms.csv` the *Edge orientation* histograms, and the summaries have one block per method (design §7). | P2, P4 | Planned |
| FR-MEAS-04 | Method parameters with defaults and an *Advanced* section: minimum edge length (default from the flake width, FR-CAL-07), integration scale, coherence and contrast thresholds, banding correction for *Edge orientation* (Off / Auto / On; *Auto* corrects only shots with strong bands, *Off* leaves them out, *On* corrects every shot, design §6.2). All are recorded in each run. | P1, P2, P4 | Planned |
| FR-MEAS-05 | Results are deterministic: the same frame, parameters and build give identical results, so saved frames can be re-analyzed reproducibly. | P1, P2 | Planned |
| FR-MEAS-06 | **Flakes (ML)**: per-flake instance segmentation with length and width, trained on the owner's pictures. | P10 | Planned (later) |

